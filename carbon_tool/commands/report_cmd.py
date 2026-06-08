import click
import pandas as pd
from pathlib import Path
from datetime import datetime
from tabulate import tabulate
from ..utils import format_number, safe_float


@click.group()
def report():
    """排放报告生成"""
    pass


@report.command('annual')
@click.option('--year', '-y', help='指定年份')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--output', '-o', 'output_file', help='输出文件名')
@click.option('--threshold', '-t', default=30.0, type=float, help='异常波动阈值')
@click.pass_context
def annual_report(ctx, year, input_file, output_file, threshold):
    """生成年度排放报告（含目标差距、减排、产品分摊、异常摘要）"""
    config = ctx.obj['config']
    dm = ctx.obj['dm']
    logger = ctx.obj['logger']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('report.annual', {'input': input_file, 'year': year}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns or 'date' not in df.columns:
            click.echo("❌ 错误: 数据缺少必要字段，请先运行 'carbon-tool calc run'")
            ctx.exit(1)

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])

        if year:
            df = df[df['date'].dt.year == int(year)]
            report_year = int(year)
        else:
            report_year = df['date'].dt.year.max()
            df = df[df['date'].dt.year == report_year]

        if df.empty:
            click.echo("⚠️  没有数据")
            return

        targets = dm.load_targets()
        reductions = dm.load_reductions()
        allocations = dm.load_allocations()

        total_emissions = df['emissions'].sum()
        scope1_total = df[df['scope'] == '范围1']['emissions'].sum() if 'scope' in df.columns else 0
        scope2_total = df[df['scope'] == '范围2']['emissions'].sum() if 'scope' in df.columns else 0
        scope3_total = df[df['scope'] == '范围3']['emissions'].sum() if 'scope' in df.columns else 0

        df['month'] = df['date'].dt.strftime('%m')
        monthly = df.groupby('month')['emissions'].sum().sort_index()

        dept_summary = df.groupby('department')['emissions'].sum().sort_values(ascending=False) if 'department' in df.columns else pd.Series()

        anomalies = _detect_anomalies(df, threshold, 'department')

        target_gap = None
        year_target = next((t for t in targets if t.year == report_year), None)
        if year_target:
            target_gap = {
                'scope1': year_target.scope1_target - scope1_total,
                'scope2': year_target.scope2_target - scope2_total,
                'scope3': year_target.scope3_target - scope3_total,
                'total': year_target.total_target - total_emissions,
                'target_total': year_target.total_target,
            }

        product_results = None
        if allocations and 'product' in df.columns and df['product'].notna().any():
            product_results = []
            for alloc in allocations:
                alloc_emis = total_emissions * alloc.allocation_ratio
                product_results.append({
                    'product': alloc.product,
                    'allocation_ratio': alloc.allocation_ratio,
                    'emissions': alloc_emis,
                    'department': alloc.department,
                })
        elif 'product' in df.columns and df['product'].notna().any():
            product_summary = df.groupby('product')['emissions'].sum().sort_values(ascending=False)
            product_results = [
                {'product': p, 'emissions': v, 'allocation_ratio': v / total_emissions if total_emissions else 0}
                for p, v in product_summary.items()
            ]

        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append(f"📄 {report_year}年度碳排放报告")
        report_lines.append("=" * 60)
        report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("")

        report_lines.append("一、排放总览")
        report_lines.append("-" * 40)
        report_lines.append(f"  总排放量:       {format_number(total_emissions, 2)} tCO2e")
        report_lines.append(f"  范围1排放:     {format_number(scope1_total, 2)} tCO2e")
        report_lines.append(f"  范围2排放:     {format_number(scope2_total, 2)} tCO2e")
        report_lines.append(f"  范围3排放:     {format_number(scope3_total, 2)} tCO2e")
        report_lines.append(f"  记录总数:      {len(df)} 条")
        report_lines.append(f"  涉及部门:      {df['department'].nunique() if 'department' in df.columns else 0} 个")
        report_lines.append("")

        if not monthly.empty:
            report_lines.append("二、月度排放趋势")
            report_lines.append("-" * 40)
            for m, v in monthly.items():
                bar_len = int(v / monthly.max() * 30) if monthly.max() > 0 else 0
                bar = '█' * bar_len
                report_lines.append(f"  {m}月: {format_number(v, 2):>12} tCO2e {bar}")
            report_lines.append("")

        if not dept_summary.empty:
            report_lines.append("三、部门排放排行")
            report_lines.append("-" * 40)
            dept_table = []
            for dept, emis in dept_summary.items():
                pct = emis / total_emissions * 100 if total_emissions else 0
                dept_table.append([dept, f"{format_number(emis, 2)} tCO2e", f"{pct:.2f}%"])
            report_lines.append(tabulate(dept_table, headers=['部门', '排放量', '占比'], tablefmt='simple'))
            report_lines.append("")

        if target_gap is not None:
            report_lines.append("四、目标达成情况")
            report_lines.append("-" * 40)
            t = target_gap
            report_lines.append(f"  年度目标:       {format_number(t['target_total'], 2)} tCO2e")
            report_lines.append(f"  实际排放:       {format_number(total_emissions, 2)} tCO2e")
            gap_status = "✅ 已达成" if t['total'] >= 0 else "❌ 未达成"
            report_lines.append(f"  目标差距:       {format_number(abs(t['total']), 2)} tCO2e {gap_status}")
            report_lines.append(f"    范围1差距:    {format_number(t['scope1'], 2)} tCO2e")
            report_lines.append(f"    范围2差距:    {format_number(t['scope2'], 2)} tCO2e")
            report_lines.append(f"    范围3差距:    {format_number(t['scope3'], 2)} tCO2e")
            report_lines.append("")

        if reductions:
            report_lines.append("五、减排措施与成果")
            report_lines.append("-" * 40)
            total_reduction = sum(r.reduction_amount for r in reductions)
            report_lines.append(f"  减排措施总数:   {len(reductions)} 项")
            report_lines.append(f"  累计减排量:     {format_number(total_reduction, 2)} tCO2e")
            report_lines.append("")
            for r in reductions[:10]:
                report_lines.append(f"  • [{r.date}] {r.measure}: {format_number(r.reduction_amount, 2)} tCO2e ({r.department})")
            if len(reductions) > 10:
                report_lines.append(f"  ... 还有 {len(reductions) - 10} 项")
            report_lines.append("")

        if product_results:
            report_lines.append("六、产品分摊结果")
            report_lines.append("-" * 40)
            prod_table = []
            for p in product_results:
                ratio = p.get('allocation_ratio', 0) * 100
                prod_table.append([
                    p['product'],
                    f"{format_number(p['emissions'], 2)} tCO2e",
                    f"{ratio:.2f}%",
                    p.get('department', '')
                ])
            report_lines.append(tabulate(prod_table, headers=['产品', '分摊排放量', '分摊比例', '部门'], tablefmt='simple'))
            report_lines.append("")

        if anomalies:
            report_lines.append("七、异常波动摘要")
            report_lines.append("-" * 40)
            report_lines.append(f"  异常记录数: {len(anomalies)} 条 (阈值 ±{threshold}%)")
            report_lines.append("")
            for a in anomalies[:10]:
                report_lines.append(f"  • [{a.get('department', '')} {a['月份']}: {a['变化率']:+.2f}% ({a['方向']})")
            if len(anomalies) > 10:
                report_lines.append(f"  ... 还有 {len(anomalies) - 10} 条")
            report_lines.append("")

        report_lines.append("=" * 60)
        report_lines.append("报告结束")
        report_lines.append("=" * 60)

        report_text = "\n".join(report_lines)
        click.echo(report_text)

        if output_file:
            output_path = config.output_dir / output_file
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            click.echo(f"\n💾 报告已保存到: {output_path}")

        logger.log('report.annual', {'year': report_year, 'input': input_file}, 'success',
                   f'年度报告生成，总排放{format_number(total_emissions, 2)}tCO2e')

    except Exception as e:
        click.echo(f"❌ 报告生成失败: {e}")
        logger.log('report.annual', {'input': input_file, 'year': year}, 'failed', str(e))
        ctx.exit(1)


def _detect_anomalies(df, threshold, group_by='department'):
    if 'date' not in df.columns or 'emissions' not in df.columns:
        return []
    df = df.copy()
    df['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
    if group_by not in df.columns:
        group_by = 'department'

    anomalies = []
    groups = df[group_by].dropna().unique()
    for group in groups:
        group_df = df[df[group_by] == group]
        monthly = group_df.groupby('month')['emissions'].sum().sort_index()
        if len(monthly) < 2:
            continue
        for i in range(1, len(monthly)):
            prev_val = monthly.iloc[i - 1]
            curr_val = monthly.iloc[i]
            if prev_val == 0:
                continue
            pct_change = abs((curr_val - prev_val) / prev_val * 100)
            if pct_change > threshold:
                anomalies.append({
                    group_by: group,
                    '月份': monthly.index[i],
                    '变化率': round((curr_val - prev_val) / prev_val * 100, 2),
                    '方向': "上升" if curr_val > prev_val else "下降",
                })
    return anomalies


@report.command('summary')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.pass_context
def summary_report(ctx, input_file):
    """快速汇总报告"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('report.summary', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns:
            click.echo("❌ 错误: 数据缺少 emissions 字段")
            ctx.exit(1)

        total = df['emissions'].sum()
        record_count = len(df)

        click.echo("📊 排放数据汇总")
        click.echo("=" * 40)
        click.echo(f"总排放量:  {format_number(total, 2)} tCO2e")
        click.echo(f"记录总数:  {record_count} 条")

        if 'scope' in df.columns:
            scope_summary = df.groupby('scope')['emissions'].sum()
            click.echo(f"\n按范围:")
            for scope, val in scope_summary.items():
                pct = val / total * 100 if total else 0
                click.echo(f"  {scope}: {format_number(val, 2)} tCO2e ({pct:.1f}%)")

        if 'department' in df.columns:
            dept_count = df['department'].nunique()
            click.echo(f"\n部门数: {dept_count} 个")

        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
            if not df.empty:
                date_min = df['date'].min().strftime('%Y-%m-%d')
                date_max = df['date'].max().strftime('%Y-%m-%d')
                click.echo(f"数据区间:  {date_min} ~ {date_max}")

        click.echo("=" * 40)

        logger.log('report.summary', {'input': input_file}, 'success',
                   f'汇总报告，总排放{format_number(total, 2)}tCO2e')

    except Exception as e:
        click.echo(f"❌ 失败: {e}")
        logger.log('report.summary', {'input': input_file}, 'failed', str(e))
        ctx.exit(1)

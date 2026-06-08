import click
import pandas as pd
from pathlib import Path
from ..utils import write_excel


@click.group()
def export():
    """数据导出"""
    pass


@export.command('excel')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--output', '-o', 'output_file', default='emissions_report.xlsx', help='输出文件名')
@click.option('--year', '-y', help='指定年份')
@click.option('--threshold', '-t', default=30.0, type=float, help='异常波动阈值')
@click.pass_context
def export_excel(ctx, input_file, output_file, year, threshold):
    """导出 Excel 报告（多工作表：明细/月度/部门/范围/产品/异常/目标差距）"""
    config = ctx.obj['config']
    dm = ctx.obj['dm']
    logger = ctx.obj['logger']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('export.excel', {'input': input_file}, 'failed', '输入文件不存在')
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

        if df.empty:
            click.echo("⚠️  没有数据可导出")
            return

        df_export = df.copy()
        df_export['date'] = df_export['date'].dt.strftime('%Y-%m-%d')

        sheets = {}
        sheets['排放明细'] = df_export

        df_month = df.copy()
        df_month['month'] = df_month['date'].dt.strftime('%Y-%m')
        monthly_summary = df_month.groupby('month')['emissions'].sum().reset_index()
        monthly_summary.columns = ['月份', '排放量(tCO2e)']
        monthly_summary = monthly_summary.sort_values('月份')
        monthly_summary['环比变化(%)'] = monthly_summary['排放量(tCO2e)'].pct_change() * 100
        sheets['月度汇总'] = monthly_summary.round(4)

        if 'department' in df.columns:
            dept_summary = df.groupby('department')['emissions'].agg(['sum', 'count']).reset_index()
            dept_summary.columns = ['部门', '排放量(tCO2e)', '记录数']
            dept_summary = dept_summary.sort_values('排放量(tCO2e)', ascending=False)
            total_emis = dept_summary['排放量(tCO2e)'].sum()
            dept_summary['占比(%)'] = dept_summary['排放量(tCO2e)'] / total_emis * 100 if total_emis else 0
            sheets['部门汇总'] = dept_summary.round(4)

        if 'scope' in df.columns:
            scope_summary = df.groupby('scope')['emissions'].agg(['sum', 'count']).reset_index()
            scope_summary.columns = ['范围', '排放量(tCO2e)', '记录数']
            scope_summary['占比(%)'] = scope_summary['排放量(tCO2e)'] / total_emis * 100 if total_emis else 0
            sheets['范围汇总'] = scope_summary.round(4)

        if 'product' in df.columns and df['product'].notna().any():
            prod_summary = df.groupby('product')['emissions'].agg(['sum', 'count']).reset_index()
            prod_summary.columns = ['产品', '排放量(tCO2e)', '记录数']
            prod_summary = prod_summary.sort_values('排放量(tCO2e)', ascending=False)
            prod_summary['占比(%)'] = prod_summary['排放量(tCO2e)'] / total_emis * 100 if total_emis else 0
            sheets['产品汇总'] = prod_summary.round(4)

        anomalies = _detect_anomalies_df(df, threshold, 'department')
        if not anomalies.empty:
            sheets['异常波动'] = anomalies.round(4)

        targets = dm.load_targets()
        if targets:
            report_year = year or df['date'].dt.year.max()
            year_target = next((t for t in targets if t.year == int(report_year)), None)
            if year_target:
                scope1 = df[df['scope'] == '范围1']['emissions'].sum() if 'scope' in df.columns else 0
                scope2 = df[df['scope'] == '范围2']['emissions'].sum() if 'scope' in df.columns else 0
                scope3 = df[df['scope'] == '范围3']['emissions'].sum() if 'scope' in df.columns else 0
                total = df['emissions'].sum()

                target_df = pd.DataFrame([
                    ['范围1', year_target.scope1_target, scope1, year_target.scope1_target - scope1],
                    ['范围2', year_target.scope2_target, scope2, year_target.scope2_target - scope2],
                    ['范围3', year_target.scope3_target, scope3, year_target.scope3_target - scope3],
                    ['总计', year_target.total_target, total, year_target.total_target - total],
                ], columns=['类别', '目标值(tCO2e)', '实际值(tCO2e)', '差距(tCO2e)'])
                target_df['达成率(%)'] = (
                    (target_df['实际值(tCO2e)'] / target_df['目标值(tCO2e)'] * 100)
                    .where(target_df['目标值(tCO2e)'] != 0, 0)
                )
                sheets['目标差距'] = target_df.round(4)

        reductions = dm.load_reductions()
        if reductions:
            red_df = pd.DataFrame([{
                '日期': r.date,
                '措施': r.measure,
                '减排量(tCO2e)': r.reduction_amount,
                '部门': r.department,
                '描述': r.description,
            } for r in reductions])
            sheets['减排措施'] = red_df

        allocations = dm.load_allocations()
        if allocations:
            total_e = df['emissions'].sum()
            alloc_df = pd.DataFrame([{
                '产品': a.product,
                '分摊比例(%)': a.allocation_ratio * 100,
                '分摊排放量(tCO2e)': total_e * a.allocation_ratio,
                '部门': a.department,
            } for a in allocations])
            sheets['产品分摊'] = alloc_df.round(4)

        output_path = config.output_dir / output_file
        write_excel(sheets, output_path)

        click.echo(f"✅ Excel 报告已导出: {output_path}")
        click.echo(f"   包含 {len(sheets)} 个工作表: {', '.join(sheets.keys())}")

        logger.log('export.excel', {
            'input': input_file, 'output': output_file, 'sheets': list(sheets.keys())
        }, 'success', f'导出Excel，共{len(sheets)}个工作表')

    except Exception as e:
        click.echo(f"❌ 导出失败: {e}")
        logger.log('export.excel', {'input': input_file, 'output': output_file}, 'failed', str(e))
        ctx.exit(1)


def _detect_anomalies_df(df, threshold, group_by='department'):
    if 'date' not in df.columns or 'emissions' not in df.columns:
        return pd.DataFrame()
    df = df.copy()
    df['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
    if group_by not in df.columns:
        group_by = 'department'

    rows = []
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
            pct_change = (curr_val - prev_val) / prev_val * 100
            if abs(pct_change) > threshold:
                rows.append({
                    '分组': group,
                    '月份': monthly.index[i],
                    '上月排放量(tCO2e)': round(prev_val, 4),
                    '本月排放量(tCO2e)': round(curr_val, 4),
                    '变化量(tCO2e)': round(curr_val - prev_val, 4),
                    '变化率(%)': round(pct_change, 2),
                    '方向': "上升" if curr_val > prev_val else "下降",
                })
    return pd.DataFrame(rows)


@export.command('csv')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--output', '-o', 'output_file', default='emissions_export.csv', help='输出文件名')
@click.option('--scope', help='按范围筛选')
@click.option('--department', help='按部门筛选')
@click.pass_context
def export_csv(ctx, input_file, output_file, scope, department):
    """导出 CSV 数据"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('export.csv', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')

        if scope and 'scope' in df.columns:
            df = df[df['scope'] == scope]
        if department and 'department' in df.columns:
            df = df[df['department'] == department]

        if df.empty:
            click.echo("⚠️  没有数据可导出")
            return

        output_path = config.output_dir / output_file
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo(f"✅ CSV 已导出: {output_path}")
        click.echo(f"   共 {len(df)} 条记录")

        logger.log('export.csv', {
            'input': input_file, 'output': output_file, 'rows': len(df)
        }, 'success', f'导出CSV，{len(df)}条记录')

    except Exception as e:
        click.echo(f"❌ 导出失败: {e}")
        logger.log('export.csv', {'input': input_file, 'output': output_file}, 'failed', str(e))
        ctx.exit(1)

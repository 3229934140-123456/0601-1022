import click
import pandas as pd
from datetime import datetime
from tabulate import tabulate
from pathlib import Path
from ..config import Config
from ..logger import CommandLogger
from ..data_manager import DataManager
from ..models import Target, ReductionRecord
from ..utils import format_number, safe_float


@click.group()
def report():
    """报告生成与减排管理"""
    pass


@report.group()
def target():
    """减排目标管理"""
    pass


@target.command('set')
@click.option('--year', '-y', type=int, required=True, help='目标年份')
@click.option('--scope1', type=float, default=0.0, help='范围1目标 (tCO2e)')
@click.option('--scope2', type=float, default=0.0, help='范围2目标 (tCO2e)')
@click.option('--scope3', type=float, default=0.0, help='范围3目标 (tCO2e)')
@click.option('--total', type=float, default=0.0, help='总目标 (tCO2e)')
@click.option('--description', '-d', default='', help='目标描述')
@click.pass_context
def set_target(ctx, year, scope1, scope2, scope3, total, description):
    """设置年度减排目标"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        t = Target(
            year=year,
            scope1_target=scope1,
            scope2_target=scope2,
            scope3_target=scope3,
            total_target=total,
            description=description
        )
        dm.add_target(t)
        click.echo(f"✅ {year} 年度减排目标设置成功")
        click.echo(f"   范围1: {scope1:,.2f} tCO2e")
        click.echo(f"   范围2: {scope2:,.2f} tCO2e")
        click.echo(f"   范围3: {scope3:,.2f} tCO2e")
        click.echo(f"   总计: {total:,.2f} tCO2e")
        logger.log('report.target.set', {'year': year}, 'success', f'设置{year}年目标')
    except Exception as e:
        click.echo(f"❌ 设置失败: {e}")
        logger.log('report.target.set', {'year': year}, 'failed', str(e))
        ctx.exit(1)


@target.command('list')
@click.pass_context
def list_targets(ctx):
    """列出所有减排目标"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        targets = dm.load_targets()
        if not targets:
            click.echo("📋 暂无减排目标")
            return

        click.echo("📋 减排目标列表:")
        table = []
        for t in sorted(targets, key=lambda x: x.year):
            table.append([
                t.year,
                f"{t.scope1_target:,.2f}",
                f"{t.scope2_target:,.2f}",
                f"{t.scope3_target:,.2f}",
                f"{t.total_target:,.2f}",
                t.description or '-'
            ])
        click.echo(tabulate(table, headers=['年份', '范围1(tCO2e)', '范围2(tCO2e)',
                                            '范围3(tCO2e)', '总计(tCO2e)', '描述'],
                            tablefmt='simple'))
        logger.log('report.target.list', {}, 'success', f'列出{len(targets)}个目标')
    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('report.target.list', {}, 'failed', str(e))
        ctx.exit(1)


@target.command('gap')
@click.option('--year', '-y', type=int, help='指定年份（默认最近一年）')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='排放数据文件')
@click.pass_context
def target_gap(ctx, year, input_file):
    """目标差距分析"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 排放数据文件不存在: {input_path}")
        logger.log('report.target.gap', {'input': input_file}, 'failed', '数据文件不存在')
        ctx.exit(1)

    try:
        targets = dm.load_targets()
        if not targets:
            click.echo("⚠️  暂未设置减排目标，请先运行 'carbon-tool report target set'")
            ctx.exit(1)

        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns or 'date' not in df.columns:
            click.echo("❌ 错误: 数据缺少必要字段")
            ctx.exit(1)

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df['year'] = df['date'].dt.year

        if year:
            target_year = year
        else:
            target_year = max(t.year for t in targets)

        target = next((t for t in targets if t.year == target_year), None)
        if not target:
            click.echo(f"❌ 错误: {target_year} 年没有设置目标")
            ctx.exit(1)

        year_df = df[df['year'] == target_year]

        scope_data = {}
        if 'scope' in year_df.columns:
            for scope in ['范围1', '范围2', '范围3']:
                scope_data[scope] = year_df[year_df['scope'] == scope]['emissions'].sum()
        else:
            scope_data = {'范围1': 0, '范围2': 0, '范围3': 0}

        actual_total = year_df['emissions'].sum()
        target_total = target.total_target
        gap = target_total - actual_total
        gap_pct = (gap / target_total * 100) if target_total > 0 else 0

        click.echo(f"📊 {target_year} 年目标差距分析:")
        click.echo("=" * 50)

        table = []
        for scope_name in ['范围1', '范围2', '范围3']:
            actual = scope_data.get(scope_name, 0)
            tgt = getattr(target, f"scope{scope_name[-1]}_target", 0)
            g = tgt - actual
            gp = (g / tgt * 100) if tgt > 0 else 0
            status = "✅ 达标" if g >= 0 else "❌ 超标"
            table.append([
                scope_name,
                f"{actual:,.2f}",
                f"{tgt:,.2f}",
                f"{g:+,.2f}",
                f"{gp:+.2f}%",
                status
            ])

        total_status = "✅ 达标" if gap >= 0 else "❌ 超标"
        table.append([
            '总计',
            f"{actual_total:,.2f}",
            f"{target_total:,.2f}",
            f"{gap:+,.2f}",
            f"{gap_pct:+.2f}%",
            total_status
        ])

        click.echo(tabulate(table, headers=['范围', '实际排放(tCO2e)', '目标(tCO2e)',
                                            '差距(tCO2e)', '差距率', '状态'],
                            tablefmt='simple'))

        if gap >= 0:
            click.echo(f"\n🎉 已实现减排目标！还有 {format_number(gap, 2)} tCO2e 的减排空间")
        else:
            click.echo(f"\n⚠️  未达成目标，超出 {format_number(abs(gap), 2)} tCO2e，需加强减排措施")

        logger.log('report.target.gap', {'year': target_year, 'input': input_file}, 'success',
                   f'目标差距分析，差距{gap:+.2f} tCO2e')

    except Exception as e:
        click.echo(f"❌ 分析失败: {e}")
        logger.log('report.target.gap', {'year': year, 'input': input_file}, 'failed', str(e))
        ctx.exit(1)


@report.group()
def reduction():
    """减排量录入与管理"""
    pass


@reduction.command('add')
@click.option('--date', '-d', required=True, help='减排日期 YYYY-MM-DD')
@click.option('--measure', '-m', required=True, help='减排措施名称')
@click.option('--amount', '-a', type=float, required=True, help='减排量 (tCO2e)')
@click.option('--department', '-dept', default='', help='责任部门')
@click.option('--description', '-desc', default='', help='详细描述')
@click.pass_context
def add_reduction(ctx, date, measure, amount, department, description):
    """录入减排措施"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        record = ReductionRecord(
            date=date,
            measure=measure,
            reduction_amount=amount,
            department=department,
            description=description
        )
        rec_id = dm.add_reduction(record)
        click.echo(f"✅ 减排措施录入成功 (ID: {rec_id})")
        click.echo(f"   日期: {date}")
        click.echo(f"   措施: {measure}")
        click.echo(f"   减排量: {amount:,.2f} tCO2e")
        click.echo(f"   部门: {department or '-'}")
        logger.log('report.reduction.add', {'measure': measure}, 'success',
                   f'录入减排措施: {measure}, {amount} tCO2e')
    except Exception as e:
        click.echo(f"❌ 录入失败: {e}")
        logger.log('report.reduction.add', {'measure': measure}, 'failed', str(e))
        ctx.exit(1)


@reduction.command('list')
@click.option('--year', '-y', type=int, help='按年份筛选')
@click.option('--department', '-dept', help='按部门筛选')
@click.pass_context
def list_reductions(ctx, year, department):
    """列出减排措施"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        reductions = dm.load_reductions()

        if year:
            reductions = [r for r in reductions if r.date.startswith(str(year))]
        if department:
            reductions = [r for r in reductions if department in r.department]

        if not reductions:
            click.echo("📋 暂无减排措施记录")
            return

        total = sum(r.reduction_amount for r in reductions)

        click.echo(f"📋 减排措施列表 (共 {len(reductions)} 项):")
        table = []
        for r in sorted(reductions, key=lambda x: x.date):
            table.append([
                r.id[:8],
                r.date,
                r.measure,
                f"{r.reduction_amount:,.2f}",
                r.department or '-',
                r.description[:30] if r.description else '-'
            ])
        click.echo(tabulate(table, headers=['ID', '日期', '措施', '减排量(tCO2e)', '部门', '描述'],
                            tablefmt='simple'))

        click.echo(f"\n📊 总减排量: {format_number(total, 2)} tCO2e")

        logger.log('report.reduction.list', {'year': year, 'department': department}, 'success',
                   f'列出{len(reductions)}项减排措施')
    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('report.reduction.list', {}, 'failed', str(e))
        ctx.exit(1)


@report.group()
def allocation():
    """产品分摊管理"""
    pass


@allocation.command('set')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='排放数据文件')
@click.option('--product', '-p', required=True, help='产品名称')
@click.option('--ratio', '-r', type=float, required=True, help='分摊比例 (0-1)')
@click.option('--department', '-dept', default='', help='所属部门')
@click.pass_context
def set_allocation(ctx, input_file, product, ratio, department):
    """设置产品分摊比例"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    if ratio < 0 or ratio > 1:
        click.echo("❌ 错误: 分摊比例必须在 0 到 1 之间")
        ctx.exit(1)

    alloc_file = config.data_dir / 'product_allocations.csv'

    try:
        if alloc_file.exists():
            df = pd.read_csv(alloc_file, encoding='utf-8-sig')
        else:
            df = pd.DataFrame(columns=['product', 'allocation_ratio', 'department'])

        existing = df[(df['product'] == product) & (df['department'] == department)]
        if not existing.empty:
            df.loc[existing.index, 'allocation_ratio'] = ratio
            click.echo(f"✅ 已更新产品 '{product}' 的分摊比例为 {ratio:.2%}")
        else:
            new_row = pd.DataFrame([{'product': product, 'allocation_ratio': ratio, 'department': department}])
            df = pd.concat([df, new_row], ignore_index=True)
            click.echo(f"✅ 已添加产品 '{product}'，分摊比例为 {ratio:.2%}")

        df.to_csv(alloc_file, index=False, encoding='utf-8-sig')
        logger.log('report.allocation.set', {'product': product, 'ratio': ratio}, 'success',
                   f'设置产品分摊: {product} = {ratio}')

    except Exception as e:
        click.echo(f"❌ 设置失败: {e}")
        logger.log('report.allocation.set', {'product': product}, 'failed', str(e))
        ctx.exit(1)


@allocation.command('calc')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='排放数据文件')
@click.option('--output', '-o', default='product_emissions.csv', help='输出文件名')
@click.pass_context
def calc_allocation(ctx, input_file, output):
    """计算产品分摊排放量"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    alloc_file = config.data_dir / 'product_allocations.csv'

    if not input_path.exists():
        click.echo(f"❌ 错误: 排放数据文件不存在: {input_path}")
        logger.log('report.allocation.calc', {'input': input_file}, 'failed', '数据文件不存在')
        ctx.exit(1)

    if not alloc_file.exists():
        click.echo("❌ 错误: 未设置产品分摊比例，请先运行 'carbon-tool report allocation set'")
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        alloc_df = pd.read_csv(alloc_file, encoding='utf-8-sig')

        if df.empty or alloc_df.empty:
            click.echo("⚠️  没有可计算的数据")
            return

        results = []
        for _, alloc_row in alloc_df.iterrows():
            product = alloc_row['product']
            ratio = alloc_row['allocation_ratio']
            dept = alloc_row.get('department', '')

            if dept and 'department' in df.columns:
                dept_df = df[df['department'] == dept]
            else:
                dept_df = df

            total_emissions = dept_df['emissions'].sum() if 'emissions' in dept_df.columns else 0
            product_emissions = total_emissions * ratio

            results.append({
                '产品': product,
                '部门': dept or '全部',
                '分摊比例': f"{ratio:.2%}",
                '总排放量 (tCO2e)': round(total_emissions, 4),
                '产品排放量 (tCO2e)': round(product_emissions, 4),
            })

        result_df = pd.DataFrame(results)
        output_path = config.output_dir / output
        result_df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo("📊 产品分摊计算结果:")
        click.echo(tabulate(result_df, headers='keys', tablefmt='simple', showindex=False))
        click.echo(f"\n💾 结果已保存到: {output_path}")

        logger.log('report.allocation.calc', {'input': input_file, 'output': output}, 'success',
                   f'计算{len(results)}个产品的分摊排放量')

    except Exception as e:
        click.echo(f"❌ 计算失败: {e}")
        logger.log('report.allocation.calc', {'input': input_file, 'output': output}, 'failed', str(e))
        ctx.exit(1)


@report.command('generate')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='排放数据文件')
@click.option('--output', '-o', 'output_file', default='carbon_report.txt', help='报告文件名')
@click.option('--format', '-f', 'fmt', default='txt', type=click.Choice(['txt', 'markdown', 'html']),
              help='报告格式')
@click.option('--year', '-y', type=int, help='指定报告年份')
@click.pass_context
def generate_report(ctx, input_file, output_file, fmt, year):
    """生成碳排报告"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 排放数据文件不存在: {input_path}")
        logger.log('report.generate', {'input': input_file}, 'failed', '数据文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns or 'date' not in df.columns:
            click.echo("❌ 错误: 数据缺少必要字段，请先运行 'carbon-tool calc run'")
            ctx.exit(1)

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])

        if year:
            df = df[df['date'].dt.year == year]

        if df.empty:
            click.echo("⚠️  没有数据可生成报告")
            return

        report_content = _build_report(df, config, dm, fmt, year)

        output_path = config.output_dir / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        click.echo(f"✅ 报告已生成: {output_path}")
        click.echo(f"   格式: {fmt}")

        logger.log('report.generate', {'input': input_file, 'output': output_file, 'format': fmt},
                   'success', f'生成{fmt}格式报告')

    except Exception as e:
        click.echo(f"❌ 生成失败: {e}")
        logger.log('report.generate', {'input': input_file, 'output': output_file}, 'failed', str(e))
        ctx.exit(1)


def _build_report(df, config, dm, fmt, year):
    """构建报告内容"""
    total_emissions = df['emissions'].sum()
    record_count = len(df)

    title_year = f"{year} 年度" if year else ""

    if fmt == 'markdown':
        report = f"# {title_year}企业碳排放报告\n\n"
        report += f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report += f"**项目**: {config.get('project_name', '未知')}\n\n"
        report += "---\n\n"

        report += "## 一、总体排放情况\n\n"
        report += f"- **总排放量**: {total_emissions:,.2f} tCO2e\n"
        report += f"- **数据记录数**: {record_count} 条\n"
        report += f"- **统计周期**: {df['date'].min().strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}\n\n"

        if 'scope' in df.columns:
            report += "## 二、按范围分类\n\n"
            scope_summary = df.groupby('scope')['emissions'].sum().reset_index()
            scope_summary['占比'] = scope_summary['emissions'] / total_emissions * 100
            report += "| 范围 | 排放量 (tCO2e) | 占比 |\n"
            report += "|------|---------------|------|\n"
            for _, row in scope_summary.iterrows():
                report += f"| {row['scope']} | {row['emissions']:,.2f} | {row['占比']:.2f}% |\n"
            report += "\n"

        if 'department' in df.columns:
            report += "## 三、按部门分类\n\n"
            dept_summary = df.groupby('department')['emissions'].sum().sort_values(ascending=False).reset_index()
            dept_summary['占比'] = dept_summary['emissions'] / total_emissions * 100
            report += "| 部门 | 排放量 (tCO2e) | 占比 |\n"
            report += "|------|---------------|------|\n"
            for _, row in dept_summary.iterrows():
                report += f"| {row['department']} | {row['emissions']:,.2f} | {row['占比']:.2f}% |\n"
            report += "\n"

        df['month'] = df['date'].dt.strftime('%Y-%m')
        monthly = df.groupby('month')['emissions'].sum().sort_index().reset_index()
        report += "## 四、月度排放趋势\n\n"
        report += "| 月份 | 排放量 (tCO2e) |\n"
        report += "|------|---------------|\n"
        for _, row in monthly.iterrows():
            report += f"| {row['month']} | {row['emissions']:,.2f} |\n"
        report += "\n"

        reductions = dm.load_reductions()
        if reductions:
            report += "## 五、减排措施\n\n"
            total_reduction = sum(r.reduction_amount for r in reductions)
            report += f"**减排措施总数**: {len(reductions)} 项\n\n"
            report += f"**总减排量**: {total_reduction:,.2f} tCO2e\n\n"
            report += "| 日期 | 措施 | 减排量 (tCO2e) | 部门 |\n"
            report += "|------|------|---------------|------|\n"
            for r in sorted(reductions, key=lambda x: x.date)[:10]:
                report += f"| {r.date} | {r.measure} | {r.reduction_amount:,.2f} | {r.department or '-'} |\n"
            report += "\n"

        report += "---\n\n"
        report += "*本报告由 carbon-tool 自动生成*\n"

    elif fmt == 'html':
        report = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title_year}企业碳排放报告</title>
    <style>
        body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ color: #2c5f2d; border-bottom: 3px solid #97bc62; padding-bottom: 10px; }}
        h2 {{ color: #2c5f2d; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
        th {{ background-color: #97bc62; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .summary {{ background: #f0f7f0; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        .footer {{ margin-top: 40px; color: #999; font-size: 0.9em; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }}
    </style>
</head>
<body>
    <h1>{title_year}企业碳排放报告</h1>
    <p><strong>生成时间</strong>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p><strong>项目</strong>: {config.get('project_name', '未知')}</p>

    <h2>一、总体排放情况</h2>
    <div class="summary">
        <p><strong>总排放量</strong>: {total_emissions:,.2f} tCO2e</p>
        <p><strong>数据记录数</strong>: {record_count} 条</p>
        <p><strong>统计周期</strong>: {df['date'].min().strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}</p>
    </div>
"""
        if 'scope' in df.columns:
            scope_summary = df.groupby('scope')['emissions'].sum().reset_index()
            scope_summary['占比'] = scope_summary['emissions'] / total_emissions * 100
            report += "<h2>二、按范围分类</h2>\n<table>\n<tr><th>范围</th><th>排放量 (tCO2e)</th><th>占比</th></tr>\n"
            for _, row in scope_summary.iterrows():
                report += f"<tr><td>{row['scope']}</td><td>{row['emissions']:,.2f}</td><td>{row['占比']:.2f}%</td></tr>\n"
            report += "</table>\n"

        if 'department' in df.columns:
            dept_summary = df.groupby('department')['emissions'].sum().sort_values(ascending=False).reset_index()
            dept_summary['占比'] = dept_summary['emissions'] / total_emissions * 100
            report += "<h2>三、按部门分类</h2>\n<table>\n<tr><th>部门</th><th>排放量 (tCO2e)</th><th>占比</th></tr>\n"
            for _, row in dept_summary.iterrows():
                report += f"<tr><td>{row['department']}</td><td>{row['emissions']:,.2f}</td><td>{row['占比']:.2f}%</td></tr>\n"
            report += "</table>\n"

        df['month'] = df['date'].dt.strftime('%Y-%m')
        monthly = df.groupby('month')['emissions'].sum().sort_index().reset_index()
        report += "<h2>四、月度排放趋势</h2>\n<table>\n<tr><th>月份</th><th>排放量 (tCO2e)</th></tr>\n"
        for _, row in monthly.iterrows():
            report += f"<tr><td>{row['month']}</td><td>{row['emissions']:,.2f}</td></tr>\n"
        report += "</table>\n"

        reductions = dm.load_reductions()
        if reductions:
            total_reduction = sum(r.reduction_amount for r in reductions)
            report += f"<h2>五、减排措施</h2>\n"
            report += f"<p><strong>减排措施总数</strong>: {len(reductions)} 项</p>\n"
            report += f"<p><strong>总减排量</strong>: {total_reduction:,.2f} tCO2e</p>\n"
            report += "<table>\n<tr><th>日期</th><th>措施</th><th>减排量 (tCO2e)</th><th>部门</th></tr>\n"
            for r in sorted(reductions, key=lambda x: x.date)[:10]:
                report += f"<tr><td>{r.date}</td><td>{r.measure}</td><td>{r.reduction_amount:,.2f}</td><td>{r.department or '-'}</td></tr>\n"
            report += "</table>\n"

        report += """
    <div class="footer">
        本报告由 carbon-tool 自动生成
    </div>
</body>
</html>
"""

    else:
        report = "=" * 60 + "\n"
        report += f"  {title_year}企业碳排放报告\n"
        report += "=" * 60 + "\n\n"
        report += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"项目: {config.get('project_name', '未知')}\n\n"

        report += "【一、总体排放情况】\n"
        report += "-" * 40 + "\n"
        report += f"总排放量: {total_emissions:,.2f} tCO2e\n"
        report += f"数据记录数: {record_count} 条\n"
        report += f"统计周期: {df['date'].min().strftime('%Y-%m-%d')} 至 {df['date'].max().strftime('%Y-%m-%d')}\n\n"

        if 'scope' in df.columns:
            report += "【二、按范围分类】\n"
            report += "-" * 40 + "\n"
            scope_summary = df.groupby('scope')['emissions'].sum().reset_index()
            scope_summary['占比'] = scope_summary['emissions'] / total_emissions * 100
            for _, row in scope_summary.iterrows():
                report += f"  {row['scope']}: {row['emissions']:,.2f} tCO2e ({row['占比']:.2f}%)\n"
            report += "\n"

        if 'department' in df.columns:
            report += "【三、按部门分类】\n"
            report += "-" * 40 + "\n"
            dept_summary = df.groupby('department')['emissions'].sum().sort_values(ascending=False).reset_index()
            dept_summary['占比'] = dept_summary['emissions'] / total_emissions * 100
            for _, row in dept_summary.iterrows():
                report += f"  {row['department']}: {row['emissions']:,.2f} tCO2e ({row['占比']:.2f}%)\n"
            report += "\n"

        df['month'] = df['date'].dt.strftime('%Y-%m')
        monthly = df.groupby('month')['emissions'].sum().sort_index().reset_index()
        report += "【四、月度排放趋势】\n"
        report += "-" * 40 + "\n"
        for _, row in monthly.iterrows():
            bar_len = int(row['emissions'] / monthly['emissions'].max() * 30)
            bar = "█" * bar_len
            report += f"  {row['month']}: {bar} {row['emissions']:,.2f} tCO2e\n"
        report += "\n"

        reductions = dm.load_reductions()
        if reductions:
            total_reduction = sum(r.reduction_amount for r in reductions)
            report += "【五、减排措施】\n"
            report += "-" * 40 + "\n"
            report += f"  减排措施总数: {len(reductions)} 项\n"
            report += f"  总减排量: {total_reduction:,.2f} tCO2e\n\n"
            for r in sorted(reductions, key=lambda x: x.date)[:5]:
                report += f"  - {r.date} | {r.measure} | {r.reduction_amount:,.2f} tCO2e\n"
            report += "\n"

        report += "=" * 60 + "\n"
        report += "  本报告由 carbon-tool 自动生成\n"
        report += "=" * 60 + "\n"

    return report

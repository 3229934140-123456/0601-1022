import click
import pandas as pd
from tabulate import tabulate
from datetime import datetime
from ..config import Config
from ..logger import CommandLogger
from ..utils import safe_float, format_number


@click.group()
def compare():
    """数据对比与汇总分析"""
    pass


@compare.command('monthly')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--year', '-y', help='指定年份（默认全部）')
@click.option('--by', 'group_by', default='department', help='二级分组: department/scope/category')
@click.pass_context
def monthly_compare(ctx, input_file, year, group_by):
    """月度排放对比"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('compare.monthly', {'input': input_file}, 'failed', '输入文件不存在')
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
            click.echo("⚠️  没有有效的数据")
            return

        df['month'] = df['date'].dt.strftime('%Y-%m')
        monthly = df.groupby('month')['emissions'].sum().reset_index()
        monthly.columns = ['月份', '排放量 (tCO2e)']
        monthly = monthly.sort_values('月份')

        monthly['环比变化'] = monthly['排放量 (tCO2e)'].pct_change() * 100

        click.echo("📊 月度排放对比:")
        table = monthly.values.tolist()
        headers = ['月份', '排放量 (tCO2e)', '环比变化 (%)']
        formatted_table = []
        for row in table:
            month_val, emis_val, pct_val = row
            pct_str = f"{pct_val:.2f}" if pd.notna(pct_val) else '-'
            if pd.notna(pct_val) and pct_val > 0:
                pct_str = f"+{pct_str}% 🔺"
            elif pd.notna(pct_val) and pct_val < 0:
                pct_str = f"{pct_str}% 🔽"
            elif pd.notna(pct_val):
                pct_str = f"{pct_str}%"
            formatted_table.append([month_val, f"{emis_val:,.2f}", pct_str])
        click.echo(tabulate(formatted_table, headers=headers, tablefmt='simple'))

        total = df['emissions'].sum()
        month_count = df['month'].nunique()
        avg_monthly = total / month_count if month_count > 0 else 0
        click.echo(f"\n📊 合计排放: {format_number(total, 2)} tCO2e")
        click.echo(f"   月均排放: {format_number(avg_monthly, 2)} tCO2e")
        click.echo(f"   统计月份: {month_count} 个")

        if group_by and group_by in df.columns:
            group_map = {
                'department': '部门',
                'scope': '范围',
                'category': '类别',
            }
            group_name = group_map.get(group_by, group_by)

            pivot = pd.pivot_table(
                df,
                values='emissions',
                index='month',
                columns=group_by,
                aggfunc='sum',
                fill_value=0
            )
            pivot = pivot.sort_index()

            click.echo(f"\n📊 按{group_name}的月度分布:")
            click.echo(tabulate(pivot.round(2), headers='keys', tablefmt='simple'))

        logger.log('compare.monthly', {'input': input_file, 'year': year}, 'success',
                   f'月度对比，共{month_count}个月')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('compare.monthly', {'input': input_file, 'year': year}, 'failed', str(e))
        ctx.exit(1)


@compare.command('department')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--scope', help='按范围筛选')
@click.pass_context
def department_summary(ctx, input_file, scope):
    """部门排放汇总"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('compare.department', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns or 'department' not in df.columns:
            click.echo("❌ 错误: 数据缺少必要字段")
            ctx.exit(1)

        if scope and 'scope' in df.columns:
            df = df[df['scope'] == scope]

        if df.empty:
            click.echo("⚠️  没有数据")
            return

        dept_summary = df.groupby('department')['emissions'].agg(['sum', 'count']).reset_index()
        dept_summary.columns = ['部门', '排放量 (tCO2e)', '记录数']
        dept_summary = dept_summary.sort_values('排放量 (tCO2e)', ascending=False)

        total = dept_summary['排放量 (tCO2e)'].sum()
        dept_summary['占比 (%)'] = dept_summary['排放量 (tCO2e)'] / total * 100

        click.echo("📊 部门排放汇总:")
        table = []
        for _, row in dept_summary.iterrows():
            table.append([
                row['部门'],
                f"{row['排放量 (tCO2e)']:,.2f}",
                int(row['记录数']),
                f"{row['占比 (%)']:.2f}%"
            ])
        click.echo(tabulate(table, headers=['部门', '排放量 (tCO2e)', '记录数', '占比'], tablefmt='simple'))

        click.echo(f"\n总排放量: {format_number(total, 2)} tCO2e")
        click.echo(f"部门数量: {len(dept_summary)} 个")

        if 'scope' in df.columns:
            pivot = pd.pivot_table(
                df,
                values='emissions',
                index='department',
                columns='scope',
                aggfunc='sum',
                fill_value=0
            )
            pivot = pivot.sort_values(pivot.columns[0], ascending=False)
            click.echo(f"\n📊 各部门分范围排放:")
            click.echo(tabulate(pivot.round(2), headers='keys', tablefmt='simple'))

        logger.log('compare.department', {'input': input_file, 'scope': scope}, 'success',
                   f'部门汇总，共{len(dept_summary)}个部门')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('compare.department', {'input': input_file, 'scope': scope}, 'failed', str(e))
        ctx.exit(1)


@compare.command('period')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--start1', required=True, help='第一期开始日期 YYYY-MM-DD')
@click.option('--end1', required=True, help='第一期结束日期 YYYY-MM-DD')
@click.option('--start2', required=True, help='第二期开始日期 YYYY-MM-DD')
@click.option('--end2', required=True, help='第二期结束日期 YYYY-MM-DD')
@click.pass_context
def period_compare(ctx, input_file, start1, end1, start2, end2):
    """两期排放对比"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('compare.period', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns or 'date' not in df.columns:
            click.echo("❌ 错误: 数据缺少必要字段")
            ctx.exit(1)

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])

        period1 = df[(df['date'] >= start1) & (df['date'] <= end1)]
        period2 = df[(df['date'] >= start2) & (df['date'] <= end2)]

        total1 = period1['emissions'].sum()
        total2 = period2['emissions'].sum()
        diff = total2 - total1
        pct_change = (diff / total1 * 100) if total1 != 0 else 0

        click.echo("📊 两期排放对比:")
        table = [
            ['指标', f'第一期 ({start1} ~ {end1})', f'第二期 ({start2} ~ {end2})', '变化量', '变化率'],
            ['总排放量 (tCO2e)',
             f"{total1:,.2f}",
             f"{total2:,.2f}",
             f"{diff:+,.2f}",
             f"{pct_change:+.2f}%"],
            ['记录数', len(period1), len(period2),
             f"{len(period2) - len(period1):+d}", '-'],
        ]
        click.echo(tabulate(table, headers='firstrow', tablefmt='simple'))

        if 'scope' in df.columns:
            scope1 = period1.groupby('scope')['emissions'].sum()
            scope2 = period2.groupby('scope')['emissions'].sum()
            scope_compare = pd.DataFrame({'第一期': scope1, '第二期': scope2}).fillna(0)
            scope_compare['变化量'] = scope_compare['第二期'] - scope_compare['第一期']
            scope_compare['变化率'] = (
                (scope_compare['第二期'] - scope_compare['第一期']) / scope_compare['第一期'] * 100
            ).fillna(0)

            click.echo(f"\n📊 分范围对比:")
            click.echo(tabulate(scope_compare.round(2), headers='keys', tablefmt='simple'))

        logger.log('compare.period', {
            'input': input_file,
            'start1': start1, 'end1': end1,
            'start2': start2, 'end2': end2
        }, 'success', f'两期对比，变化{pct_change:+.2f}%')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('compare.period', {'input': input_file}, 'failed', str(e))
        ctx.exit(1)

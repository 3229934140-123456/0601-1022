import click
import pandas as pd
from pathlib import Path
from ..config import Config
from ..logger import CommandLogger
from ..data_manager import DataManager
from ..utils import write_csv, write_excel


@click.group()
def export():
    """结果导出与数据输出"""
    pass


@export.command('csv')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入数据文件')
@click.option('--output', '-o', default='emissions_export.csv', help='输出文件名')
@click.option('--scope', help='按范围筛选')
@click.option('--department', help='按部门筛选')
@click.option('--start-date', help='开始日期 YYYY-MM-DD')
@click.option('--end-date', help='结束日期 YYYY-MM-DD')
@click.pass_context
def export_csv(ctx, input_file, output, scope, department, start_date, end_date):
    """导出为 CSV 格式"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

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
        if start_date and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df[df['date'] >= start_date]
        if end_date and 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df[df['date'] <= end_date]

        output_path = config.output_dir / output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo(f"✅ 导出成功")
        click.echo(f"   输出文件: {output_path}")
        click.echo(f"   记录数: {len(df)} 条")
        if 'emissions' in df.columns:
            click.echo(f"   总排放量: {df['emissions'].sum():,.2f} tCO2e")

        logger.log('export.csv', {
            'input': input_file, 'output': output,
            'scope': scope, 'department': department
        }, 'success', f'导出{len(df)}条记录')

    except Exception as e:
        click.echo(f"❌ 导出失败: {e}")
        logger.log('export.csv', {'input': input_file, 'output': output}, 'failed', str(e))
        ctx.exit(1)


@export.command('excel')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入数据文件')
@click.option('--output', '-o', default='emissions_export.xlsx', help='输出文件名')
@click.option('--summary/--no-summary', default=True, help='是否包含汇总sheet')
@click.pass_context
def export_excel(ctx, input_file, output, summary):
    """导出为 Excel 格式（多sheet）"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

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
        sheets = {'排放明细': df}

        if summary and 'emissions' in df.columns:
            if 'scope' in df.columns:
                scope_summary = df.groupby('scope')['emissions'].sum().reset_index()
                scope_summary.columns = ['范围', '排放量 (tCO2e)']
                sheets['按范围汇总'] = scope_summary

            if 'department' in df.columns:
                dept_summary = df.groupby('department')['emissions'].sum().sort_values(
                    ascending=False).reset_index()
                dept_summary.columns = ['部门', '排放量 (tCO2e)']
                sheets['按部门汇总'] = dept_summary

            if 'category' in df.columns:
                cat_summary = df.groupby('category')['emissions'].sum().sort_values(
                    ascending=False).reset_index()
                cat_summary.columns = ['类别', '排放量 (tCO2e)']
                sheets['按类别汇总'] = cat_summary

            if 'date' in df.columns:
                df_dt = df.copy()
                df_dt['date'] = pd.to_datetime(df_dt['date'], errors='coerce')
                df_dt = df_dt.dropna(subset=['date'])
                df_dt['月份'] = df_dt['date'].dt.strftime('%Y-%m')
                monthly = df_dt.groupby('月份')['emissions'].sum().reset_index()
                monthly.columns = ['月份', '排放量 (tCO2e)']
                sheets['月度汇总'] = monthly

            factors_dict = dm.load_factors()
            if factors_dict:
                factors_list = []
                for name, ef in factors_dict.items():
                    factors_list.append({
                        '因子名称': ef.name,
                        '因子值': ef.factor,
                        '单位': ef.unit,
                        '范围': ef.scope,
                        '类别': ef.category,
                        '描述': ef.description
                    })
                factors_df = pd.DataFrame(factors_list)
                sheets['排放因子'] = factors_df

        output_path = config.output_dir / output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for sheet_name, sheet_df in sheets.items():
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

        click.echo(f"✅ Excel 导出成功")
        click.echo(f"   输出文件: {output_path}")
        click.echo(f"   工作表数: {len(sheets)} 个")
        click.echo(f"   包含: {', '.join(sheets.keys())}")

        logger.log('export.excel', {
            'input': input_file, 'output': output, 'sheets': list(sheets.keys())
        }, 'success', f'导出Excel，{len(sheets)}个工作表')

    except Exception as e:
        click.echo(f"❌ 导出失败: {e}")
        logger.log('export.excel', {'input': input_file, 'output': output}, 'failed', str(e))
        ctx.exit(1)


@export.command('factors')
@click.option('--output', '-o', default='factors_export.csv', help='输出文件名')
@click.pass_context
def export_factors(ctx, output):
    """导出排放因子库"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        factors = dm.load_factors()
        if not factors:
            click.echo("⚠️  没有排放因子可导出")
            return

        data = []
        for name, ef in factors.items():
            data.append({
                'name': ef.name,
                'factor': ef.factor,
                'unit': ef.unit,
                'scope': ef.scope,
                'category': ef.category,
                'description': ef.description
            })

        df = pd.DataFrame(data)
        output_path = config.output_dir / output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo(f"✅ 排放因子导出成功")
        click.echo(f"   输出文件: {output_path}")
        click.echo(f"   因子数量: {len(factors)} 个")

        logger.log('export.factors', {'output': output}, 'success',
                   f'导出{len(factors)}个排放因子')

    except Exception as e:
        click.echo(f"❌ 导出失败: {e}")
        logger.log('export.factors', {'output': output}, 'failed', str(e))
        ctx.exit(1)


@export.command('template')
@click.option('--output', '-o', default='import_template.csv', help='模板文件名')
@click.option('--format', '-f', 'fmt', default='csv', type=click.Choice(['csv', 'xlsx']),
              help='模板格式')
@click.pass_context
def export_template(ctx, output, fmt):
    """导出入数据模板"""
    config = Config()
    logger = CommandLogger(config.logs_dir)
    dm = DataManager(config)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        columns = [
            '日期', '部门', '能源类型', '活动数据', '单位',
            '排放因子', '产品', '备注'
        ]
        sample_data = [
            ['2024-01-15', '生产部', '电力-华东电网', 1000, 'kWh', 0.5810, '产品A', '一月份用电'],
            ['2024-01-20', '行政部', '天然气', 500, 'm³', 0.0021622, '', '办公采暖'],
        ]

        df = pd.DataFrame(sample_data, columns=columns)
        output_path = config.output_dir / output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == 'xlsx':
            if not output.endswith('.xlsx'):
                output_path = config.output_dir / (output + '.xlsx')
            df.to_excel(output_path, index=False, engine='openpyxl')
        else:
            df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo(f"✅ 数据模板导出成功")
        click.echo(f"   输出文件: {output_path}")
        click.echo(f"   格式: {fmt}")
        click.echo(f"   包含 {len(columns)} 个字段，附示例数据")

        logger.log('export.template', {'output': output, 'format': fmt}, 'success',
                   '导出数据模板')

    except Exception as e:
        click.echo(f"❌ 导出失败: {e}")
        logger.log('export.template', {'output': output, 'format': fmt}, 'failed', str(e))
        ctx.exit(1)

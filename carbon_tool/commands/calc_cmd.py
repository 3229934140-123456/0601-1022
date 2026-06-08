import click
import pandas as pd
import uuid
import math
from tabulate import tabulate
from ..utils import safe_float, format_number


@click.group()
def calc():
    """排放计算与范围分类"""
    pass


UNIT_CONVERSIONS = {
    'electricity': {
        'kWh': {'MWh': 0.001, 'kWh': 1.0},
        'MWh': {'kWh': 1000.0, 'MWh': 1.0},
    },
    'volume': {
        'm³': {'万m³': 0.0001, 'm³': 1.0, 'L': 1000.0},
        '万m³': {'m³': 10000.0, '万m³': 1.0},
        'L': {'m³': 0.001, '万m³': 0.0000001, 'L': 1.0},
    },
    'mass': {
        'kg': {'t': 0.001, 'kg': 1.0, 'g': 1000.0},
        't': {'kg': 1000.0, 't': 1.0},
        'g': {'kg': 0.001, 't': 0.000001, 'g': 1.0},
    },
}

CATEGORY_UNIT_MAP = {
    '外购电力': 'electricity',
    '固定燃烧': 'volume',
    '移动燃烧': 'volume',
    '过程排放': 'mass',
}


def _get_unit_category(unit):
    unit = str(unit).strip().lower()
    for cat, units in UNIT_CONVERSIONS.items():
        for u in units:
            if u.lower() == unit:
                return cat
    return None


def _convert_unit(value, from_unit, to_unit):
    from_unit = str(from_unit).strip()
    to_unit = str(to_unit).strip()
    if from_unit == to_unit:
        return value, ''
    cat = _get_unit_category(from_unit)
    if not cat:
        return value, ''
    cat_units = UNIT_CONVERSIONS.get(cat, {})
    if from_unit not in cat_units or to_unit not in cat_units[from_unit]:
        return value, ''
    factor = cat_units[from_unit][to_unit]
    converted = value * factor
    note = f"{value:g} {from_unit} = {converted:g} {to_unit}"
    return converted, note


def _extract_factor_unit(unit_str):
    if not unit_str:
        return '', ''
    unit_str = str(unit_str)
    if '/' in unit_str:
        parts = unit_str.split('/')
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
    return unit_str.strip(), ''


@calc.command('run')
@click.option('--input', '-i', 'input_file', default='emissions_mapped.csv', help='输入文件名')
@click.option('--output', '-o', default='emissions_calculated.csv', help='输出文件名')
@click.option('--summary', '-s', is_flag=True, help='显示汇总信息')
@click.option('--unit-check/--no-unit-check', default=True, help='是否启用单位自动换算')
@click.pass_context
def run_calc(ctx, input_file, output, summary, unit_check):
    """批量计算排放量（支持单位自动换算）"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('calc.run', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        factors = dm.load_factors()

        total_rows = len(df)
        calculated = 0
        missing_factor = 0
        missing_activity = 0
        unit_converted = 0
        missing_records = []

        if 'id' not in df.columns:
            df['id'] = [str(uuid.uuid4())[:8] for _ in range(len(df))]
        if 'emissions' not in df.columns:
            df['emissions'] = 0.0
        if 'emissions_unit' not in df.columns:
            df['emissions_unit'] = 'tCO2e'
        if 'scope' not in df.columns:
            df['scope'] = ''
        if 'category' not in df.columns:
            df['category'] = ''
        if 'factor_unit' not in df.columns:
            df['factor_unit'] = ''
        if 'original_activity_data' not in df.columns:
            df['original_activity_data'] = ''
        if 'original_activity_unit' not in df.columns:
            df['original_activity_unit'] = ''
        if 'conversion_note' not in df.columns:
            df['conversion_note'] = ''

        for idx, row in df.iterrows():
            source_type = str(row.get('source_type', '')).strip()
            activity_data = safe_float(row.get('activity_data', 0))
            activity_unit = str(row.get('activity_unit', '')).strip()
            emission_factor = safe_float(row.get('emission_factor', 0))

            if activity_data == 0:
                missing_activity += 1
                missing_records.append({
                    '行号': idx + 2,
                    '原因': '缺少活动数据',
                    '部门': row.get('department', ''),
                    '能源类型': source_type,
                })
                continue

            ef_obj = None
            if emission_factor == 0 and source_type:
                ef_obj = factors.get(source_type)
                if ef_obj:
                    emission_factor = ef_obj.factor
                    df.at[idx, 'emission_factor'] = ef_obj.factor
                    df.at[idx, 'factor_unit'] = ef_obj.unit
                    df.at[idx, 'scope'] = ef_obj.scope
                    df.at[idx, 'category'] = ef_obj.category
                else:
                    missing_factor += 1
                    missing_records.append({
                        '行号': idx + 2,
                        '原因': '未找到排放因子',
                        '部门': row.get('department', ''),
                        '能源类型': source_type,
                    })
                    continue
            elif emission_factor > 0 and source_type and not row.get('scope'):
                ef_obj = factors.get(source_type)
                if ef_obj:
                    df.at[idx, 'scope'] = ef_obj.scope
                    df.at[idx, 'category'] = ef_obj.category
                    df.at[idx, 'factor_unit'] = ef_obj.unit

            conv_note = ''
            original_data = activity_data
            original_unit = activity_unit

            if unit_check and ef_obj and activity_unit:
                factor_emission_unit, factor_activity_unit = _extract_factor_unit(ef_obj.unit)
                if factor_activity_unit and activity_unit != factor_activity_unit:
                    converted_data, note = _convert_unit(
                        activity_data, activity_unit, factor_activity_unit
                    )
                    if note:
                        activity_data = converted_data
                        conv_note = note
                        unit_converted += 1
                        df.at[idx, 'original_activity_data'] = original_data
                        df.at[idx, 'original_activity_unit'] = original_unit
                        df.at[idx, 'conversion_note'] = note
                        df.at[idx, 'activity_data'] = converted_data
                        df.at[idx, 'activity_unit'] = factor_activity_unit

            emissions = activity_data * emission_factor
            df.at[idx, 'emissions'] = emissions
            calculated += 1

        output_path = config.data_dir / output
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo(f"✅ 计算完成")
        click.echo(f"   总记录数: {total_rows}")
        click.echo(f"   成功计算: {calculated} 条")
        click.echo(f"   单位换算: {unit_converted} 条")
        click.echo(f"   缺少活动数据: {missing_activity} 条")
        click.echo(f"   缺少排放因子: {missing_factor} 条")

        if missing_records:
            click.echo(f"\n⚠️  缺失值提示 ({len(missing_records)} 条):")
            table = []
            for r in missing_records[:20]:
                table.append([r['行号'], r['原因'], r['部门'], r['能源类型']])
            click.echo(tabulate(table, headers=['行号', '原因', '部门', '能源类型'], tablefmt='simple'))
            if len(missing_records) > 20:
                click.echo(f"   ... 还有 {len(missing_records) - 20} 条未显示")

        if summary:
            _print_summary(df)

        total_emissions = df['emissions'].sum()
        logger.log('calc.run', {'input': input_file, 'output': output}, 'success',
                   f'计算{calculated}条记录，总排放量{format_number(total_emissions, 2)} tCO2e',
                   details={
                       'total_rows': total_rows,
                       'calculated': calculated,
                       'unit_converted': unit_converted,
                       'missing_activity': missing_activity,
                       'missing_factor': missing_factor,
                       'total_emissions': total_emissions
                   })

    except Exception as e:
        click.echo(f"❌ 计算失败: {e}")
        import traceback
        traceback.print_exc()
        logger.log('calc.run', {'input': input_file, 'output': output}, 'failed', str(e))
        ctx.exit(1)


@calc.command('summary')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--by', 'group_by', default='scope', help='按字段汇总: scope/department/category/source_type')
@click.pass_context
def summary(ctx, input_file, group_by):
    """查看排放汇总"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('calc.summary', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        _print_summary(df, group_by)
        logger.log('calc.summary', {'input': input_file, 'group_by': group_by}, 'success', '查看排放汇总')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('calc.summary', {'input': input_file, 'group_by': group_by}, 'failed', str(e))
        ctx.exit(1)


@calc.command('scope')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--set', 'set_scope', nargs=2, multiple=True, help='设置范围: 能源类型 范围')
@click.pass_context
def scope_classify(ctx, input_file, set_scope):
    """范围分类管理"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('calc.scope', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        if set_scope:
            factors = dm.load_factors()
            for source_type, scope in set_scope:
                if source_type in factors:
                    factors[source_type].scope = scope
                    click.echo(f"✅ {source_type}: 范围设置为 {scope}")
                else:
                    click.echo(f"⚠️  {source_type}: 排放因子不存在")
            dm.save_factors(factors)

            df = pd.read_csv(input_path, encoding='utf-8-sig')
            factors = dm.load_factors()
            for idx, row in df.iterrows():
                st = str(row.get('source_type', '')).strip()
                if st in factors:
                    df.at[idx, 'scope'] = factors[st].scope
                    df.at[idx, 'category'] = factors[st].category
            df.to_csv(input_path, index=False, encoding='utf-8-sig')

            logger.log('calc.scope', {'action': 'set', 'count': len(set_scope)}, 'success',
                       f'设置{len(set_scope)}个排放源的范围')
            return

        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'scope' not in df.columns:
            click.echo("⚠️  数据中没有 scope 字段，请先运行 'carbon-tool calc run'")
            ctx.exit(1)

        scope_summary = df.groupby('scope', dropna=False)['emissions'].sum().reset_index()
        scope_summary.columns = ['范围', '排放量 (tCO2e)']
        scope_summary = scope_summary.sort_values('排放量 (tCO2e)', ascending=False)

        click.echo("📊 按范围分类:")
        click.echo(tabulate(scope_summary, headers='keys', tablefmt='simple',
                            floatfmt='.2f', showindex=False))

        total = df['emissions'].sum()
        click.echo(f"\n总排放量: {format_number(total, 2)} tCO2e")

        logger.log('calc.scope', {'action': 'list'}, 'success', '查看范围分类')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('calc.scope', {'action': 'unknown'}, 'failed', str(e))
        ctx.exit(1)


def _print_summary(df, group_by='scope'):
    """打印汇总信息"""
    if 'emissions' not in df.columns:
        click.echo("⚠️  数据中没有排放量字段，请先运行 'carbon-tool calc run'")
        return

    total = df['emissions'].sum()

    group_names = {
        'scope': '范围',
        'department': '部门',
        'category': '类别',
        'source_type': '能源类型',
    }
    group_name = group_names.get(group_by, group_by)

    if group_by in df.columns:
        summary = df.groupby(group_by, dropna=False)['emissions'].sum().reset_index()
        summary.columns = [group_name, '排放量 (tCO2e)']
        summary = summary.sort_values('排放量 (tCO2e)', ascending=False)
        summary['占比 (%)'] = summary['排放量 (tCO2e)'] / total * 100

        click.echo(f"\n📊 按{group_name}汇总:")
        click.echo(tabulate(summary, headers='keys', tablefmt='simple',
                            floatfmt='.2f', showindex=False))

    click.echo(f"\n📊 总排放量: {format_number(total, 2)} tCO2e")
    click.echo(f"   记录数: {len(df)} 条")

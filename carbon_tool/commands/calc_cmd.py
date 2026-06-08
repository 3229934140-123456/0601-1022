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
@click.option('--tag', '-t', 'tags', multiple=True, help='因子标签筛选，格式 key=value（可重复）')
@click.option('--region', help='排放因子地区（优先于预设）')
@click.option('--year', help='排放因子年份（优先于预设）')
@click.option('--scenario', help='排放因子情景（优先于预设）')
@click.option('--gaps-output', 'gaps_output', help='缺口清单输出文件名')
@click.option('--factor-mode', default='strict', type=click.Choice(['strict', 'best', 'first']),
              help='多因子匹配策略: strict=严格匹配(缺则报错), best=最优匹配, first=第一个')
@click.pass_context
def run_calc(ctx, input_file, output, summary, unit_check, tags,
             region, year, scenario, gaps_output, factor_mode):
    """批量计算排放量（支持单位自动换算、手填因子、多候选因子筛选）"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']
    audit = ctx.obj['audit']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('calc.run', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    defaults = config.get('defaults', {}) or {}
    tag_dict = {}
    if tags:
        for t in tags:
            if '=' in t:
                k, v = t.split('=', 1)
                tag_dict[k.strip()] = v.strip()

    eff_region = region if region is not None else defaults.get('region', '')
    eff_year = year if year is not None else str(defaults.get('year', ''))
    eff_scenario = scenario if scenario is not None else defaults.get('scenario', '')

    if eff_region:
        tag_dict['region'] = eff_region
    if eff_year:
        tag_dict['year'] = str(eff_year)
    if eff_scenario:
        tag_dict['scenario'] = eff_scenario

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')

        total_rows = len(df)
        calculated = 0
        missing_factor = 0
        missing_activity = 0
        unit_converted = 0
        manual_factor = 0
        factor_library = 0
        unit_mismatch = 0
        gap_records = []

        if 'id' not in df.columns:
            df['id'] = [str(uuid.uuid4())[:8] for _ in range(len(df))]
        for col in ['emissions', 'emission_factor', 'activity_data']:
            if col not in df.columns:
                df[col] = 0.0
        for col in ['emissions_unit', 'scope', 'category', 'factor_unit',
                    'activity_unit', 'original_activity_data',
                    'original_activity_unit', 'conversion_note', 'factor_source',
                    'calc_status']:
            if col not in df.columns:
                df[col] = ''
        df['emissions_unit'] = 'tCO2e'
        df['activity_data'] = pd.to_numeric(df['activity_data'], errors='coerce').astype(float).fillna(0.0)
        df['emissions'] = pd.to_numeric(df['emissions'], errors='coerce').astype(float).fillna(0.0)
        df['emission_factor'] = pd.to_numeric(df['emission_factor'], errors='coerce').astype(float).fillna(0.0)
        df['original_activity_data'] = pd.to_numeric(df.get('original_activity_data', ''), 
                                                     errors='coerce').astype(float).fillna(0.0)
        df['activity_unit'] = df['activity_unit'].astype(str).replace('nan', '').fillna('')
        df['factor_unit'] = df['factor_unit'].astype(str).replace('nan', '').fillna('')

        factors_all = dm.load_factors()

        for idx, row in df.iterrows():
            source_type = str(row.get('source_type', '')).strip()
            activity_data = safe_float(row.get('activity_data', 0))
            activity_unit = str(row.get('activity_unit', '')).strip()
            manual_ef = safe_float(row.get('emission_factor', 0))
            manual_fu = str(row.get('factor_unit', '')).strip()
            exist_status = str(row.get('calc_status', '')).strip()

            original_data = activity_data
            original_unit = activity_unit
            ef_value = 0.0
            fu_value = ''
            ef_scope = ''
            ef_category = ''
            ef_source = ''
            conv_note = ''
            calc_status = '未计算'

            if activity_data == 0:
                missing_activity += 1
                gap_records.append(_make_gap_record(
                    idx, row, '缺少活动数据', source_type, activity_unit
                ))
                df.at[idx, 'calc_status'] = '未计算-无活动数据'
                continue

            if manual_ef > 0 and manual_fu:
                ef_value = manual_ef
                fu_value = manual_fu
                ef_source = '手填'
                manual_factor += 1
            elif source_type:
                candidates = dm.find_factors(source_type, tag_dict)
                if not candidates and source_type in factors_all:
                    candidates = [factors_all[source_type]]

                if candidates:
                    if factor_mode == 'strict' and tag_dict:
                        perfect_match = False
                        for c in candidates:
                            if all(c.tags.get(k) == str(v) for k, v in tag_dict.items()):
                                ef_obj = c
                                perfect_match = True
                                break
                        if not perfect_match:
                            missing_factor += 1
                            gap_records.append(_make_gap_record(
                                idx, row, '无严格匹配的因子', source_type, activity_unit,
                                f'期望标签: {tag_dict}'
                            ))
                            df.at[idx, 'calc_status'] = '未计算-缺因子'
                            continue
                    else:
                        ef_obj = candidates[0]

                    ef_value = ef_obj.factor
                    fu_value = ef_obj.unit
                    ef_scope = ef_obj.scope
                    ef_category = ef_obj.category
                    ef_source = f'因子库({ef_obj.name})'
                    factor_library += 1
                else:
                    missing_factor += 1
                    gap_records.append(_make_gap_record(
                        idx, row, '未找到排放因子', source_type, activity_unit
                    ))
                    df.at[idx, 'calc_status'] = '未计算-缺因子'
                    continue
            else:
                missing_factor += 1
                gap_records.append(_make_gap_record(
                    idx, row, '缺少能源类型和因子', source_type, activity_unit
                ))
                df.at[idx, 'calc_status'] = '未计算-缺因子'
                continue

            converted_ok = True
            if unit_check and activity_unit and fu_value:
                factor_emission_unit, factor_activity_unit = _extract_factor_unit(fu_value)
                if factor_activity_unit and activity_unit and activity_unit != factor_activity_unit:
                    converted_data, note = _convert_unit(
                        activity_data, activity_unit, factor_activity_unit
                    )
                    if note and '=' in note:
                        activity_data = converted_data
                        conv_note = note
                        unit_converted += 1
                    else:
                        converted_ok = False
                        unit_mismatch += 1
                        conv_note = f'单位无法换算: {activity_unit} → {factor_activity_unit}'
                        gap_records.append(_make_gap_record(
                            idx, row, '单位不匹配且无法换算', source_type, activity_unit,
                            f'因子单位: {fu_value}'
                        ))

            if not converted_ok:
                df.at[idx, 'calc_status'] = '未计算-单位不匹配'
                df.at[idx, 'emission_factor'] = ef_value
                df.at[idx, 'factor_unit'] = fu_value
                df.at[idx, 'factor_source'] = ef_source
                df.at[idx, 'conversion_note'] = conv_note
                df.at[idx, 'original_activity_data'] = original_data
                df.at[idx, 'original_activity_unit'] = original_unit
                df.at[idx, 'emissions'] = 0.0
                continue

            emissions = activity_data * ef_value
            calc_status = '已计算'

            df.at[idx, 'emission_factor'] = ef_value
            df.at[idx, 'factor_unit'] = fu_value
            df.at[idx, 'factor_source'] = ef_source
            if ef_scope:
                df.at[idx, 'scope'] = ef_scope
            if ef_category:
                df.at[idx, 'category'] = ef_category
            df.at[idx, 'original_activity_data'] = original_data
            df.at[idx, 'original_activity_unit'] = original_unit
            df.at[idx, 'conversion_note'] = conv_note
            df.at[idx, 'activity_data'] = activity_data
            df.at[idx, 'activity_unit'] = factor_activity_unit if conv_note else activity_unit
            df.at[idx, 'emissions'] = emissions
            df.at[idx, 'calc_status'] = calc_status
            calculated += 1

        output_path = config.data_dir / output
        df.to_csv(output_path, index=False, encoding='utf-8-sig')

        click.echo(f"✅ 计算完成")
        click.echo(f"   总记录数:     {total_rows}")
        click.echo(f"   已计算:       {calculated} 条")
        click.echo(f"     ├─ 因子库匹配: {factor_library} 条")
        click.echo(f"     └─ 手填因子: {manual_factor} 条")
        click.echo(f"   单位换算:     {unit_converted} 条")
        click.echo(f"   未计算:       {total_rows - calculated} 条")
        click.echo(f"     ├─ 缺少活动数据: {missing_activity} 条")
        click.echo(f"     ├─ 缺少排放因子: {missing_factor} 条")
        click.echo(f"     └─ 单位不匹配: {unit_mismatch} 条")

        if gap_records:
            _print_gap_summary(gap_records, tag_dict)

        if gaps_output and gap_records:
            gaps_path = config.data_dir / gaps_output
            pd.DataFrame(gap_records).to_csv(gaps_path, index=False, encoding='utf-8-sig')
            click.echo(f"\n💾 缺口清单已保存到: {gaps_path}")

        if summary:
            _print_summary(df[df['calc_status'] == '已计算'] if 'calc_status' in df.columns else df)

        total_emissions = df['emissions'].sum() if calculated > 0 else 0
        calc_emissions = df[df['calc_status'] == '已计算']['emissions'].sum() if 'calc_status' in df.columns else total_emissions

        logger.log('calc.run', {'input': input_file, 'output': output}, 'success',
                   f'计算{calculated}条记录，总排放量{format_number(calc_emissions, 2)} tCO2e',
                   details={
                       'total_rows': total_rows,
                       'calculated': calculated,
                       'factor_library': factor_library,
                       'manual_factor': manual_factor,
                       'unit_converted': unit_converted,
                       'missing_activity': missing_activity,
                       'missing_factor': missing_factor,
                       'unit_mismatch': unit_mismatch,
                       'total_emissions': calc_emissions,
                       'tags': tag_dict,
                       'factor_mode': factor_mode,
                   })

        audit.record(
            command='calc.run',
            input_files=[str(input_path)],
            output_file=str(output_path),
            row_count=calculated,
            total_emissions=calc_emissions,
            parameters={
                'input': input_file,
                'output': output,
                'unit_check': unit_check,
                'tags': tag_dict,
                'factor_mode': factor_mode,
                'total_rows': total_rows,
                'calculated_rows': calculated,
            },
            status='success',
            message=f'计算{calculated}条（共{total_rows}条），总排放{format_number(calc_emissions, 2)} tCO2e',
        )

    except Exception as e:
        click.echo(f"❌ 计算失败: {e}")
        import traceback
        traceback.print_exc()
        logger.log('calc.run', {'input': input_file, 'output': output}, 'failed', str(e))
        ctx.exit(1)


def _print_gap_summary(gap_records, tag_dict):
    """打印缺口分类汇总"""
    click.echo(f"\n📋 缺口明细 ({len(gap_records)} 条):")

    reasons = {}
    for r in gap_records:
        reason = r.get('原因', '未知')
        if reason not in reasons:
            reasons[reason] = []
        reasons[reason].append(r)

    for reason, items in reasons.items():
        click.echo(f"\n  ▸ {reason}: {len(items)} 条")
        by_source = {}
        for r in items:
            st = r.get('能源类型', '未知') or '未知'
            if st not in by_source:
                by_source[st] = 0
            by_source[st] += 1
        for st, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
            click.echo(f"    • {st}: {cnt} 条")

    if tag_dict:
        tag_str = ', '.join(f"{k}={v}" for k, v in tag_dict.items())
        click.echo(f"\n💡 当前筛选标签: {tag_str}")
        click.echo("   可用 --region/--year/--scenario 调整，或 --factor-mode best 放宽匹配")

    show_count = min(10, len(gap_records))
    click.echo(f"\n  前 {show_count} 条详情:")
    table = []
    for r in gap_records[:show_count]:
        table.append([
            r['行号'],
            r.get('来源文件', '')[:15],
            r.get('能源类型', ''),
            r.get('活动单位', ''),
            r.get('原因', ''),
            r.get('备注', '')[:25],
        ])
    click.echo(tabulate(
        table,
        headers=['行号', '来源文件', '能源类型', '活动单位', '原因', '备注'],
        tablefmt='simple'
    ))
    if len(gap_records) > show_count:
        click.echo(f"  ... 还有 {len(gap_records) - show_count} 条，可用 --gaps-output 导出全部")


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


def _make_gap_record(idx, row, reason, source_type, activity_unit, extra=''):
    """生成缺口记录"""
    rec = {
        '行号': idx + 2,
        '来源文件': str(row.get('source_file', '')),
        '来源工作表': str(row.get('source_sheet', '')),
        '原始行号': row.get('source_row', ''),
        '部门': row.get('department', ''),
        '能源类型': source_type,
        '活动单位': activity_unit,
        '原因': reason,
        '备注': extra,
    }
    return rec

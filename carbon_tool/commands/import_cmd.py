import click
import pandas as pd
from pathlib import Path
from tabulate import tabulate
from ..models import FieldMapping
from ..utils import read_file, safe_float


@click.group()
def import_cmd():
    """数据导入与字段映射管理"""
    pass


@import_cmd.command('file')
@click.argument('file_path')
@click.option('--sheet', '-s', default=0, help='Excel工作表名称或索引（0=第一个）')
@click.option('--output', '-o', default='emissions_raw.csv', help='输出文件名')
@click.option('--preview', '-p', is_flag=True, help='仅预览前10行数据，不保存')
@click.option('--list-sheets', '-ls', is_flag=True, help='列出Excel文件的所有工作表')
@click.option('--append', '-a', is_flag=True, help='追加到已有数据（保留原始数据）')
@click.option('--no-source', is_flag=True, help='不添加来源追踪列')
@click.pass_context
def import_file(ctx, file_path, sheet, output, preview, list_sheets, append, no_source):
    """从CSV/Excel文件导入排放数据

    文件查找顺序: 当前目录 → 项目 data 目录
    """
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    resolved_path = _resolve_file_path(file_path, config.data_dir)
    if not resolved_path:
        click.echo(f"❌ 错误: 找不到文件 '{file_path}'")
        click.echo(f"   已查找: 当前目录、{config.data_dir}")
        logger.log('import', {'file': str(file_path)}, 'failed', '文件不存在')
        ctx.exit(1)

    file_path = resolved_path
    file_name = file_path.name

    try:
        suffix = file_path.suffix.lower()

        if list_sheets and suffix in ['.xlsx', '.xls']:
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')
            click.echo(f"📋 工作表列表 (共 {len(excel_file.sheet_names)} 个):")
            for i, name in enumerate(excel_file.sheet_names):
                click.echo(f"   [{i}] {name}")
            logger.log('import', {'file': str(file_path), 'action': 'list_sheets'},
                       'success', f'列出{len(excel_file.sheet_names)}个工作表')
            return

        sheet_param = sheet
        sheet_name_display = ''
        if isinstance(sheet, str) and sheet.isdigit():
            sheet_param = int(sheet)

        df = read_file(file_path, sheet_param)

        if isinstance(sheet_param, int) and suffix in ['.xlsx', '.xls']:
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')
            if 0 <= sheet_param < len(excel_file.sheet_names):
                sheet_name_display = excel_file.sheet_names[sheet_param]
        elif isinstance(sheet_param, str):
            sheet_name_display = sheet_param
        elif suffix in ['.xlsx', '.xls']:
            excel_file = pd.ExcelFile(file_path, engine='openpyxl')
            if excel_file.sheet_names:
                sheet_name_display = excel_file.sheet_names[0]

        click.echo(f"✅ 成功读取文件: {file_path}")
        if sheet_name_display:
            click.echo(f"   工作表: {sheet_name_display}")
        click.echo(f"   数据行数: {len(df)}")
        click.echo(f"   列数: {len(df.columns)}")
        click.echo(f"   列名: {', '.join(df.columns.tolist())}")

        if preview:
            click.echo("\n📋 数据预览 (前10行):")
            click.echo(tabulate(df.head(10), headers='keys', tablefmt='simple', showindex=False))

        mappings = dm.load_mapping()
        if mappings:
            matched = []
            suggestions = []
            target_fields = {m.target_field: m.source_field for m in mappings}
            for col in df.columns:
                if col in target_fields.values():
                    matched.append(col)
            if matched:
                click.echo(f"\n💡 字段映射匹配: 已匹配 {len(matched)} 个字段")
            else:
                click.echo(f"\n💡 建议字段映射:")
                for m in mappings:
                    suggestions.append([m.source_field, m.target_field, m.data_type,
                                        "是" if m.required else "否"])
                click.echo(tabulate(suggestions,
                                    headers=['源字段（模板）', '目标字段', '类型', '必填'],
                                    tablefmt='simple'))

        if preview:
            logger.log('import', {'file': str(file_path), 'action': 'preview'}, 'success',
                       f'预览{len(df)}行数据')
            return

        if not no_source:
            df.insert(0, 'source_file', file_name)
            df.insert(1, 'source_sheet', sheet_name_display if sheet_name_display else '')
            df.insert(2, 'source_row', range(2, len(df) + 2))

        output_path = config.data_dir / output
        existing_rows = 0

        if append and output_path.exists():
            existing_df = pd.read_csv(output_path, encoding='utf-8-sig')
            existing_rows = len(existing_df)
            df = pd.concat([existing_df, df], ignore_index=True)
            click.echo(f"\n🔗 追加模式: 已有 {existing_rows} 条，新增 {len(df) - existing_rows} 条")

        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        click.echo(f"\n💾 数据已保存到: {output_path}")
        click.echo(f"   总计 {len(df)} 条记录")
        if not no_source:
            click.echo(f"   已添加来源追踪列: source_file, source_sheet, source_row")
        click.echo("\n💡 提示: 运行 'carbon-tool import map -l' 查看字段映射")
        click.echo("   运行 'carbon-tool import apply' 应用字段映射后进行计算")

        logger.log('import', {
            'file': str(file_path),
            'output': str(output_path),
            'rows': len(df),
            'append': append,
            'sheet': sheet_name_display,
        }, 'success', f'导入{len(df) - existing_rows if append else len(df)}行数据')

    except Exception as e:
        click.echo(f"❌ 导入失败: {e}")
        logger.log('import', {'file': str(file_path)}, 'failed', str(e))
        ctx.exit(1)


@import_cmd.command('map')
@click.option('--list', '-l', 'list_mapping', is_flag=True, help='列出当前字段映射')
@click.option('--set', '-s', 'set_pair', nargs=2, multiple=True, help='设置字段映射: 源字段 目标字段')
@click.option('--remove', '-r', help='移除字段映射（源字段名）')
@click.option('--reset', is_flag=True, help='重置为默认映射')
@click.pass_context
def field_map(ctx, list_mapping, set_pair, remove, reset):
    """管理字段映射关系"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        if reset:
            default_mapping = [
                FieldMapping(source_field='日期', target_field='date', data_type='date', required=True),
                FieldMapping(source_field='部门', target_field='department', data_type='string', required=True),
                FieldMapping(source_field='能源类型', target_field='source_type', data_type='string', required=True),
                FieldMapping(source_field='活动数据', target_field='activity_data', data_type='float', required=True),
                FieldMapping(source_field='单位', target_field='activity_unit', data_type='string', required=False),
                FieldMapping(source_field='排放因子', target_field='emission_factor', data_type='float', required=False),
                FieldMapping(source_field='产品', target_field='product', data_type='string', required=False),
                FieldMapping(source_field='备注', target_field='remarks', data_type='string', required=False),
            ]
            dm.save_mapping(default_mapping)
            click.echo("✅ 字段映射已重置为默认值")
            logger.log('import.map', {'action': 'reset'}, 'success', '重置字段映射')
            return

        if remove:
            mappings = dm.load_mapping()
            new_mappings = [m for m in mappings if m.source_field != remove]
            if len(new_mappings) == len(mappings):
                click.echo(f"⚠️  未找到映射: {remove}")
            else:
                dm.save_mapping(new_mappings)
                click.echo(f"✅ 已移除映射: {remove}")
                logger.log('import.map', {'action': 'remove', 'field': remove}, 'success', '移除字段映射')
            return

        if set_pair:
            mappings = dm.load_mapping()
            mapping_dict = {m.source_field: m for m in mappings}
            for source, target in set_pair:
                if source in mapping_dict:
                    mapping_dict[source].target_field = target
                    click.echo(f"🔄 更新映射: {source} → {target}")
                else:
                    mapping_dict[source] = FieldMapping(
                        source_field=source,
                        target_field=target,
                        data_type='string',
                        required=False
                    )
                    click.echo(f"➕ 新增映射: {source} → {target}")
            dm.save_mapping(list(mapping_dict.values()))
            logger.log('import.map', {'action': 'set', 'pairs': len(set_pair)}, 'success', '设置字段映射')
            return

        if list_mapping:
            mappings = dm.load_mapping()
            if not mappings:
                click.echo("📋 当前没有字段映射配置")
            else:
                click.echo("📋 当前字段映射:")
                table = []
                for m in mappings:
                    table.append([
                        m.source_field,
                        m.target_field,
                        m.data_type,
                        "是" if m.required else "否"
                    ])
                click.echo(tabulate(table, headers=['源字段', '目标字段', '数据类型', '必填'], tablefmt='simple'))
            return

        click.echo(ctx.get_help())

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('import.map', {'action': 'unknown'}, 'failed', str(e))
        ctx.exit(1)


@import_cmd.command('apply')
@click.option('--input', '-i', 'input_file', default='emissions_raw.csv', help='输入文件名')
@click.option('--output', '-o', default='emissions_mapped.csv', help='输出文件名')
@click.pass_context
def apply_mapping(ctx, input_file, output):
    """应用字段映射到数据"""
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
        logger.log('import.apply', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        mappings = dm.load_mapping()

        if not mappings:
            click.echo("❌ 错误: 没有配置字段映射，请先运行 'carbon-tool import map --set'")
            ctx.exit(1)

        rename_dict = {}
        missing_fields = []
        for m in mappings:
            if m.source_field in df.columns:
                rename_dict[m.source_field] = m.target_field
            elif m.required:
                missing_fields.append(m.source_field)

        if missing_fields:
            click.echo(f"⚠️  缺少必填字段: {', '.join(missing_fields)}")

        df_mapped = df.rename(columns=rename_dict)

        for target_col in ['date', 'department', 'source_type', 'activity_data',
                           'activity_unit', 'emission_factor', 'product', 'remarks']:
            if target_col not in df_mapped.columns:
                df_mapped[target_col] = ''

        output_path = config.data_dir / output
        df_mapped.to_csv(output_path, index=False, encoding='utf-8-sig')

        audit.record(
            command='import.apply',
            input_files=[str(input_path)],
            output_file=str(output_path),
            row_count=len(df_mapped),
            parameters={'input': input_file, 'output': output, 'mappings': len(rename_dict)},
            status='success',
            message=f'应用{len(rename_dict)}个字段映射',
        )

        click.echo(f"✅ 字段映射应用完成")
        click.echo(f"   映射字段数: {len(rename_dict)}")
        click.echo(f"   输出文件: {output_path}")

        logger.log('import.apply', {'input': input_file, 'output': output}, 'success',
                   f'应用{len(rename_dict)}个字段映射')

    except Exception as e:
        click.echo(f"❌ 应用映射失败: {e}")
        logger.log('import.apply', {'input': input_file, 'output': output}, 'failed', str(e))
        ctx.exit(1)


SOURCE_COLUMNS = ['source_file', 'source_sheet', 'source_row']


def _resolve_file_path(file_path, data_dir):
    """解析文件路径：先当前目录，再项目 data 目录"""
    p = Path(file_path)
    if p.is_absolute():
        return p if p.exists() else None
    if p.exists():
        return p.resolve()
    in_data = Path(data_dir) / file_path
    if in_data.exists():
        return in_data.resolve()
    return None

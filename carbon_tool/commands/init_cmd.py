import click
import yaml
from pathlib import Path
from ..config import Config
from ..logger import CommandLogger
from ..data_manager import DataManager
from ..models import EmissionFactor, FieldMapping


@click.command()
@click.option('--name', '-n', default='carbon-project', help='项目名称')
@click.option('--path', '-p', default=None, help='项目路径（默认使用 --project-path）')
@click.option('--force', '-f', is_flag=True, help='强制初始化，覆盖已有配置')
@click.pass_context
def init(ctx, name, path, force):
    """初始化碳中和管理项目"""
    if path:
        project_path = Path(path).resolve()
        config = Config(project_path)
        logger = CommandLogger(config.logs_dir)
        dm = DataManager(config)
    else:
        config = ctx.obj['config']
        logger = ctx.obj['logger']
        dm = ctx.obj['dm']
        project_path = config.project_path

    try:
        if config.is_initialized() and not force:
            click.echo(f"错误: 项目已存在于 {project_path}，使用 --force 覆盖")
            logger.log('init', {'name': name, 'path': str(project_path)}, 'failed', '项目已存在')
            ctx.exit(1)

        config.set('project_name', name)
        config.ensure_dirs()

        default_factors = {
            '电力-华东电网': EmissionFactor(
                name='电力-华东电网',
                factor=0.5810,
                unit='tCO2e/MWh',
                scope='范围2',
                category='外购电力',
                description='华东电网电网排放因子（参考值）'
            ),
            '天然气': EmissionFactor(
                name='天然气',
                factor=2.1622,
                unit='tCO2e/万m³',
                scope='范围1',
                category='固定燃烧',
                description='天然气燃烧排放因子'
            ),
            '汽油': EmissionFactor(
                name='汽油',
                factor=2.9252,
                unit='tCO2e/t',
                scope='范围1',
                category='移动燃烧',
                description='汽油燃烧排放因子'
            ),
            '柴油': EmissionFactor(
                name='柴油',
                factor=3.1617,
                unit='tCO2e/t',
                scope='范围1',
                category='移动燃烧',
                description='柴油燃烧排放因子'
            ),
            '原煤': EmissionFactor(
                name='原煤',
                factor=2.6489,
                unit='tCO2e/t',
                scope='范围1',
                category='固定燃烧',
                description='原煤燃烧排放因子'
            ),
            '自来水': EmissionFactor(
                name='自来水',
                factor=0.00091,
                unit='tCO2e/m³',
                scope='范围3',
                category='上游运输',
                description='自来水供应排放因子'
            ),
        }
        dm.save_factors(default_factors)

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

        click.echo(f"✅ 项目 '{name}' 初始化成功！")
        click.echo(f"   项目路径: {project_path}")
        click.echo(f"   数据目录: {config.data_dir}")
        click.echo(f"   输出目录: {config.output_dir}")
        click.echo(f"   日志目录: {config.logs_dir}")
        click.echo("")
        click.echo("已预置默认排放因子:")
        for fname in default_factors.keys():
            click.echo(f"  - {fname}")
        click.echo("")
        click.echo("下一步操作:")
        click.echo(f"  1. 将排放数据放入 {config.data_dir} 目录")
        click.echo(f"  2. 运行 'carbon-tool import file <文件名>' 导入数据")
        click.echo(f"  3. 运行 'carbon-tool calc run' 计算排放量")

        logger.log('init', {'name': name, 'path': str(project_path)}, 'success',
                   f'项目初始化成功，预置{len(default_factors)}个排放因子')

    except Exception as e:
        click.echo(f"❌ 初始化失败: {e}")
        logger.log('init', {'name': name, 'path': str(project_path)}, 'failed', str(e))
        ctx.exit(1)

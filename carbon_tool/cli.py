import click
from . import __version__
from .commands.init_cmd import init
from .commands.import_cmd import import_cmd
from .commands.factor_cmd import factor
from .commands.calc_cmd import calc
from .commands.compare_cmd import compare
from .commands.check_cmd import check
from .commands.report_cmd import report
from .commands.export_cmd import export
from .commands.logs_cmd import logs


@click.group()
@click.version_option(version=__version__, prog_name='carbon-tool')
@click.option('--project-path', '-P', default='.', help='项目路径（默认为当前目录）')
@click.pass_context
def cli(ctx, project_path):
    """碳中和管理命令行工具 - 企业排放数据批量整理与分析

    \b
    八大功能模块:
      init      项目初始化
      import    数据导入与字段映射
      factor    排放因子维护
      calc      排放计算与范围分类
      compare   数据对比与汇总分析
      check     数据质量检查与异常检测
      report    报告生成与减排管理
      export    结果导出与数据输出
      logs      命令执行日志管理

    \b
    典型工作流:
      1. carbon-tool init -n 项目名称
      2. carbon-tool import file 排放数据.csv
      3. carbon-tool import map -l
      4. carbon-tool import apply
      5. carbon-tool calc run
      6. carbon-tool calc summary
      7. carbon-tool report generate -f markdown
    """
    ctx.ensure_object(dict)
    ctx.obj['project_path'] = project_path


cli.add_command(init)
cli.add_command(import_cmd, name='import')
cli.add_command(factor)
cli.add_command(calc)
cli.add_command(compare)
cli.add_command(check)
cli.add_command(report)
cli.add_command(export)
cli.add_command(logs)


def main():
    cli()


if __name__ == '__main__':
    main()

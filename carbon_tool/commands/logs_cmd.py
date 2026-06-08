import click
from tabulate import tabulate
from ..config import Config
from ..logger import CommandLogger


@click.group()
def logs():
    """命令执行日志管理"""
    pass


@logs.command('list')
@click.option('--limit', '-n', default=20, type=int, help='显示条数（默认20）')
@click.option('--command', '-c', help='按命令筛选')
@click.option('--status', '-s', help='按状态筛选（success/failed）')
@click.pass_context
def list_logs(ctx, limit, command, status):
    """查看命令执行日志"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        all_logs = logger.list_logs(limit=1000, command_filter=command)

        if status:
            all_logs = [l for l in all_logs if l.get('status') == status]

        logs = all_logs[-limit:]

        if not logs:
            click.echo("📋 暂无日志记录")
            return

        click.echo(f"📋 命令执行日志 (共 {len(logs)} 条，最近 {limit} 条):")
        click.echo("")

        table = []
        for log in reversed(logs):
            status_icon = "✅" if log.get('status') == 'success' else "❌"
            table.append([
                log.get('timestamp', '')[:19],
                log.get('command', ''),
                status_icon,
                log.get('message', '')[:50]
            ])

        click.echo(tabulate(table, headers=['时间', '命令', '状态', '消息'], tablefmt='simple'))

    except Exception as e:
        click.echo(f"❌ 读取日志失败: {e}")
        ctx.exit(1)


@logs.command('show')
@click.argument('index', type=int, default=-1)
@click.pass_context
def show_log(ctx, index):
    """查看日志详情（-1表示最新一条）"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        logs = logger.list_logs(limit=1000)
        if not logs:
            click.echo("📋 暂无日志记录")
            return

        if index < 0:
            log_entry = logs[index]
        else:
            log_entry = logs[index] if index < len(logs) else logs[-1]

        import json
        click.echo("📋 日志详情:")
        click.echo("-" * 50)
        click.echo(f"   时间: {log_entry.get('timestamp', '')}")
        click.echo(f"   命令: {log_entry.get('command', '')}")
        click.echo(f"   状态: {log_entry.get('status', '')}")
        click.echo(f"   消息: {log_entry.get('message', '')}")
        click.echo(f"   参数:")
        args = log_entry.get('args', {})
        if args:
            for k, v in args.items():
                click.echo(f"     - {k}: {v}")
        details = log_entry.get('details', {})
        if details:
            click.echo(f"   详情:")
            for k, v in details.items():
                click.echo(f"     - {k}: {v}")

    except Exception as e:
        click.echo(f"❌ 读取日志失败: {e}")
        ctx.exit(1)


@logs.command('clear')
@click.option('--yes', '-y', is_flag=True, help='确认清除')
@click.pass_context
def clear_logs(ctx, yes):
    """清除所有日志"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        if not yes:
            click.confirm("确定要清除所有命令执行日志吗？", abort=True)

        if logger.clear_logs():
            click.echo("✅ 日志已清除")
        else:
            click.echo("⚠️  没有日志文件可清除")

    except click.Abort:
        click.echo("取消清除")
    except Exception as e:
        click.echo(f"❌ 清除失败: {e}")
        ctx.exit(1)

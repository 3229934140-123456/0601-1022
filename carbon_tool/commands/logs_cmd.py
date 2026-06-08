import click
import json
from datetime import datetime
from pathlib import Path
from tabulate import tabulate


@click.command('logs')
@click.option('--limit', '-n', default=20, type=int, help='显示最近 N 条 (默认20)')
@click.option('--command', '-c', help='按命令过滤')
@click.option('--status', '-s', help='按状态过滤 (success/failed)')
@click.option('--today', is_flag=True, help='仅显示今天的日志')
@click.pass_context
def logs(ctx, limit, command, status, today):
    """查看命令执行日志"""
    config = ctx.obj['config']
    logger_obj = ctx.obj['logger']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        records = logger_obj.list_logs(limit=1000)

        if not records:
            click.echo("📭 暂无日志记录")
            return

        filtered = records
        if command:
            filtered = [r for r in filtered if command in r.get('command', '')]
        if status:
            filtered = [r for r in filtered if r.get('status') == status]
        if today:
            today_str = datetime.now().strftime('%Y-%m-%d')
            filtered = [r for r in filtered if r.get('timestamp', '').startswith(today_str)]

        if not filtered:
            click.echo("🔍 没有匹配的日志记录")
            return

        recent = filtered[-limit:]

        click.echo(f"📜 命令执行日志 (共 {len(filtered)} 条，显示最近 {len(recent)} 条):")
        click.echo("")

        table = []
        for r in recent:
            ts = r.get('timestamp', '')[:19].replace('T', ' ')
            cmd = r.get('command', '')
            st = r.get('status', '')
            status_icon = "✅" if st == 'success' else "❌"
            detail = r.get('message', '')[:30] if r.get('message') else ''
            table.append([ts, f"{status_icon} {st}", cmd, detail])

        click.echo(tabulate(table, headers=['时间', '状态', '命令', '详情'], tablefmt='simple'))

        total = len(filtered)
        success_count = sum(1 for r in filtered if r.get('status') == 'success')
        failed_count = sum(1 for r in filtered if r.get('status') == 'failed')

        click.echo(f"\n📊 统计: 总计 {total} 条, 成功 {success_count} 条, 失败 {failed_count} 条")

    except Exception as e:
        click.echo(f"❌ 读取日志失败: {e}")
        ctx.exit(1)

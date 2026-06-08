import click
from pathlib import Path
from tabulate import tabulate


@click.group()
def history():
    """数据处理历史与审计追踪"""
    pass


@history.command('list')
@click.option('--limit', '-n', default=20, type=int, help='显示最近 N 条 (默认20)')
@click.option('--command', '-c', help='按命令过滤')
@click.pass_context
def history_list(ctx, limit, command):
    """查看最近的数据处理记录"""
    config = ctx.obj['config']
    audit = ctx.obj['audit']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    records = audit.list_records(limit=limit, command=command)

    if not records:
        click.echo("📭 暂无数据处理记录")
        return

    click.echo(f"📜 数据处理历史 (最近 {len(records)} 条):")
    click.echo("")

    table = []
    for r in records:
        ts = r.get('timestamp', '')[:19].replace('T', ' ')
        cmd = r.get('command', '')
        status = r.get('status', '')
        status_icon = "✅" if status == 'success' else "❌"
        out_file = Path(r.get('output_file', '')).name
        rows = r.get('row_count', 0)
        table.append([
            r.get('id', '')[:8],
            ts,
            f"{status_icon} {status}",
            cmd,
            out_file,
            rows,
        ])
    click.echo(tabulate(table, headers=['ID', '时间', '状态', '命令', '输出文件', '行数'],
                        tablefmt='simple'))

    total = len(records)
    success_count = sum(1 for r in records if r.get('status') == 'success')
    click.echo(f"\n📊 统计: 共 {total} 条, 成功 {success_count} 条")


@history.command('trace')
@click.argument('file_name')
@click.option('--max-depth', '-d', default=10, type=int, help='最大追溯深度')
@click.pass_context
def history_trace(ctx, file_name, max_depth):
    """追溯文件的数据来源链路"""
    config = ctx.obj['config']
    audit = ctx.obj['audit']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    chain = audit.trace_file(file_name, max_depth)

    if not chain:
        click.echo(f"🔍 未找到文件 '{file_name}' 的处理记录")
        return

    click.echo(f"🔗 数据链路追踪: {file_name}")
    click.echo("")

    for i, r in enumerate(chain):
        ts = r.get('timestamp', '')[:19].replace('T', ' ')
        cmd = r.get('command', '')
        rec_id = r.get('id', '')[:8]
        inputs = ', '.join(Path(f).name for f in r.get('input_files', []))
        output = Path(r.get('output_file', '')).name
        rows = r.get('row_count', 0)
        indent = '  ' * i
        click.echo(f"{indent}┌─ [{rec_id}] {ts} {cmd}")
        click.echo(f"{indent}│  输入: {inputs if inputs else '(无)'}")
        click.echo(f"{indent}│  输出: {output} ({rows} 行)")
        if r.get('total_emissions'):
            click.echo(f"{indent}│  排放量: {r['total_emissions']:,.2f} tCO2e")
        if i < len(chain) - 1:
            click.echo(f"{indent}│")

    click.echo(f"\n📊 链路深度: {len(chain)} 步")


@history.command('detail')
@click.argument('record_id')
@click.pass_context
def history_detail(ctx, record_id):
    """查看单条记录的详细信息"""
    config = ctx.obj['config']
    audit = ctx.obj['audit']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    record = audit.get_record(record_id)

    if not record:
        click.echo(f"❌ 未找到记录: {record_id}")
        ctx.exit(1)

    click.echo(f"📋 记录详情")
    click.echo("=" * 50)
    click.echo(f"ID:        {record.get('id', '')}")
    click.echo(f"时间:      {record.get('timestamp', '')}")
    click.echo(f"命令:      {record.get('command', '')}")
    click.echo(f"状态:      {record.get('status', '')}")
    click.echo(f"消息:      {record.get('message', '')}")
    click.echo("")
    click.echo(f"输入文件:")
    inputs = record.get('input_files', [])
    if inputs:
        for f in inputs:
            click.echo(f"  - {f}")
    else:
        click.echo("  (无)")
    click.echo("")
    click.echo(f"输出文件:  {record.get('output_file', '')}")
    click.echo(f"行数:      {record.get('row_count', 0)}")
    click.echo(f"总排放量:  {record.get('total_emissions', 0):,.2f} tCO2e")
    click.echo("")
    params = record.get('parameters', {})
    if params:
        click.echo(f"命令参数:")
        for k, v in params.items():
            click.echo(f"  {k}: {v}")
    click.echo("=" * 50)

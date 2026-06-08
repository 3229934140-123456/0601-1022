import click
import json
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
@click.option('--tree/--no-tree', default=True, help='是否树形展示（默认树形）')
@click.pass_context
def history_trace(ctx, file_name, max_depth, tree):
    """追溯文件的数据来源链路（支持多输入、工作表、行号）"""
    config = ctx.obj['config']
    audit = ctx.obj['audit']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    tree_node = audit.trace_file_tree(file_name, max_depth)

    if not tree_node:
        click.echo(f"🔍 未找到文件 '{file_name}' 的处理记录")
        return

    click.echo(f"🔗 数据链路追踪: {file_name}")
    click.echo("")

    _print_tree(tree_node, indent=0, is_last=True, is_root=True)

    original_files = _collect_original_files(tree_node)
    if original_files:
        click.echo(f"\n📂 原始数据来源 (共 {len(original_files)} 个):")
        for of in original_files[:20]:
            click.echo(f"   • {of}")
        if len(original_files) > 20:
            click.echo(f"   ... 还有 {len(original_files) - 20} 个")

    depth = _tree_depth(tree_node)
    click.echo(f"\n📊 链路深度: {depth} 步")


def _print_tree(node, indent, is_last, is_root=False):
    """递归打印树节点"""
    record = node.get('record')
    fname = node.get('file_name', '')
    sources = node.get('sources', [])
    inputs = node.get('inputs', [])

    if is_root:
        prefix = ''
    else:
        prefix = '│  ' * (indent - 1) + ('└─ ' if is_last else '├─ ')

    if record:
        rec_id = record.get('id', '')[:8]
        ts = record.get('timestamp', '')[:19].replace('T', ' ')
        cmd = record.get('command', '')
        status = record.get('status', '')
        status_icon = "✅" if status == 'success' else "❌"
        rows = record.get('row_count', 0)
        emissions = record.get('total_emissions', 0)

        header = f"{prefix}[{rec_id}] {ts} {cmd} {status_icon}"
        click.echo(header)

        sub_prefix = ('   ' if is_root else '│  ' * indent)
        click.echo(f"{sub_prefix}输出: {fname} ({rows} 行)")
        if emissions:
            click.echo(f"{sub_prefix}排放: {emissions:,.2f} tCO2e")
    else:
        header = f"{prefix}📄 {fname} (原始文件)"
        click.echo(header)
        sub_prefix = '   ' * (indent + 1)

    if sources:
        sub_prefix2 = '   ' * (indent + 1) if is_root else '│  ' * indent + '   '
        for i, s in enumerate(sources):
            sf = s.get('source_file', '')
            ss = s.get('source_sheet', '')
            rmin = s.get('min_row', '')
            rmax = s.get('max_row', '')
            rc = s.get('row_count', '')
            sheet_str = f" [{ss}]" if ss else ""
            row_str = f" 行{rmin}-{rmax}" if rmin else ""
            click.echo(f"{sub_prefix2}• 来源: {sf}{sheet_str} ({rc} 行{row_str})")

    if inputs:
        for i, inp in enumerate(inputs):
            is_last_child = (i == len(inputs) - 1)
            _print_tree(inp, indent + 1, is_last_child, is_root=False)


def _tree_depth(node):
    """计算树的深度"""
    if not node or not node.get('inputs'):
        return 0
    return 1 + max(_tree_depth(inp) for inp in node['inputs'])


def _collect_original_files(node):
    """收集所有原始输入文件（叶子节点）"""
    if not node:
        return []
    if node.get('is_original') or not node.get('inputs'):
        return [node.get('file_name', '')]
    result = []
    for inp in node.get('inputs', []):
        result.extend(_collect_original_files(inp))
    return list(set(result))


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


@history.command('export')
@click.option('--limit', '-n', default=20, type=int, help='最近 N 条记录 (默认20)')
@click.option('--format', '-f', 'fmt', default='json',
              type=click.Choice(['json', 'markdown', 'md']),
              help='输出格式: json/markdown (默认json)')
@click.option('--output', '-o', 'output_file', help='输出文件路径（不填则输出到终端）')
@click.option('--command', '-c', help='按命令过滤')
@click.option('--trace', '-t', 'trace_file', help='追溯指定文件的完整链路并导出')
@click.pass_context
def history_export(ctx, limit, fmt, output_file, command, trace_file):
    """导出审计记录为 JSON 或 Markdown"""
    config = ctx.obj['config']
    audit = ctx.obj['audit']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    if trace_file:
        tree = audit.trace_file_tree(trace_file, max_depth=20)
        records = _flatten_tree_records(tree)
        title = f"数据链路追溯: {trace_file}"
    else:
        records = audit.list_records(limit=limit, command=command)
        title = f"数据处理历史 (最近 {len(records)} 条)"

    if fmt == 'json':
        content = json.dumps(records, ensure_ascii=False, indent=2)
    else:
        content = _render_markdown(records, title, trace_file, audit)

    if output_file:
        out_path = Path(output_file)
        if not out_path.is_absolute():
            out_path = config.output_dir / output_file
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(content)
        click.echo(f"✅ 已导出到: {out_path}")
        click.echo(f"   记录数: {len(records)} 条")
    else:
        click.echo(content)


def _flatten_tree_records(node):
    """把树节点展平为记录列表（按时间顺序）"""
    if not node:
        return []
    result = []
    if node.get('record'):
        result.append(node['record'])
    for inp in node.get('inputs', []):
        result.extend(_flatten_tree_records(inp))
    result.sort(key=lambda r: r.get('timestamp', ''))
    return result


def _render_markdown(records, title, trace_file=None, audit=None):
    """把审计记录渲染成 Markdown"""
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**记录数:** {len(records)}")
    if records:
        lines.append(f"**时间范围:** {records[0].get('timestamp', '')} ~ {records[-1].get('timestamp', '')}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for i, r in enumerate(records):
        cmd = r.get('command', '')
        ts = r.get('timestamp', '')
        status = r.get('status', '')
        out_f = Path(r.get('output_file', '')).name
        rows = r.get('row_count', 0)
        emissions = r.get('total_emissions', 0)
        inputs = r.get('input_files', [])
        params = r.get('parameters', {})
        msg = r.get('message', '')
        rec_id = r.get('id', '')

        lines.append(f"## {i + 1}. {cmd}")
        lines.append("")
        lines.append(f"- **ID:** {rec_id}")
        lines.append(f"- **时间:** {ts}")
        lines.append(f"- **状态:** {status}")
        if msg:
            lines.append(f"- **说明:** {msg}")
        lines.append(f"- **行数:** {rows}")
        lines.append(f"- **总排放量:** {emissions:,.2f} tCO2e")
        lines.append("")

        if inputs:
            lines.append("### 输入文件")
            lines.append("")
            for f in inputs:
                lines.append(f"- `{Path(f).name}`")
            lines.append("")

        lines.append(f"### 输出文件")
        lines.append("")
        lines.append(f"- `{out_f}`")
        lines.append("")

        if params:
            lines.append("### 命令参数")
            lines.append("")
            for k, v in params.items():
                lines.append(f"- **{k}:** {v}")
            lines.append("")

        lines.append("---")
        lines.append("")

    if trace_file and audit:
        tree = audit.trace_file_tree(trace_file, max_depth=20)
        original = _collect_original_files(tree)
        if original:
            lines.append("## 原始数据来源")
            lines.append("")
            for of in sorted(original):
                lines.append(f"- `{of}`")
            lines.append("")

    return '\n'.join(lines)

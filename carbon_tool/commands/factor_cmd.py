import click
from tabulate import tabulate
from ..models import EmissionFactor


@click.group()
def factor():
    """排放因子维护管理"""
    pass


@factor.command('list')
@click.option('--scope', help='按范围筛选（范围1/范围2/范围3）')
@click.option('--category', help='按类别筛选')
@click.pass_context
def list_factors(ctx, scope, category):
    """列出所有排放因子"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        factors = dm.load_factors()
        filtered = list(factors.values())

        if scope:
            filtered = [f for f in filtered if scope in f.scope]

        if category:
            filtered = [f for f in filtered if category in f.category]

        if not filtered:
            click.echo("📋 没有找到排放因子")
        else:
            click.echo(f"📋 排放因子列表 (共 {len(filtered)} 个):")
            table = []
            for f in sorted(filtered, key=lambda x: (x.scope, x.category, x.name)):
                table.append([
                    f.name,
                    f.factor,
                    f.unit,
                    f.scope,
                    f.category,
                    f.description
                ])
            click.echo(tabulate(table, headers=['名称', '因子值', '单位', '范围', '类别', '描述'],
                                tablefmt='simple', floatfmt='.4f'))

        logger.log('factor.list', {'scope': scope, 'category': category}, 'success',
                   f'列出{len(filtered)}个排放因子')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('factor.list', {}, 'failed', str(e))
        ctx.exit(1)


@factor.command('add')
@click.option('--name', '-n', required=True, help='排放因子名称')
@click.option('--value', '-v', required=True, type=float, help='排放因子值')
@click.option('--unit', '-u', required=True, help='排放因子单位')
@click.option('--scope', '-s', required=True, help='排放范围（范围1/范围2/范围3）')
@click.option('--category', '-c', required=True, help='排放类别')
@click.option('--description', '-d', default='', help='描述说明')
@click.option('--tag', '-t', 'tags', multiple=True, help='标签，格式 key=value（可重复）')
@click.pass_context
def add_factor(ctx, name, value, unit, scope, category, description, tags):
    """新增排放因子"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    tag_dict = {}
    if tags:
        for t in tags:
            if '=' in t:
                k, v = t.split('=', 1)
                tag_dict[k.strip()] = v.strip()

    try:
        ef = EmissionFactor(
            name=name,
            factor=value,
            unit=unit,
            scope=scope,
            category=category,
            description=description,
            tags=tag_dict,
        )
        dm.add_factor(ef)
        click.echo(f"✅ 排放因子 '{name}' 添加成功")
        click.echo(f"   值: {value} {unit}")
        click.echo(f"   范围: {scope}")
        click.echo(f"   类别: {category}")
        if tag_dict:
            tag_str = ', '.join(f"{k}={v}" for k, v in tag_dict.items())
            click.echo(f"   标签: {tag_str}")
        logger.log('factor.add', {'name': name}, 'success', f'添加排放因子: {name}')

    except Exception as e:
        click.echo(f"❌ 添加失败: {e}")
        logger.log('factor.add', {'name': name}, 'failed', str(e))
        ctx.exit(1)


@factor.command('update')
@click.option('--name', '-n', required=True, help='排放因子名称')
@click.option('--value', '-v', type=float, help='排放因子值')
@click.option('--unit', '-u', help='排放因子单位')
@click.option('--scope', '-s', help='排放范围')
@click.option('--category', '-c', help='排放类别')
@click.option('--description', '-d', help='描述说明')
@click.option('--tag', '-t', 'tags', multiple=True, help='添加/更新标签，格式 key=value（可重复）')
@click.option('--remove-tag', 'remove_tags', multiple=True, help='移除标签（按 key）')
@click.option('--clear-tags', is_flag=True, help='清除所有标签')
@click.pass_context
def update_factor(ctx, name, value, unit, scope, category, description, tags, remove_tags, clear_tags):
    """更新排放因子"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    tag_updates = {}
    if tags:
        for t in tags:
            if '=' in t:
                k, v = t.split('=', 1)
                tag_updates[k.strip()] = v.strip()

    try:
        existing = dm.get_factor(name)
        if not existing:
            click.echo(f"❌ 错误: 排放因子 '{name}' 不存在")
            logger.log('factor.update', {'name': name}, 'failed', '因子不存在')
            ctx.exit(1)

        if value is not None:
            existing.factor = value
        if unit is not None:
            existing.unit = unit
        if scope is not None:
            existing.scope = scope
        if category is not None:
            existing.category = category
        if description is not None:
            existing.description = description
        if clear_tags:
            existing.tags = {}
        if remove_tags:
            for rt in remove_tags:
                existing.tags.pop(rt, None)
        if tag_updates:
            existing.tags.update(tag_updates)

        dm.add_factor(existing)
        click.echo(f"✅ 排放因子 '{name}' 更新成功")
        if tag_updates:
            tag_str = ', '.join(f"{k}={v}" for k, v in tag_updates.items())
            click.echo(f"   新增/更新标签: {tag_str}")
        logger.log('factor.update', {'name': name}, 'success', f'更新排放因子: {name}')

    except Exception as e:
        click.echo(f"❌ 更新失败: {e}")
        logger.log('factor.update', {'name': name}, 'failed', str(e))
        ctx.exit(1)


@factor.command('search')
@click.argument('keyword')
@click.option('--tag', '-t', 'tags', multiple=True, help='按标签筛选，格式 key=value（可重复）')
@click.pass_context
def search_factor(ctx, keyword, tags):
    """搜索排放因子（按名称/类别/标签）"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    tag_dict = {}
    if tags:
        for t in tags:
            if '=' in t:
                k, v = t.split('=', 1)
                tag_dict[k.strip()] = v.strip()

    try:
        candidates = dm.find_factors(keyword, tag_dict)
        if not candidates:
            click.echo(f"🔍 未找到匹配的排放因子: {keyword}")
            return

        click.echo(f"🔍 找到 {len(candidates)} 个候选因子:")
        table = []
        for i, f in enumerate(candidates):
            tag_str = ', '.join(f"{k}={v}" for k, v in f.tags.items()) if f.tags else ''
            table.append([
                f"[{i}]",
                f.name,
                f.factor,
                f.unit,
                f.scope,
                tag_str,
            ])
        click.echo(tabulate(table, headers=['', '名称', '因子值', '单位', '范围', '标签'],
                            tablefmt='simple', floatfmt='.4f'))

        logger.log('factor.search', {'keyword': keyword, 'tags': tag_dict}, 'success',
                   f'找到{len(candidates)}个候选因子')

    except Exception as e:
        click.echo(f"❌ 搜索失败: {e}")
        logger.log('factor.search', {'keyword': keyword}, 'failed', str(e))
        ctx.exit(1)


@factor.command('delete')
@click.argument('name')
@click.option('--yes', '-y', is_flag=True, help='确认删除')
@click.pass_context
def delete_factor(ctx, name, yes):
    """删除排放因子"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        existing = dm.get_factor(name)
        if not existing:
            click.echo(f"❌ 错误: 排放因子 '{name}' 不存在")
            ctx.exit(1)

        if not yes:
            click.confirm(f"确定要删除排放因子 '{name}' 吗？", abort=True)

        if dm.delete_factor(name):
            click.echo(f"✅ 排放因子 '{name}' 已删除")
            logger.log('factor.delete', {'name': name}, 'success', f'删除排放因子: {name}')
        else:
            click.echo(f"❌ 删除失败")
            ctx.exit(1)

    except click.Abort:
        click.echo("取消删除")
    except Exception as e:
        click.echo(f"❌ 删除失败: {e}")
        logger.log('factor.delete', {'name': name}, 'failed', str(e))
        ctx.exit(1)


@factor.command('show')
@click.argument('name')
@click.pass_context
def show_factor(ctx, name):
    """查看排放因子详情"""
    config = ctx.obj['config']
    logger = ctx.obj['logger']
    dm = ctx.obj['dm']

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    try:
        ef = dm.get_factor(name)
        if not ef:
            click.echo(f"❌ 错误: 排放因子 '{name}' 不存在")
            ctx.exit(1)

        click.echo(f"📋 排放因子详情:")
        click.echo(f"   名称: {ef.name}")
        click.echo(f"   因子值: {ef.factor} {ef.unit}")
        click.echo(f"   范围: {ef.scope}")
        click.echo(f"   类别: {ef.category}")
        click.echo(f"   描述: {ef.description or '-'}")
        logger.log('factor.show', {'name': name}, 'success', '查看排放因子详情')

    except Exception as e:
        click.echo(f"❌ 操作失败: {e}")
        logger.log('factor.show', {'name': name}, 'failed', str(e))
        ctx.exit(1)

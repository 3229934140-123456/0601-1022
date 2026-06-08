import click
import pandas as pd
from tabulate import tabulate
from ..config import Config
from ..logger import CommandLogger
from ..utils import safe_float, format_number


@click.group()
def check():
    """数据质量检查与异常检测"""
    pass


@check.command('anomaly')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--threshold', '-t', default=30.0, type=float, help='波动阈值百分比 (默认30%%)')
@click.option('--by', 'group_by', default='department', help='按部门/类别/范围检查')
@click.option('--output', '-o', 'output_file', help='异常结果输出文件名')
@click.pass_context
def anomaly_check(ctx, input_file, threshold, group_by, output_file):
    """异常波动检查"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('check.anomaly', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        if 'emissions' not in df.columns or 'date' not in df.columns:
            click.echo("❌ 错误: 数据缺少必要字段，请先运行 'carbon-tool calc run'")
            ctx.exit(1)

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date'])
        df['month'] = df['date'].dt.strftime('%Y-%m')

        if group_by not in df.columns:
            group_by = 'department'

        anomalies = []

        groups = df[group_by].dropna().unique()
        for group in groups:
            group_df = df[df[group_by] == group]
            monthly = group_df.groupby('month')['emissions'].sum().sort_index()

            if len(monthly) < 2:
                continue

            for i in range(1, len(monthly)):
                prev_val = monthly.iloc[i - 1]
                curr_val = monthly.iloc[i]
                if prev_val == 0:
                    continue
                pct_change = abs((curr_val - prev_val) / prev_val * 100)
                if pct_change > threshold:
                    direction = "上升" if curr_val > prev_val else "下降"
                    anomalies.append({
                        group_by: group,
                        '月份': monthly.index[i],
                        '上月排放量': round(prev_val, 2),
                        '本月排放量': round(curr_val, 2),
                        '变化量': round(curr_val - prev_val, 2),
                        '变化率': round((curr_val - prev_val) / prev_val * 100, 2),
                        '方向': direction,
                    })

        if not anomalies:
            click.echo(f"✅ 未发现超过 {threshold}% 的异常波动")
            logger.log('check.anomaly', {'input': input_file, 'threshold': threshold}, 'success',
                       '未发现异常波动')
            return

        click.echo(f"⚠️  发现 {len(anomalies)} 条异常波动记录 (阈值: {threshold}%):")
        click.echo("")

        table = []
        for a in anomalies:
            table.append([
                a[group_by],
                a['月份'],
                f"{a['上月排放量']:,.2f}",
                f"{a['本月排放量']:,.2f}",
                f"{a['变化量']:+,.2f}",
                f"{a['变化率']:+.2f}%",
                a['方向']
            ])
        headers = [group_by, '月份', '上月(tCO2e)', '本月(tCO2e)', '变化量', '变化率', '方向']
        click.echo(tabulate(table, headers=headers, tablefmt='simple'))

        if output_file:
            output_path = config.output_dir / output_file
            anomaly_df = pd.DataFrame(anomalies)
            anomaly_df.to_csv(output_path, index=False, encoding='utf-8-sig')
            click.echo(f"\n💾 异常结果已保存到: {output_path}")

        high_count = sum(1 for a in anomalies if a['方向'] == '上升')
        low_count = sum(1 for a in anomalies if a['方向'] == '下降')
        click.echo(f"\n📊 统计: 上升异常 {high_count} 条, 下降异常 {low_count} 条")

        logger.log('check.anomaly', {
            'input': input_file, 'threshold': threshold, 'group_by': group_by
        }, 'success', f'发现{len(anomalies)}条异常波动')

    except Exception as e:
        click.echo(f"❌ 检查失败: {e}")
        logger.log('check.anomaly', {'input': input_file, 'threshold': threshold}, 'failed', str(e))
        ctx.exit(1)


@check.command('missing')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.pass_context
def missing_check(ctx, input_file):
    """缺失值检查"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('check.missing', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')

        click.echo("📊 缺失值检查:")
        click.echo(f"   总记录数: {len(df)}")
        click.echo("")

        missing_stats = []
        for col in df.columns:
            missing_count = df[col].isna().sum() + (df[col] == '').sum()
            if missing_count > 0:
                pct = missing_count / len(df) * 100
                missing_stats.append([col, missing_count, f"{pct:.2f}%"])

        if not missing_stats:
            click.echo("✅ 所有字段均无缺失值")
        else:
            click.echo(f"⚠️  共 {len(missing_stats)} 个字段存在缺失:")
            click.echo(tabulate(missing_stats, headers=['字段', '缺失数', '缺失率'], tablefmt='simple'))

        critical_fields = ['date', 'department', 'source_type', 'activity_data', 'emissions']
        critical_missing = []
        for field in critical_fields:
            if field in df.columns:
                missing = df[field].isna().sum() + (df[field] == '').sum()
                if missing > 0:
                    critical_missing.append([field, missing])

        if critical_missing:
            click.echo(f"\n🚨 关键字段缺失:")
            click.echo(tabulate(critical_missing, headers=['关键字段', '缺失数'], tablefmt='simple'))

        logger.log('check.missing', {'input': input_file}, 'success',
                   f'缺失值检查，{len(missing_stats)}个字段有缺失')

    except Exception as e:
        click.echo(f"❌ 检查失败: {e}")
        logger.log('check.missing', {'input': input_file}, 'failed', str(e))
        ctx.exit(1)


@check.command('duplicate')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--keys', '-k', default='date,department,source_type', help='重复判定字段（逗号分隔）')
@click.pass_context
def duplicate_check(ctx, input_file, keys):
    """重复数据检查"""
    config = Config()
    logger = CommandLogger(config.logs_dir)

    if not config.is_initialized():
        click.echo("❌ 错误: 当前目录不是碳管理项目，请先运行 'carbon-tool init'")
        ctx.exit(1)

    input_path = config.data_dir / input_file
    if not input_path.exists():
        click.echo(f"❌ 错误: 输入文件不存在: {input_path}")
        logger.log('check.duplicate', {'input': input_file}, 'failed', '输入文件不存在')
        ctx.exit(1)

    try:
        df = pd.read_csv(input_path, encoding='utf-8-sig')
        key_fields = [k.strip() for k in keys.split(',') if k.strip() in df.columns]

        if not key_fields:
            click.echo("❌ 错误: 没有有效的判定字段")
            ctx.exit(1)

        duplicate_mask = df.duplicated(subset=key_fields, keep=False)
        duplicates = df[duplicate_mask].sort_values(by=key_fields)

        if duplicates.empty:
            click.echo("✅ 未发现重复数据")
            logger.log('check.duplicate', {'input': input_file, 'keys': keys}, 'success',
                       '未发现重复数据')
            return

        dup_count = len(duplicates)
        dup_groups = duplicates.groupby(key_fields).size()

        click.echo(f"⚠️  发现 {dup_count} 条重复记录 (按 {', '.join(key_fields)} 判定):")
        click.echo(f"   重复组数: {len(dup_groups)}")
        click.echo("")

        preview = duplicates[key_fields + [c for c in ['activity_data', 'emissions'] if c in df.columns]].head(10)
        click.echo(tabulate(preview, headers='keys', tablefmt='simple', showindex=False, floatfmt='.2f'))
        if len(duplicates) > 10:
            click.echo(f"... 还有 {len(duplicates) - 10} 条")

        logger.log('check.duplicate', {'input': input_file, 'keys': keys}, 'success',
                   f'发现{dup_count}条重复记录')

    except Exception as e:
        click.echo(f"❌ 检查失败: {e}")
        logger.log('check.duplicate', {'input': input_file, 'keys': keys}, 'failed', str(e))
        ctx.exit(1)


@check.command('all')
@click.option('--input', '-i', 'input_file', default='emissions_calculated.csv', help='输入文件名')
@click.option('--threshold', '-t', default=30.0, type=float, help='异常波动阈值')
@click.pass_context
def all_checks(ctx, input_file, threshold):
    """执行全部数据质量检查"""
    click.echo("=" * 50)
    click.echo("📋 全面数据质量检查")
    click.echo("=" * 50)

    ctx.invoke(missing_check, input_file=input_file)
    click.echo("")
    ctx.invoke(anomaly_check, input_file=input_file, threshold=threshold,
               group_by='department', output_file=None)
    click.echo("")
    ctx.invoke(duplicate_check, input_file=input_file, keys='date,department,source_type')
    click.echo("")
    click.echo("=" * 50)
    click.echo("✅ 检查完成")

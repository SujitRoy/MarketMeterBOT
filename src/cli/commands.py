"""
CLI Commands
Command-line interface for maintenance and operations.
"""
import logging
from datetime import date

import click

from src.analysis import run_batch_analysis
from src.core.logging import setup_logging
from src.data.sync import BackfillEngine, SyncEngine
from src.database.connection import check_database_health, init_database, vacuum_database
from src.database.repositories import (
    StatsRepository,
    SubscriberRepository,
    SyncRepository,
)
from src.reports import MorningReport, ReportContext

logger = logging.getLogger(__name__)


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.pass_context
def cli(ctx, verbose):
    """MarketMeter CLI - Maintenance and operations commands."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(log_level=log_level)


@cli.command()
@click.pass_context
def init_db(ctx):
    """Initialize database schema."""
    click.echo("Initializing database...")
    init_database()
    click.echo("✅ Database initialized")


@cli.command()
@click.pass_context
def vacuum_db(ctx):
    """Vacuum database to reclaim space."""
    click.echo("Vacuuming database...")
    vacuum_database()
    click.echo("✅ Database vacuumed")


@cli.command()
@click.pass_context
def health(ctx):
    """Check database health."""
    click.echo("Checking database health...")
    health = check_database_health()

    click.echo(f"Integrity: {health['integrity']}")
    click.echo(f"Size: {health['size_mb']} MB")
    click.echo(f"Journal Mode: {health['journal_mode']}")
    click.echo("Tables:")
    for table, count in health['tables'].items():
        click.echo(f"  {table}: {count:,} rows")


@cli.command()
@click.option('--days', '-d', default=30, help='Number of days to backfill')
@click.option('--start', '-s', help='Start date (YYYY-MM-DD)')
@click.option('--end', '-e', help='End date (YYYY-MM-DD)')
@click.pass_context
def backfill(ctx, days, start, end):
    """Run historical backfill."""
    from datetime import timedelta

    if start:
        start_date = date.fromisoformat(start)
    else:
        start_date = date.today() - timedelta(days=days)

    if end:
        end_date = date.fromisoformat(end)
    else:
        end_date = date.today()

    click.echo(f"Backfilling from {start_date} to {end_date}...")

    engine = BackfillEngine()
    result = engine.run_backfill(start_date, end_date)

    click.echo(f"Status: {result.status}")
    click.echo(f"Processed: {result.dates_processed} days")
    click.echo(f"Success: {result.success}")
    click.echo(f"Failed: {result.failed}")
    click.echo(f"Holidays: {result.holidays}")
    click.echo(f"Total Records: {result.total_records:,}")


@cli.command()
@click.pass_context
def sync(ctx):
    """Run incremental sync."""
    click.echo("Running incremental sync...")

    engine = SyncEngine()
    result = engine.run_incremental_sync()

    click.echo(f"Status: {result.status}")
    click.echo(f"Processed: {result.dates_processed} days")
    click.echo(f"Success: {result.success}")
    click.echo(f"Failed: {result.failed}")
    click.echo(f"Holidays: {result.holidays}")
    click.echo(f"Pending: {len(result.not_available)}")
    click.echo(f"Total Records: {result.total_records:,}")


@cli.command()
@click.pass_context
def retry_sync(ctx):
    """Run retry sync for failed dates."""
    click.echo("Running retry sync...")

    engine = SyncEngine()
    result = engine.run_retry_sync()

    click.echo(f"Status: {result.status}")
    click.echo(f"Retried: {result.dates_processed} days")
    click.echo(f"Succeeded: {result.success}")
    click.echo(f"Failed: {result.failed}")
    click.echo(f"Still Pending: {len(result.not_available)}")
    click.echo(f"Total Records: {result.total_records:,}")


@cli.command()
@click.pass_context
def analyze(ctx):
    """Run technical analysis."""
    click.echo("Running technical analysis...")

    result = run_batch_analysis()

    click.echo(f"Status: {result['status']}")
    click.echo(f"Analyzed: {result['analyzed']} stocks")
    click.echo(f"Skipped: {result['skipped']}")
    click.echo(f"Saved: {result['saved']} rows")
    click.echo(result['message'])


@cli.command()
@click.option('--date', '-d', help='Analysis date (YYYY-MM-DD), default: latest')
@click.pass_context
def report(ctx, date):
    """Generate and display morning report."""
    from src.database.repositories import AnalysisReadRepository, SyncReadRepository

    if date:
        analysis_date = date.fromisoformat(date)
    else:
        sync_repo = SyncReadRepository()
        analysis_date = sync_repo.get_last_synced_date()

    if not analysis_date:
        click.echo("No analysis date available")
        return

    click.echo(f"Generating report for {analysis_date}...")

    analysis_repo = AnalysisReadRepository()
    grouped = analysis_repo.get_analysis_by_recommendation(analysis_date)

    all_stocks = [s for v in grouped.values() for s in v]

    report = MorningReport(ReportContext(
        analysis_date=analysis_date,
        grouped_data={"all_stocks": all_stocks},
        outlook={},
    ))
    result = report.build()

    click.echo(result.content)


@cli.command()
@click.pass_context
def warm_cache(ctx):
    """Warm report cache for latest analysis."""
    from src.database.repositories import (
        AnalysisReadRepository,
        ReportCacheRepository,
        SyncReadRepository,
    )
    from src.reports import MorningReport, ReportContext

    sync_repo = SyncReadRepository()
    analysis_date = sync_repo.get_last_synced_date()

    if not analysis_date:
        click.echo("No analysis date available")
        return

    click.echo(f"Warming cache for {analysis_date}...")

    analysis_repo = AnalysisReadRepository()
    grouped = analysis_repo.get_analysis_by_recommendation(analysis_date)

    all_stocks = [s for v in grouped.values() for s in v]

    report = MorningReport(ReportContext(
        analysis_date=analysis_date,
        grouped_data={"all_stocks": all_stocks},
        outlook={},
    ))
    result = report.build()

    cache_repo = ReportCacheRepository()
    cache_repo.put_cached_report('morning', analysis_date, result.content)

    click.echo("✅ Cache warmed")


@cli.command()
@click.pass_context
def stats(ctx):
    """Show database statistics."""
    repo = StatsRepository()
    stats = repo.get_stats()

    click.echo(f"Total Records: {stats['total_records']:,}")
    click.echo(f"Unique Symbols: {stats['unique_symbols']:,}")
    click.echo(f"Date Range: {stats['date_from']} → {stats['date_to']}")
    click.echo(f"Active Subscribers: {stats['active_subscribers']}")


@cli.command()
@click.pass_context
def subscribers(ctx):
    """List all subscribers."""
    repo = SubscriberRepository()
    subs = repo.get_all_subscribers()

    if not subs:
        click.echo("No subscribers")
        return

    for s in subs:
        status = "✅" if s['active'] else "❌"
        reports = "📬" if s['receive_reports'] else "📭"
        click.echo(
            f"{status} {reports} {s['chat_id']} — "
            f"@{s['username'] or 'N/A'} {s['first_name'] or ''} {s['last_name'] or ''}"
        )


@cli.command()
@click.argument('chat_id', type=int)
@click.pass_context
def remove_subscriber(ctx, chat_id):
    """Remove a subscriber."""
    repo = SubscriberRepository()
    result = repo.remove_subscriber(chat_id)

    if result:
        click.echo(f"✅ Removed subscriber {chat_id}")
    else:
        click.echo(f"❌ Subscriber {chat_id} not found or already inactive")


@cli.command()
@click.pass_context
def sync_status(ctx):
    """Show recent sync status."""
    repo = SyncRepository()
    logs = repo.get_sync_status(days=10)

    if not logs:
        click.echo("No sync history")
        return

    click.echo("Recent Syncs:")
    for log in logs:
        status_icon = {
            'success': '✅', 'failed': '❌',
            'holiday': '🏖️', 'skipped': '⏭️',
            'not_available': '⏳',
        }.get(log['status'], '❓')

        click.echo(
            f"  {status_icon} {log['trade_date']} — {log['status']} "
            f"({log['records_count']:,} records)"
        )


def main():
    """Main CLI entry point."""
    cli(obj={})


if __name__ == '__main__':
    main()

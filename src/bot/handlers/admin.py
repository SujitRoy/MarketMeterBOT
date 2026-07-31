"""
Admin Handler
Owner-only commands for bot management.
"""
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler


class AdminHandler(BaseHandler):
    """Handle admin commands (owner only)."""

    @property
    def command(self) -> str:
        return "admin"

    @property
    def description(self) -> str:
        return "Admin commands (owner only)"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self.require_owner(update, context):
            return

        if not context.args:
            await self.send_message(update, (
                "🔧 **Admin Commands**\n\n"
                "`/admin sync` — Run manual sync\n"
                "`/admin analysis` — Run manual analysis\n"
                "`/admin cache` — Clear report cache\n"
                "`/admin stats` — Database statistics\n"
                "`/admin vacuum` — Vacuum database\n"
                "`/admin subscribers` — List subscribers\n"
                "`/admin broadcast <msg>` — Broadcast message\n"
            ))
            return

        subcmd = context.args[0].lower()

        if subcmd == "sync":
            await self._run_sync(update, context)
        elif subcmd == "analysis":
            await self._run_analysis(update, context)
        elif subcmd == "cache":
            await self._clear_cache(update, context)
        elif subcmd == "stats":
            await self._show_stats(update, context)
        elif subcmd == "vacuum":
            await self._vacuum_db(update, context)
        elif subcmd == "subscribers":
            await self._list_subscribers(update, context)
        elif subcmd == "broadcast":
            await self._broadcast(update, context)
        else:
            await self.send_message(update, f"❌ Unknown admin command: {subcmd}")

    async def _run_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from src.data.sync import SyncEngine

        await self.send_message(update, "🔄 Starting manual sync...")

        engine = SyncEngine()
        result = engine.run_incremental_sync()

        from src.reports import generate_sync_status_message
        msg = generate_sync_status_message({
            'status': result.status,
            'success': result.success,
            'failed': result.failed,
            'holidays': result.holidays,
            'not_available': result.not_available,
            'total_records': result.total_records,
            'dates_processed': result.dates_processed,
        })
        await self.send_message(update, msg)

    async def _run_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from src.analysis import run_batch_analysis

        await self.send_message(update, "📊 Starting manual analysis...")

        result = run_batch_analysis()

        msg = f"""✅ **Analysis Complete**

📅 Date: {result['analysis_date']}
📊 Analyzed: {result['analyzed']} stocks
⏭️ Skipped: {result['skipped']}
💾 Saved: {result['saved']} rows

{result['message']}"""
        await self.send_message(update, msg)

    async def _clear_cache(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from src.database.repositories import ReportCacheRepository

        repo = ReportCacheRepository()
        count = repo.invalidate()

        await self.send_message(update, f"🗑️ Cleared {count} cached reports.")

    async def _show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from src.database.repositories import StatsRepository

        repo = StatsRepository()
        stats = repo.get_stats()

        msg = (
            "📊 **Database Statistics**\n\n"
            f"• Total Records: {stats['total_records']:,}\n"
            f"• Unique Symbols: {stats['unique_symbols']:,}\n"
            f"• Date Range: {stats['date_from']} → {stats['date_to']}\n"
            f"• Active Subscribers: {stats['active_subscribers']}"
        )
        await self.send_message(update, msg)

    async def _vacuum_db(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from src.database.connection import vacuum_database

        await self.send_message(update, "🔧 Vacuuming database...")
        vacuum_database()
        await self.send_message(update, "✅ Database vacuumed.")

    async def _list_subscribers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from src.database.repositories import SubscriberRepository

        repo = SubscriberRepository()
        subs = repo.get_all_subscribers()

        if not subs:
            await self.send_message(update, "No subscribers found.")
            return

        lines = ["👥 **All Subscribers**\n"]
        for s in subs[:50]:
            status = "✅" if s['active'] else "❌"
            reports = "📬" if s['receive_reports'] else "📭"
            lines.append(
                f"{status} {reports} {s['chat_id']} — "
                f"@{s['username'] or 'N/A'} {s['first_name'] or ''} {s['last_name'] or ''}"
            )

        if len(subs) > 50:
            lines.append(f"\n... and {len(subs) - 50} more")

        await self.send_message(update, "\n".join(lines))

    async def _broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.args) < 2:
            await self.send_message(update, "Usage: `/admin broadcast <message>`")
            return

        message = " ".join(context.args[1:])
        from bot import _needs_rich, _send_rich_chunks
        from src.database.repositories import SubscriberRepository

        repo = SubscriberRepository()
        subs = repo.get_active_subscribers()

        sent = 0
        failed = 0

        for sub in subs:
            try:
                if _needs_rich(message):
                    await _send_rich_chunks(update.get_bot(), sub['chat_id'], message)
                else:
                    await update.get_bot().send_message(
                        chat_id=sub['chat_id'], text=message, parse_mode="Markdown"
                    )
                sent += 1
            except Exception as e:
                logger.error("Broadcast failed for %s: %s", sub['chat_id'], e)
                failed += 1

        await self.send_message(update, f"📢 Broadcast sent: {sent} delivered, {failed} failed.")

"""
Report Handler
Handles /report command to send latest analysis.
"""
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.handlers.base import BaseHandler


class ReportHandler(BaseHandler):
    """Handle /report command."""

    @property
    def command(self) -> str:
        return "report"

    @property
    def description(self) -> str:
        return "Get latest analysis report"

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from bot import _needs_rich, _send_rich_chunks
        from src.core.config import OWNER_CHAT_ID
        from src.database.repositories import AnalysisReadRepository, SyncReadRepository
        from src.reports import MorningReport, ReportContext

        # Check if we should send to owner or all subscribers
        is_owner = self.is_owner(update)

        # Get analysis date
        sync_repo = SyncReadRepository()
        analysis_date = sync_repo.get_last_synced_date()

        if not analysis_date:
            await self.send_message(update, "⚠️ No analysis data available yet. Check `/status` for sync progress.")
            return

        # Get analysis data
        analysis_repo = AnalysisReadRepository()
        grouped = analysis_repo.get_analysis_by_recommendation(analysis_date)

        total = sum(len(v) for v in grouped.values())
        if total == 0:
            await self.send_message(update, f"⚠️ No analysis data for {analysis_date.strftime('%d %b %Y')}.")
            return

        # Flatten all stocks
        all_stocks = [s for v in grouped.values() for s in v]

        # Build report
        report = MorningReport(ReportContext(
            analysis_date=analysis_date,
            grouped_data={"all_stocks": all_stocks},
            outlook={},
        ))
        result = report.build()

        if _needs_rich(result.content):
            if is_owner:
                await _send_rich_chunks(context.bot, OWNER_CHAT_ID, result.content)
            else:
                # For non-owner, just send first chunk or fallback
                await self.send_message(update, result.chunks[0] if result.chunks else result.content)
        else:
            await self.send_message(update, result.content)

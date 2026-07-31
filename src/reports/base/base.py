"""
Report Base Classes
Abstract base classes for all report types.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReportContext:
    """Context passed to report builders."""
    analysis_date: date
    grouped_data: dict[str, list[dict[str, Any]]]
    outlook: dict[str, Any]
    live_data: list[dict[str, Any]] | None = None
    merged_data: list[dict[str, Any]] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportResult:
    """Result of report generation."""
    content: str
    chunks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseReport(ABC):
    """Abstract base class for all reports."""

    # Class attributes to be overridden
    kind: str = "base"           # Report kind for caching
    name: str = "Base Report"    # Human-readable name
    description: str = ""        # Description for help
    template_name: str = ""      # Jinja2 template file name

    def __init__(self, context: ReportContext):
        self.context = context
        self.logger = logging.getLogger(f"report.{self.kind}")

    @abstractmethod
    def build(self) -> ReportResult:
        """Build the report content. Must be implemented by subclasses."""
        pass

    def get_template_vars(self) -> dict[str, Any]:
        """Get variables for template rendering."""
        return {
            'analysis_date': self.context.analysis_date,
            'grouped': self.context.grouped_data,
            'outlook': self.context.outlook,
            'live_data': self.context.live_data,
            'merged_data': self.context.merged_data,
            **self.context.extra,
        }

    def format_date(self, d: date) -> str:
        """Format date for display."""
        return d.strftime('%d %b %Y')

    def format_number(self, val: Any, decimals: int = 2, na: str = "—") -> str:
        """Format number for display."""
        if val is None:
            return na
        try:
            return format(val, f",.{decimals}f")
        except (ValueError, TypeError):
            return na

    def format_pct(self, val: Any, decimals: int = 2, na: str = "—") -> str:
        """Format percentage for display."""
        if val is None:
            return na
        try:
            return f"{val:+.{decimals}f}%"
        except (ValueError, TypeError):
            return na

    def chunk_message(self, text: str, max_chars: int = 3800) -> list[str]:
        """Split message into chunks under max_chars."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        lines = text.split('\n')
        current = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if current_len + line_len > max_chars and current:
                chunks.append('\n'.join(current))
                current = [line]
                current_len = line_len
            else:
                current.append(line)
                current_len += line_len

        if current:
            chunks.append('\n'.join(current))

        return chunks


class TemplateReport(BaseReport):
    """Report that uses Jinja2 template."""

    def __init__(self, context: ReportContext, template_env=None):
        super().__init__(context)
        self.template_env = template_env

    def build(self) -> ReportResult:
        """Build report using template."""
        if not self.template_env or not self.template_name:
            raise NotImplementedError("TemplateReport requires template_env and template_name")

        template = self.template_env.get_template(self.template_name)
        content = template.render(**self.get_template_vars())

        chunks = self.chunk_message(content)

        return ReportResult(
            content=content,
            chunks=chunks,
            metadata={'template': self.template_name, 'chunks': len(chunks)}
        )


class CompositeReport(BaseReport):
    """Report composed of multiple sections."""

    def __init__(self, context: ReportContext, sections: list[BaseReport] = None):
        super().__init__(context)
        self.sections = sections or []

    def add_section(self, section: BaseReport):
        """Add a section to the composite report."""
        self.sections.append(section)

    def build(self) -> ReportResult:
        """Build report by combining all sections."""
        parts = []
        all_chunks = []

        for section in self.sections:
            result = section.build()
            parts.append(result.content)
            all_chunks.extend(result.chunks)

        content = "\n\n---\n\n".join(parts)

        return ReportResult(
            content=content,
            chunks=all_chunks if all_chunks else self.chunk_message(content),
            metadata={'sections': len(self.sections)}
        )

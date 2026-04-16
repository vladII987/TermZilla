"""Transfer queue UI component."""

import logging
from typing import Optional

from textual.containers import VerticalScroll
from textual.widgets import Label, ProgressBar, Static

from termzilla.services.transfer_engine import TransferJob, TransferStatus

logger = logging.getLogger("termzilla")


class TransferQueueItem(Static):
    """Display a single transfer job."""

    def __init__(self, job: TransferJob, id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.job = job

    def on_mount(self) -> None:
        """Render the transfer item."""
        self._update_display()

    def update_job(self, job: TransferJob) -> None:
        """Update with new job data."""
        self.job = job
        self._update_display()

    def _update_display(self) -> None:
        """Update the visual display."""
        status_icon = {
            TransferStatus.QUEUED: "⏳",
            TransferStatus.IN_PROGRESS: "⬆️",
            TransferStatus.COMPLETED: "✅",
            TransferStatus.FAILED: "❌",
            TransferStatus.CANCELLED: "⛔",
        }.get(self.job.status, "❓")

        progress = 0
        if self.job.size > 0:
            progress = (self.job.transferred / self.job.size) * 100

        speed = ""
        if self.job.status == TransferStatus.IN_PROGRESS and self.job.speed > 0:
            speed = f" - {self._format_speed(self.job.speed)}"

        error_text = ""
        if self.job.status == TransferStatus.FAILED:
            error_text = f"\n[dim]{self.job.error}[/]"

        direction = "↑" if self.job.direction.name == "UPLOAD" else "↓"

        self.update(
            f"{status_icon} {direction} [bold]{self._truncate_name(self.job.source)}[/]{speed}{error_text}"
        )

    @staticmethod
    def _format_speed(speed_bytes: float) -> str:
        """Format transfer speed."""
        if speed_bytes < 1024:
            return f"{speed_bytes:.0f} B/s"
        elif speed_bytes < 1024 * 1024:
            return f"{speed_bytes / 1024:.1f} KB/s"
        else:
            return f"{speed_bytes / (1024 * 1024):.1f} MB/s"

    @staticmethod
    def _truncate_name(path: str, max_length: int = 40) -> str:
        """Truncate long filenames."""
        name = path.split("/")[-1]
        if len(name) > max_length:
            return name[:max_length - 3] + "..."
        return name


class TransferQueue(VerticalScroll):
    """Scrollable container for transfer jobs."""

    DEFAULT_CSS = """
    TransferQueue {
        height: auto;
        max-height: 10;
        border: solid $primary;
        padding: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._items: dict[str, TransferQueueItem] = {}
        self.hidden = True

    def on_mount(self) -> None:
        """Initialize the queue."""
        self.display = False

    def add_job(self, job: TransferJob) -> None:
        """Add a new transfer job to the queue."""
        if not self.display:
            self.display = True
            self.hidden = False

        item = TransferQueueItem(job, id=f"tqi-{job.id}")
        self.mount(item)
        self._items[job.id] = item

    def update_job(self, job: TransferJob) -> None:
        """Update an existing job in the queue."""
        if job.id in self._items:
            self._items[job.id].update_job(job)

    def remove_job(self, job_id: str) -> None:
        """Remove a completed or failed job."""
        if job_id in self._items:
            item = self._items.pop(job_id)
            item.remove()

    def get_active_count(self) -> int:
        """Get number of active transfers."""
        return sum(
            1 for job in self._items.values()
            if job.job.status == TransferStatus.IN_PROGRESS
        )

    def clear_completed(self) -> None:
        """Remove completed jobs from display."""
        completed_ids = [
            job_id for job_id, item in self._items.items()
            if item.job.status in (
                TransferStatus.COMPLETED,
                TransferStatus.FAILED,
                TransferStatus.CANCELLED,
            )
        ]
        for job_id in completed_ids:
            self.remove_job(job_id)

        # Hide queue if empty
        if not self._items:
            self.display = False
            self.hidden = True

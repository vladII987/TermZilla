"""Status bar component."""

from rich.text import Text
from textual.widgets import Static


class StatusBar(Static):
    """Status bar showing connection info and key hints."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        color: $text-muted;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, id: str = "") -> None:
        super().__init__(id=id)
        self.local_path = ""
        self.remote_path = ""
        self.connection_status = "Not connected"
        self.override_text: str = ""  # When set, display this instead of normal status

    def on_mount(self) -> None:
        """Initialize status bar on mount."""
        self._refresh_display()

    def render(self) -> Text:
        """Render the status bar content."""
        if self.override_text:
            return Text(self.override_text)
        return Text(self._build_status())

    def update_status(
        self,
        local_path: str = "",
        remote_path: str = "",
        connection_status: str = "",
    ) -> None:
        if local_path:
            self.local_path = local_path
        if remote_path:
            self.remote_path = remote_path
        if connection_status:
            self.connection_status = connection_status
        self._refresh_display()

    def _build_status(self) -> str:
        """Build the status bar text."""
        return (
            f" {self.connection_status}"
            f" | L:{self._trunc(self.local_path)}"
            f" | R:{self._trunc(self.remote_path)}"
        )

    def _refresh_display(self) -> None:
        """Refresh the status bar."""
        self.refresh()

    @staticmethod
    def _trunc(path: str, n: int = 30) -> str:
        if len(path) <= n:
            return path
        parts = path.split("/")
        return ".../" + "/".join(parts[-2:]) if len(parts) > 2 else path[-n:]

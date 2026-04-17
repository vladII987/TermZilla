"""Main TermZilla Application class."""

from textual.app import App, ComposeResult

from termzilla.screens.main_screen import MainScreen


class TermZillaApp(App):
    """The main TermZilla TUI application."""

    TITLE = "TermZilla"
    CSS_PATH = "termzilla.tcss"

    def on_mount(self) -> None:
        """Called when the app is mounted and ready."""
        self.push_screen(MainScreen())

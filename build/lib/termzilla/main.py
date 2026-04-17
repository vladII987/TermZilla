"""TermZilla application entry point."""

import sys

from termzilla.app import TermZillaApp


def main() -> None:
    """Launch the TermZilla application."""
    app = TermZillaApp()
    app.run()


if __name__ == "__main__":
    main()

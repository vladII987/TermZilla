"""File table component for displaying directory listings."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable

logger = logging.getLogger("termzilla")


@dataclass
class FileEntry:
    """Metadata for a single row in the file table."""
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified: float = 0.0


class FileTable(DataTable):
    """A DataTable for displaying file/directory listings."""

    class Navigate(Message):
        """Posted when the user presses Enter on a row."""
        def __init__(self, table: "FileTable") -> None:
            super().__init__()
            self.table = table

    def __init__(self, id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.current_path: str = str(Path.home())
        self.show_hidden: bool = False
        self._entries: list[FileEntry] = []
        self._marked: set[int] = set()   # row indices marked with Space

    def on_mount(self) -> None:
        self.add_columns("Name", "Size", "Date")
        self.cursor_type = "row"
        self.zebra_stripes = True

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.post_message(FileTable.Navigate(self))
            event.prevent_default()
            event.stop()
        elif event.key == "space":
            self._toggle_mark(self.cursor_row)
            # Advance cursor so next Space marks the next file
            if self.cursor_row < len(self._entries) - 1:
                self.move_cursor(row=self.cursor_row + 1)
            event.prevent_default()
            event.stop()

    # ── Multi-select ──────────────────────────────────────────────────

    def _toggle_mark(self, row: int) -> None:
        """Toggle the mark (Space selection) on a row."""
        if row is None or row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]
        if entry.name == "..":
            return
        if row in self._marked:
            self._marked.discard(row)
        else:
            self._marked.add(row)
        self._redraw_row(row)

    def _redraw_row(self, row: int) -> None:
        """Redraw a single row to reflect its marked state."""
        entry = self._entries[row]
        marked = row in self._marked
        name_cell, size_cell, date_cell = self._render_entry(entry, marked)
        self.update_cell_at(Coordinate(row, 0), name_cell, update_width=False)
        self.update_cell_at(Coordinate(row, 1), size_cell, update_width=False)
        self.update_cell_at(Coordinate(row, 2), date_cell, update_width=False)

    def _render_entry(self, entry: FileEntry, marked: bool) -> tuple:
        """Return (name, size, date) cells for an entry."""
        modified = (
            datetime.fromtimestamp(entry.modified).strftime("%y-%m-%d %H:%M")
            if entry.modified else ""
        )
        prefix = "[#888888]►[/] " if marked else "  "

        if entry.name == "..":
            return "[#b0b0b0 bold]..[/]", "[#555555]<DIR>[/]", ""

        if entry.is_dir:
            return (
                f"{prefix}[#b0b0b0 bold]{entry.name}[/]",
                "[#555555]<DIR>[/]",
                f"[#444444]{modified}[/]",
            )
        return (
            f"{prefix}[#d0d0d0]{entry.name}[/]" if marked else entry.name,
            self._format_size(entry.size),
            f"[#444444]{modified}[/]",
        )

    def get_marked_entries(self) -> list[FileEntry]:
        """Return all marked entries, or just the cursor entry if nothing marked."""
        if self._marked:
            return [self._entries[i] for i in sorted(self._marked)]
        entry = self.get_selected_entry()
        if entry and entry.name != "..":
            return [entry]
        return []

    def clear_marks(self) -> None:
        """Clear all marked rows."""
        rows = list(self._marked)
        self._marked.clear()
        for row in rows:
            if row < len(self._entries):
                self._redraw_row(row)

    # ── Directory loading ─────────────────────────────────────────────

    def load_local_directory(self, path: str) -> None:
        self.clear()
        self._entries.clear()
        self._marked.clear()
        self.current_path = str(Path(path).resolve())

        parent = str(Path(self.current_path).parent)
        self._entries.append(FileEntry(name="..", path=parent, is_dir=True))
        self.add_row("[#b0b0b0 bold]..[/]", "[#555555]<DIR>[/]", "")

        try:
            items = sorted(
                Path(self.current_path).iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
            for item in items:
                if item.name.startswith(".") and not self.show_hidden:
                    continue
                try:
                    stat = item.stat()
                    is_dir = item.is_dir()
                    entry = FileEntry(
                        name=item.name,
                        path=str(item),
                        is_dir=is_dir,
                        size=stat.st_size,
                        modified=stat.st_mtime,
                    )
                    self._entries.append(entry)
                    name_c, size_c, date_c = self._render_entry(entry, False)
                    self.add_row(name_c, size_c, date_c)
                except PermissionError:
                    entry = FileEntry(name=item.name, path=str(item), is_dir=False)
                    self._entries.append(entry)
                    self.add_row(f"[#444444]{item.name}[/]", "[#444444]no access[/]", "")
        except PermissionError:
            pass
        except Exception as e:
            logger.error(f"Error loading directory: {e}")

    def load_remote_directory(self, sftp_client, path: str) -> None:
        from stat import S_ISDIR

        self.clear()
        self._entries.clear()
        self._marked.clear()

        try:
            self.current_path = sftp_client.normalize(path)
            entries = sftp_client.listdir_attr(self.current_path)
            entries_sorted = sorted(entries, key=lambda e: (
                not S_ISDIR(e.st_mode or 0), e.filename.lower()
            ))

            parent = str(Path(self.current_path).parent)
            self._entries.append(FileEntry(name="..", path=parent, is_dir=True))
            self.add_row("[#b0b0b0 bold]..[/]", "[#555555]<DIR>[/]", "")

            for attr in entries_sorted:
                if attr.filename.startswith(".") and not self.show_hidden:
                    continue
                mode = attr.st_mode or 0
                is_dir = S_ISDIR(mode)
                entry_path = f"{self.current_path.rstrip('/')}/{attr.filename}"
                entry = FileEntry(
                    name=attr.filename,
                    path=entry_path,
                    is_dir=is_dir,
                    size=attr.st_size or 0,
                    modified=attr.st_mtime or 0,
                )
                self._entries.append(entry)
                name_c, size_c, date_c = self._render_entry(entry, False)
                self.add_row(name_c, size_c, date_c)

        except Exception as e:
            logger.error(f"Error loading remote directory: {e}")

    def load_ftp_directory(self, ftp_fs, path: str) -> None:
        """Load directory listing from an FtpFileSystem."""
        self.clear()
        self._entries.clear()
        self._marked.clear()

        try:
            self.current_path = ftp_fs.change_directory(path)
        except Exception:
            self.current_path = path

        parent = str(Path(self.current_path).parent)
        self._entries.append(FileEntry(name="..", path=parent, is_dir=True))
        self.add_row("[#b0b0b0 bold]..[/]", "[#555555]<DIR>[/]", "")

        try:
            for entry in ftp_fs.list_directory(self.current_path):
                fe = FileEntry(
                    name=entry["name"],
                    path=entry["path"],
                    is_dir=entry["is_dir"],
                    size=entry.get("size", 0),
                    modified=entry.get("modified", 0.0),
                )
                self._entries.append(fe)
                name_c, size_c, date_c = self._render_entry(fe, False)
                self.add_row(name_c, size_c, date_c)
        except Exception as e:
            logger.error(f"Error loading FTP directory: {e}")

    # ── Accessors ─────────────────────────────────────────────────────

    def get_selected_entry(self) -> Optional[FileEntry]:
        row = self.cursor_row
        if row is None or row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def get_selected_path(self) -> Optional[str]:
        entry = self.get_selected_entry()
        return entry.path if entry else None

    def is_selected_directory(self) -> bool:
        entry = self.get_selected_entry()
        return entry.is_dir if entry else False

    def get_selected_name(self) -> Optional[str]:
        entry = self.get_selected_entry()
        return entry.name if entry else None

    def toggle_hidden_files(self) -> None:
        self.show_hidden = not self.show_hidden

    @staticmethod
    def _format_size(size_bytes) -> str:
        try:
            size_bytes = int(size_bytes)
        except (ValueError, TypeError):
            return "-"
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.0f} {unit}" if unit == "B" else f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

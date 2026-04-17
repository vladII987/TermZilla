"""Main screen — single screen with inline connect toolbar."""

import asyncio
import logging
import time
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Label, Select, Static

from termzilla.components.file_table import FileTable
from termzilla.components.status_bar import StatusBar
from termzilla.config import history as conn_history
from termzilla.services.connection_manager import ConnectionManager, ConnectionError
from termzilla.services.ftp_manager import FtpFileSystem, connect_ftp
from termzilla.services.file_operations import LocalFileSystem, RemoteFileSystem
from termzilla.services.transfer_engine import TransferEngine
from termzilla.utils.validators import (
    validate_host,
    validate_port,
    validate_username,
)

logger = logging.getLogger("termzilla")


class MainScreen(Screen):
    """Single-screen dual-pane file browser with inline connect toolbar."""

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("f5", "upload", "Upload"),
        ("f6", "download", "Download"),
        ("f3", "copy_file", "Copy"),
        ("f4", "move_file", "Move"),
        ("f9", "paste", "Paste"),
        ("f7", "new_dir", "New Dir"),
        ("f8", "connect", "Connect"),
        ("tab", "switch_pane", "Switch"),
    ]

    def compose(self) -> ComposeResult:
        # Connection toolbar
        with Horizontal(id="connect-toolbar"):
            with Vertical(classes="conn-field"):
                yield Label("Host", classes="conn-label")
                yield Input(placeholder="192.168.1.100", id="inp-host", classes="conn-input")
            with Vertical(classes="conn-field"):
                yield Label("Username", classes="conn-label")
                yield Input(placeholder="admin", id="inp-user", classes="conn-input")
            with Vertical(classes="conn-field"):
                yield Label("Password", classes="conn-label")
                yield Input(placeholder="", password=True, id="inp-pass", classes="conn-input")
            with Vertical(classes="conn-field conn-field-port"):
                yield Label("Port", classes="conn-label")
                yield Input(placeholder="22", value="22", id="inp-port", classes="conn-input")
            with Vertical(classes="conn-field conn-field-proto"):
                yield Label("Protocol", classes="conn-label")
                yield Select(
                    [("SFTP", "sftp"), ("FTP", "ftp"), ("FTPS", "ftps")],
                    value="sftp",
                    id="inp-protocol",
                    classes="conn-proto",
                )
            yield Button("CONNECT", id="btn-connect", classes="conn-btn")

        # Status log
        yield Static("", id="status-log")

        # Path bar (above dual panes)
        with Horizontal(id="path-bar"):
            yield Static("", id="local-path-label")
            yield Static("", id="remote-path-label")

        # Dual-pane browser
        with Horizontal(id="browser-layout"):
            with Vertical(id="local-pane"):
                yield FileTable(id="local-table")
            with Vertical(id="remote-pane"):
                yield Static("  Press F8 to connect", id="remote-placeholder")
                yield FileTable(id="remote-table")

        # Transfer queue section
        yield Static(" Transfer Queue:", id="queue-header")
        yield Static("", id="progress-bar")

        # Status bar (used only in prompt mode for copy/move/new_dir)
        yield StatusBar(id="status-bar")

        # Key hints
        yield Static(
            "[#444444] F3[/][#707070] Copy  [/]"
            "[#444444] F4[/][#707070] Cut  [/]"
            "[#444444] F9[/][#707070] Paste  [/]"
            "[#444444] F5[/][#707070] Upload  [/]"
            "[#444444] F6[/][#707070] Download  [/]"
            "[#444444] F7[/][#707070] NewDir  [/]"
            "[#444444] F8[/][#707070] Connect  [/]"
            "[#444444] Tab[/][#707070] Switch  [/]"
            "[#444444] Del[/][#707070] Delete  [/]"
            "[#444444] ^C[/][#707070] Quit[/]",
            id="key-hints",
        )

    def on_mount(self) -> None:
        self._prompt_mode = None  # None | "new_dir"
        self._prompt_buffer = ""
        self._prompt_source_path = None
        self._message = ""
        self._status_log_lines: list[str] = []
        self._clipboard: list = []         # FileEntry objects
        self._clipboard_op: str = ""       # "copy" or "move"
        self._clipboard_fs_type: str = ""  # "local" or "remote"
        self._history: list[dict] = conn_history.load()
        self._history_idx: int = -1        # -1 = not cycling
        self._protocol: str = "sftp"
        self._ftp_conn = None
        self._connected = False

        self.connection_manager = ConnectionManager()
        self.local_fs = LocalFileSystem()
        self.remote_fs = None
        self.transfer_engine = None

        self.local_table = self.query_one("#local-table", FileTable)
        self.remote_table = self.query_one("#remote-table", FileTable)
        self.placeholder = self.query_one("#remote-placeholder", Static)
        self.status_bar = self.query_one("#status-bar", StatusBar)
        self.progress_bar = self.query_one("#progress-bar", Static)
        self.progress_bar.update("")

        self._refresh_local()
        self.remote_table.display = False
        self._focused_pane = "local"
        self._refresh_status_bar()
        self._update_pane_styles()
        self.query_one("#inp-host", Input).focus()

    # ── Status log ────────────────────────────────────────────────────

    def _log_status(self, msg: str) -> None:
        self._status_log_lines.append(f" Status: {msg}")
        if len(self._status_log_lines) > 4:
            self._status_log_lines = self._status_log_lines[-4:]
        self.query_one("#status-log", Static).update(
            "\n".join(self._status_log_lines)
        )

    # ── Path bar ──────────────────────────────────────────────────────

    def _refresh_path_bar(self) -> None:
        local = self.local_fs.get_current_path()
        remote = self.remote_fs.get_current_path() if self.remote_fs else ""
        self.query_one("#local-path-label", Static).update(f" Local: {local}")
        self.query_one("#remote-path-label", Static).update(
            f" Remote: {remote}" if remote else " Remote: not connected"
        )

    def _update_pane_styles(self) -> None:
        local_label = self.query_one("#local-path-label", Static)
        remote_label = self.query_one("#remote-path-label", Static)
        local_pane = self.query_one("#local-pane")
        remote_pane = self.query_one("#remote-pane")
        if self._focused_pane == "local":
            local_label.add_class("pane-active")
            local_pane.add_class("pane-active")
            remote_label.remove_class("pane-active")
            remote_pane.remove_class("pane-active")
        else:
            remote_label.add_class("pane-active")
            remote_pane.add_class("pane-active")
            local_label.remove_class("pane-active")
            local_pane.remove_class("pane-active")

    # ── Prompt helpers ────────────────────────────────────────────────

    def _enter_prompt(self, mode: str, source_path: str = "") -> None:
        self._prompt_mode = mode
        self._prompt_buffer = ""
        self._prompt_source_path = source_path
        self._message = ""
        self._refresh_status_bar()

    def _exit_prompt(self) -> None:
        self._prompt_mode = None
        self._prompt_buffer = ""
        self._prompt_source_path = None
        self._message = ""
        self._refresh_status_bar()

    # ── Status bar ────────────────────────────────────────────────────

    def _refresh_status_bar(self) -> None:
        self._refresh_path_bar()

        if self._prompt_mode == "new_dir":
            mode_labels = {"new_dir": "New dir:"}
            label = mode_labels[self._prompt_mode]
            src_info = ""
            if self._prompt_source_path:
                src_info = f" ({Path(self._prompt_source_path).name})"
            self.status_bar.override_text = (
                f" [bold]{label}[/] {self._prompt_buffer}{src_info}  [dim]Enter=ok  Esc=cancel[/]"
            )
            self.status_bar.refresh()
            return

        if self._message:
            self._log_status(self._message)
            self._message = ""

        self.status_bar.override_text = ""
        self.status_bar.refresh()

    # ── Connect / disconnect ──────────────────────────────────────────

    def _do_connect(self) -> None:
        if self._connected:
            self._do_disconnect()
            return

        host = self.query_one("#inp-host", Input).value.strip()
        port_s = self.query_one("#inp-port", Input).value.strip() or "22"
        user = self.query_one("#inp-user", Input).value.strip()
        password = self.query_one("#inp-pass", Input).value

        for fn, val in [
            (validate_host, host),
            (validate_port, port_s),
            (validate_username, user),
        ]:
            ok, err = fn(val)
            if not ok:
                self._log_status(f"Error: {err}")
                return

        if not password:
            self._log_status("Error: password is required")
            return

        proto_sel = self.query_one("#inp-protocol", Select)
        protocol = str(proto_sel.value) if proto_sel.value != Select.BLANK else "sftp"
        self._log_status(f"Connecting to {host}:{port_s} ({protocol.upper()})...")

        try:
            if protocol == "sftp":
                self.connection_manager.connect(
                    host=host, port=int(port_s), username=user, password=password, key_path=None,
                )
                sftp = self.connection_manager.get_sftp()
                self.remote_fs = RemoteFileSystem(sftp)
                self.transfer_engine = TransferEngine(sftp)
                self._ftp_conn = None
            else:
                ftp = connect_ftp(host, int(port_s), user, password, protocol)
                self._ftp_conn = ftp
                self.remote_fs = FtpFileSystem(ftp)
                self.transfer_engine = None

            self._protocol = protocol
            self._connected = True
            conn_history.save(host, user, port_s, protocol)
            self._history = conn_history.load()
            self._history_idx = -1
            self.placeholder.display = False
            self.remote_table.display = True
            self._refresh_remote()
            self._log_status("Connection established, logged in")
            self._log_status(f"Connected to {host}")
            self._update_connect_button(connected=True)
            self._focused_pane = "local"
            self.local_table.focus()
            self._update_pane_styles()
        except (ConnectionError, Exception) as e:
            self._log_status(f"Connection error: {e}")
            logger.error(f"Connection failed: {e}")

        self._refresh_status_bar()

    def _do_disconnect(self) -> None:
        try:
            self.connection_manager.disconnect()
        except Exception:
            pass
        try:
            if self._ftp_conn:
                self._ftp_conn.quit()
        except Exception:
            pass
        self._ftp_conn = None
        self._protocol = "sftp"
        self._connected = False
        self.remote_fs = None
        self.transfer_engine = None
        self.remote_table.display = False
        self.placeholder.display = True
        self.remote_table.clear()
        self._log_status("Disconnected")
        self._update_connect_button(connected=False)
        self._refresh_status_bar()

    def _update_connect_button(self, connected: bool) -> None:
        btn = self.query_one("#btn-connect", Button)
        if connected:
            btn.label = "DISCONNECT"
            btn.add_class("conn-btn-disconnect")
            btn.remove_class("conn-btn")
        else:
            btn.label = "CONNECT"
            btn.add_class("conn-btn")
            btn.remove_class("conn-btn-disconnect")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-connect":
            self._do_connect()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        connect_inputs = {"inp-host", "inp-user", "inp-pass", "inp-port"}
        if event.input.id in connect_inputs:
            self._do_connect()

    # ── Actions ───────────────────────────────────────────────────────

    def action_switch_pane(self) -> None:
        focused = self.focused
        connect_order = ["inp-host", "inp-user", "inp-pass", "inp-port"]

        # Cycle through connect inputs
        if isinstance(focused, Input) and focused.id in connect_order:
            idx = connect_order.index(focused.id)
            if idx < len(connect_order) - 1:
                self.query_one(f"#{connect_order[idx + 1]}", Input).focus()
            else:
                # Last input (port) → Protocol selector
                self.query_one("#inp-protocol", Select).focus()
            return

        # Protocol selector → Connect button
        if isinstance(focused, Select) and focused.id == "inp-protocol":
            self.query_one("#btn-connect", Button).focus()
            return

        # Connect button → file browser
        if isinstance(focused, Button) and focused.id == "btn-connect":
            self.local_table.focus()
            self._focused_pane = "local"
            self._update_pane_styles()
            return

        if not self._connected:
            self.query_one("#inp-host", Input).focus()
            return
        if self._focused_pane == "local":
            self._focused_pane = "remote"
            self.remote_table.focus()
        else:
            self._focused_pane = "local"
            self.local_table.focus()
        self._update_pane_styles()

    def action_quit(self) -> None:
        try:
            if self._connected:
                self.connection_manager.disconnect()
        except Exception:
            pass
        self.app.exit()

    def action_connect(self) -> None:
        if self._connected:
            self._do_disconnect()
        else:
            self.query_one("#inp-host", Input).focus()

    def action_copy_file(self) -> None:
        table = self.local_table if self._focused_pane == "local" else self.remote_table
        entries = table.get_marked_entries()
        if not entries:
            self._message = "Nothing selected"
            self._refresh_status_bar()
            return
        self._clipboard = entries
        self._clipboard_op = "copy"
        self._clipboard_fs_type = self._focused_pane
        label = entries[0].name if len(entries) == 1 else f"{len(entries)} files"
        self._message = f"Copied {label} — press F9 to paste"
        self._refresh_status_bar()

    def action_move_file(self) -> None:
        table = self.local_table if self._focused_pane == "local" else self.remote_table
        entries = table.get_marked_entries()
        if not entries:
            self._message = "Nothing selected"
            self._refresh_status_bar()
            return
        self._clipboard = entries
        self._clipboard_op = "move"
        self._clipboard_fs_type = self._focused_pane
        label = entries[0].name if len(entries) == 1 else f"{len(entries)} files"
        self._message = f"Cut {label} — press F9 to paste"
        self._refresh_status_bar()

    def action_paste(self) -> None:
        if not self._clipboard:
            self._message = "Clipboard empty — use F3 (copy) or F4 (cut) first"
            self._refresh_status_bar()
            return

        dest_pane = self._focused_pane
        dest_fs = self.local_fs if dest_pane == "local" else self.remote_fs

        if dest_fs is None:
            self._message = "Not connected"
            self._refresh_status_bar()
            return

        dest_dir = dest_fs.get_current_path()
        src_type = self._clipboard_fs_type
        op = self._clipboard_op
        entries = list(self._clipboard)
        cross_fs = (src_type != dest_pane)

        if cross_fs and not self._connected:
            self._message = "Not connected — cannot transfer between local and remote"
            self._refresh_status_bar()
            return

        label = entries[0].name if len(entries) == 1 else f"{len(entries)} files"
        verb = "Copying" if op == "copy" else "Moving"
        self._show_progress(f"{verb}: {label}")

        # Clear clipboard before async work
        self._clipboard = []
        self._clipboard_op = ""
        self._clipboard_fs_type = ""

        total_count = len(entries)

        async def do():
            try:
                for i, entry in enumerate(entries, 1):
                    dest_path = f"{dest_dir.rstrip('/')}/{entry.name}"
                    file_label = f"{entry.name} ({i}/{total_count})" if total_count > 1 else entry.name
                    self._show_progress(f"{verb}: {file_label}")
                    if not cross_fs:
                        fs = self.local_fs if src_type == "local" else self.remote_fs
                        loop = asyncio.get_event_loop()
                        if op == "copy":
                            await loop.run_in_executor(
                                None,
                                lambda e=entry, d=dest_path: fs.copy(e.path, d, callback=self._on_transfer_progress),
                            )
                        else:
                            await loop.run_in_executor(
                                None, lambda e=entry, d=dest_path: fs.rename(e.path, d)
                            )
                    else:
                        if src_type == "local":
                            await self._upload_file(entry.path, dest_path)
                            if op == "move":
                                self.local_fs.delete(entry.path)
                        else:
                            await self._download_file(entry.path, dest_path)
                            if op == "move":
                                self.remote_fs.delete(entry.path)
                    # Refresh destination pane after each file
                    if dest_pane == "local":
                        self._refresh_local()
                    else:
                        self._refresh_remote()
                done_verb = "Copied" if op == "copy" else "Moved"
                self._message = f"{done_verb} {label} → {dest_dir}"
            except Exception as e:
                self._message = f"Paste error: {e}"
                logger.error(f"Paste failed: {e}")
            finally:
                self._hide_progress()
                self._refresh_local()
                if self._connected:
                    self._refresh_remote()
                self._refresh_status_bar()

        self.run_worker(do())

    def action_new_dir(self) -> None:
        self._enter_prompt("new_dir")

    # ── Progress bar ──────────────────────────────────────────────────

    def _show_progress(self, label: str) -> None:
        self._progress_label = label
        self._transfer_start_time = time.time()
        self._draw_progress(0, 0)

    def _hide_progress(self) -> None:
        self.progress_bar.update("")
        self._transfer_start_time = None

    def _format_size(self, size: float) -> str:
        for unit in ["B", "K", "M", "G", "T"]:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}P"

    def _format_duration(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds // 60)}m {int(seconds % 60)}s"
        else:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"

    def _on_transfer_progress(self, transferred: int, total: int) -> None:
        self.app.call_from_thread(self._draw_progress, transferred, total)

    def _draw_progress(self, transferred: int, total: int) -> None:
        bar_width = 20
        if total > 0:
            pct = min(100, int(transferred * 100 / total))
            filled = int(bar_width * pct / 100)
            bar = "=" * filled + ">" + " " * max(0, bar_width - filled - 1)
            mb_done = transferred / 1024 / 1024
            mb_total = total / 1024 / 1024
            speed = 0
            if hasattr(self, "_transfer_start_time") and self._transfer_start_time:
                elapsed = time.time() - self._transfer_start_time
                if elapsed > 0:
                    speed = transferred / elapsed
            if speed > 0:
                speed_str = self._format_size(speed) + "/s"
                remaining = (total - transferred) / speed if speed > 0 else 0
                eta_str = self._format_duration(remaining)
                text = f" [{bar}] {pct:>3}%  {self._progress_label} ({speed_str} | ETA {eta_str})"
            else:
                text = f" [{bar}] {pct:>3}%  {self._progress_label} | {mb_done:.1f}MB / {mb_total:.1f}MB"
        else:
            bar = " " * bar_width
            text = f" [{bar}]   0%  {self._progress_label}"
        self.progress_bar.update(text)
        self.progress_bar.refresh()

    # ── Transfer ─────────────────────────────────────────────────────

    def action_upload(self) -> None:
        if not self._connected:
            self._message = "Not connected"
            self._refresh_status_bar()
            return
        if self._focused_pane != "local":
            return
        entries = self.local_table.get_marked_entries()
        if not entries:
            return

        remote_base = self.remote_fs.get_current_path()
        names = ", ".join(e.name for e in entries[:3])
        if len(entries) > 3:
            names += f" +{len(entries) - 3} more"
        self._show_progress(f"upload: {names}")

        async def do():
            try:
                for entry in entries:
                    dest = f"{remote_base.rstrip('/')}/{entry.name}"
                    await self._upload_file(entry.path, dest)
                self.local_table.clear_marks()
                self._message = f"Uploaded {len(entries)} file(s)"
            except Exception as e:
                self._message = f"Upload error: {e}"
                logger.error(f"Upload failed: {e}")
            finally:
                self._hide_progress()
                self._refresh_remote()
                self._refresh_status_bar()

        self.run_worker(do())

    def action_download(self) -> None:
        if not self._connected:
            self._message = "Not connected"
            self._refresh_status_bar()
            return
        if self._focused_pane != "remote":
            return
        entries = self.remote_table.get_marked_entries()
        if not entries:
            return

        local_base = self.local_fs.get_current_path()
        names = ", ".join(e.name for e in entries[:3])
        if len(entries) > 3:
            names += f" +{len(entries) - 3} more"
        self._show_progress(f"download: {names}")

        async def do():
            try:
                for entry in entries:
                    dest = f"{local_base.rstrip('/')}/{entry.name}"
                    await self._download_file(entry.path, dest)
                self.remote_table.clear_marks()
                self._message = f"Downloaded {len(entries)} file(s)"
            except Exception as e:
                self._message = f"Download error: {e}"
                logger.error(f"Download failed: {e}")
            finally:
                self._hide_progress()
                self._refresh_local()
                self._refresh_status_bar()

        self.run_worker(do())

    # ── Navigation ───────────────────────────────────────────────────

    def _navigate_into(self) -> None:
        table = self.local_table if self._focused_pane == "local" else self.remote_table
        fs = self._get_fs()
        if not table.is_selected_directory():
            return
        path = table.get_selected_path()
        if not path:
            return
        try:
            fs.change_directory(path)
            self._refresh_pane()
            self._refresh_status_bar()
        except Exception as e:
            self._message = f"Error: {e}"
            self._refresh_status_bar()

    def _navigate_up(self) -> None:
        fs = self._get_fs()
        parent = str(Path(fs.get_current_path()).parent)
        try:
            fs.change_directory(parent)
            self._refresh_pane()
            self._refresh_status_bar()
        except Exception as e:
            self._message = f"Error: {e}"
            self._refresh_status_bar()

    def _get_fs(self):
        return self.local_fs if self._focused_pane == "local" else self.remote_fs

    def _refresh_pane(self):
        if self._focused_pane == "local":
            self._refresh_local()
        else:
            self._refresh_remote()

    def _refresh_local(self) -> None:
        try:
            self.local_table.load_local_directory(self.local_fs.get_current_path())
        except Exception as e:
            logger.error(f"Local refresh error: {e}")

    def _refresh_remote(self) -> None:
        if not self.remote_fs:
            return
        try:
            if isinstance(self.remote_fs, FtpFileSystem):
                self.remote_table.load_ftp_directory(self.remote_fs, self.remote_fs.get_current_path())
            else:
                sftp = self.connection_manager.get_sftp()
                self.remote_table.load_remote_directory(sftp, self.remote_fs.get_current_path())
        except Exception as e:
            logger.error(f"Remote refresh error: {e}")

    async def _upload_file(self, local_path: str, remote_path: str) -> None:
        loop = asyncio.get_event_loop()
        if self.transfer_engine:
            await self.transfer_engine.upload(local_path, remote_path, callback=self._on_transfer_progress)
        else:
            await loop.run_in_executor(
                None, lambda: self.remote_fs.upload(local_path, remote_path, callback=self._on_transfer_progress)
            )

    async def _download_file(self, remote_path: str, local_path: str) -> None:
        loop = asyncio.get_event_loop()
        if self.transfer_engine:
            await self.transfer_engine.download(remote_path, local_path, callback=self._on_transfer_progress)
        else:
            await loop.run_in_executor(
                None, lambda: self.remote_fs.download(remote_path, local_path, callback=self._on_transfer_progress)
            )

    # ── Delete / hidden ──────────────────────────────────────────────

    def _delete_selected(self) -> None:
        fs = self._get_fs()
        table = self.local_table if self._focused_pane == "local" else self.remote_table
        name = table.get_selected_name()
        if not name or name == "..":
            return
        path = table.get_selected_path()
        if not path:
            return
        try:
            fs.delete(path)
            self._refresh_pane()
            self._message = f"Deleted {name}"
        except Exception as e:
            self._message = f"Delete error: {e}"
        self._refresh_status_bar()

    def _toggle_hidden(self) -> None:
        if self._focused_pane == "local":
            self.local_table.toggle_hidden_files()
            self._refresh_local()
        else:
            self.remote_table.toggle_hidden_files()
            self._refresh_remote()

    # ── Prompt execution ─────────────────────────────────────────────

    def _execute_new_dir(self) -> None:
        name = self._prompt_buffer.strip()
        if not name:
            self._message = "Empty name"
            self._exit_prompt()
            return
        fs = self._get_fs()
        dest = f"{fs.get_current_path()}/{name}"
        fs.create_directory(dest)
        self._refresh_pane()
        self._message = f"Created {name}"
        self._exit_prompt()

    # ── FileTable Enter navigation ────────────────────────────────────

    def on_file_table_navigate(self, event: FileTable.Navigate) -> None:
        if self._prompt_mode:
            return
        if event.table is self.local_table:
            pane = "local"
            table = self.local_table
            fs = self.local_fs
        else:
            pane = "remote"
            table = self.remote_table
            fs = self.remote_fs
        if fs is None:
            return
        if not table.is_selected_directory():
            return
        path = table.get_selected_path()
        if not path:
            return
        try:
            fs.change_directory(path)
            if pane == "local":
                self._refresh_local()
            else:
                self._refresh_remote()
            self._refresh_status_bar()
        except Exception as e:
            self._message = f"Error: {e}"
            self._refresh_status_bar()

    # ── Key handling ─────────────────────────────────────────────────

    def on_key(self, event) -> None:
        focused = self.focused

        # When a connect Input is focused
        if isinstance(focused, Input):
            connect_input_ids = {"inp-host", "inp-user", "inp-pass", "inp-port"}
            if focused.id in connect_input_ids:
                # Up/Down cycles through connection history
                if event.key in ("up", "down") and self._history:
                    if event.key == "up":
                        self._history_idx = min(self._history_idx + 1, len(self._history) - 1)
                    else:
                        self._history_idx = max(self._history_idx - 1, -1)
                    if self._history_idx >= 0:
                        entry = self._history[self._history_idx]
                        self.query_one("#inp-host", Input).value = entry.get("host", "")
                        self.query_one("#inp-user", Input).value = entry.get("user", "")
                        self.query_one("#inp-port", Input).value = entry.get("port", "22")
                        self.query_one("#inp-protocol", Select).value = entry.get("protocol", "sftp")
                    else:
                        self.query_one("#inp-host", Input).value = ""
                        self.query_one("#inp-user", Input).value = ""
                        self.query_one("#inp-port", Input).value = "22"
                        self.query_one("#inp-protocol", Select).value = "sftp"
                    event.prevent_default()
                    event.stop()
                    return
                _MISSING = {
                    "full_stop": ".", "period": ".", "minus": "-",
                    "underscore": "_", "colon": ":",
                }
                ch = _MISSING.get(event.key)
                if ch is not None:
                    focused.insert_text_at_cursor(ch)
                    event.prevent_default()
                    event.stop()
            return

        key = event.key

        # Prompt mode (new_dir)
        if self._prompt_mode:
            if key == "enter":
                if self._prompt_mode == "new_dir":
                    self._execute_new_dir()
                event.stop()
                return
            elif key == "escape":
                self._exit_prompt()
                event.stop()
                return
            elif key == "backspace":
                self._prompt_buffer = self._prompt_buffer[:-1]
                self._refresh_status_bar()
                event.stop()
                return
            else:
                ch = getattr(event, "character", None)
                if not ch and event.key in ("period", "full_stop", "keypad_decimal"):
                    ch = "."
                if ch and ch.isprintable():
                    self._prompt_buffer += ch
                    self._refresh_status_bar()
                    event.stop()
                    return
                return

        # Normal mode
        if key == "backspace":
            self._navigate_up()
            event.stop()
        elif key == "delete":
            self._delete_selected()
            event.stop()
        elif key == "h":
            self._toggle_hidden()
            event.stop()

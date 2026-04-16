"""Connect dialog — modal popup for SSH connection details."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static


class ConnectDialog(ModalScreen):
    """Modal dialog for entering SSH connection details."""

    DEFAULT_CSS = """
    ConnectDialog {
        align: center middle;
    }

    #connect-dialog {
        width: 60;
        height: auto;
        border: solid #00ff88;
        background: #0a0a1a;
        padding: 1 2;
    }

    #connect-title {
        text-align: center;
        color: #00ff88;
        margin-bottom: 1;
    }

    .field-label {
        color: #888888;
        height: 1;
        margin-top: 1;
    }

    .connect-input {
        background: #1a1a2e;
        border: solid #444444;
        color: #c0c0c0;
        height: 3;
    }

    .connect-input:focus {
        border: solid #00ff88;
        color: #ffffff;
    }

    #button-row {
        margin-top: 1;
        height: auto;
        align: center middle;
    }

    #btn-connect {
        background: #00ff88;
        color: #1a1a2e;
        border: none;
        margin-right: 2;
    }

    #btn-connect:hover {
        background: #00cc66;
    }

    #btn-cancel {
        background: #333355;
        color: #c0c0c0;
        border: none;
    }

    #btn-cancel:hover {
        background: #444466;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="connect-dialog"):
            yield Static(" Connect to Remote Server", id="connect-title")
            yield Label("Host / IP address", classes="field-label")
            yield Input(placeholder="192.168.1.1", id="inp-host", classes="connect-input")
            yield Label("Port", classes="field-label")
            yield Input(placeholder="22", value="22", id="inp-port", classes="connect-input")
            yield Label("Username", classes="field-label")
            yield Input(placeholder="root", id="inp-user", classes="connect-input")
            yield Label("Password", classes="field-label")
            yield Input(placeholder="(leave empty if using SSH key)", password=True, id="inp-pass", classes="connect-input")
            yield Label("SSH Key path (optional)", classes="field-label")
            yield Input(placeholder="/home/user/.ssh/id_rsa", id="inp-key", classes="connect-input")
            with Horizontal(id="button-row"):
                yield Button("Connect", id="btn-connect", variant="success")
                yield Button("Cancel", id="btn-cancel")

    def on_mount(self) -> None:
        self.app.call_after_refresh(self.query_one("#inp-host", Input).focus)

    def on_key(self, event) -> None:
        """Explicitly handle keys whose event.character is None in some terminals."""
        _MISSING = {
            "full_stop": ".",
            "period": ".",
            "minus": "-",
            "underscore": "_",
            "colon": ":",
        }
        ch = _MISSING.get(event.key)
        if ch is None:
            return
        focused = self.focused
        if isinstance(focused, Input):
            focused.insert_text_at_cursor(ch)
            event.prevent_default()
            event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
            return
        if event.button.id == "btn-connect":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Move to next field on Enter, or submit on last field."""
        fields = ["inp-host", "inp-port", "inp-user", "inp-pass", "inp-key"]
        current_id = event.input.id
        if current_id in fields:
            idx = fields.index(current_id)
            if idx < len(fields) - 1:
                self.query_one(f"#{fields[idx + 1]}", Input).focus()
            else:
                self._submit()

    def _submit(self) -> None:
        host = self.query_one("#inp-host", Input).value.strip()
        port = self.query_one("#inp-port", Input).value.strip() or "22"
        user = self.query_one("#inp-user", Input).value.strip()
        password = self.query_one("#inp-pass", Input).value
        key_path = self.query_one("#inp-key", Input).value.strip()
        self.dismiss((host, port, user, password, key_path))

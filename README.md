# TermZilla

A Terminal User Interface (TUI) file transfer client built with Python and Textual.

## Features

- **Dual-pane file browser** - Navigate local and remote file systems side-by-side
- **SFTP support** - Secure file transfers over SSH
- **Password & SSH Key authentication** - Connect with your preferred auth method
- **Async transfers** - Non-blocking uploads and downloads with progress tracking
- **Keyboard-driven** - Fast, efficient workflow without mouse dependency
- **Cross-platform** - Works on Linux, macOS, and Windows

## Installation

```bash
pip install .
```

Or for development:

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
termzilla
```

This will launch the connection screen where you can enter your server details.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `F5` | Upload selected file(s) to remote |
| `F6` | Download selected file(s) from remote |
| `Enter` | Navigate into directory |
| `Backspace` | Go up one directory |
| `Delete` | Delete selected file/dir |
| `F7` | Create new directory |
| `R` | Rename selected file/dir |
| `F1` / `?` | Show help |
| `Esc` | Go back / Cancel |

## Requirements

- Python 3.10+
- An SSH/SFTP server for remote connections

## License

MIT License - see LICENSE for details.

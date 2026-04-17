#!/bin/bash
# TermZilla Universal Installer
# Supports: Debian/Ubuntu, Fedora/RHEL/CentOS, Arch, openSUSE, Alpine
# Usage: sudo bash install.sh

set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${GREEN}[termzilla]${NC} $*"; }
warn() { echo -e "${YELLOW}[warn]${NC} $*"; }
fail() { echo -e "${RED}[error]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/usr/lib/termzilla"
BIN="/usr/bin/termzilla"
VERSION=$(grep '^version' "$SCRIPT_DIR/pyproject.toml" | head -1 | sed 's/.*= *"\(.*\)"/\1/')

[[ $EUID -ne 0 ]] && fail "Run with sudo: sudo bash $0"

# ── Detect package manager ───────────────────────────────────────────
detect_pkg_mgr() {
    command -v apt-get &>/dev/null && echo apt   && return
    command -v dnf     &>/dev/null && echo dnf   && return
    command -v yum     &>/dev/null && echo yum   && return
    command -v pacman  &>/dev/null && echo pacman && return
    command -v zypper  &>/dev/null && echo zypper && return
    command -v apk     &>/dev/null && echo apk   && return
    echo none
}

PKG_MGR=$(detect_pkg_mgr)
info "Detected package manager: ${PKG_MGR:-none}"

# ── Ensure Python 3.10+ ──────────────────────────────────────────────
ensure_python() {
    if command -v python3 &>/dev/null; then
        PY_VER=$(python3 -c 'import sys; print(sys.version_info >= (3,10))')
        [[ "$PY_VER" == "True" ]] && return
    fi
    info "Installing Python 3.10+..."
    case "$PKG_MGR" in
        apt)    apt-get install -y python3 python3-pip python3-venv ;;
        dnf)    dnf install -y python3 python3-pip ;;
        yum)    yum install -y python3 python3-pip ;;
        pacman) pacman -S --noconfirm python python-pip ;;
        zypper) zypper install -y python3 python3-pip ;;
        apk)    apk add --no-cache python3 py3-pip ;;
        *)      fail "Could not install Python. Please install Python 3.10+ manually." ;;
    esac
}

# ── Ensure pip ───────────────────────────────────────────────────────
ensure_pip() {
    if command -v pip3 &>/dev/null || command -v pip &>/dev/null; then return; fi
    info "Installing pip..."
    case "$PKG_MGR" in
        apt)    apt-get install -y python3-pip ;;
        dnf)    dnf install -y python3-pip ;;
        yum)    yum install -y python3-pip ;;
        pacman) pacman -S --noconfirm python-pip ;;
        zypper) zypper install -y python3-pip ;;
        apk)    apk add --no-cache py3-pip ;;
        *)      python3 -m ensurepip --upgrade || fail "Could not install pip." ;;
    esac
}

# ── Find pip ─────────────────────────────────────────────────────────
find_pip() {
    command -v pip3 &>/dev/null && echo pip3 && return
    command -v pip  &>/dev/null && echo pip  && return
    python3 -m pip --version &>/dev/null && echo "python3 -m pip" && return
    fail "pip not found after installation"
}

# ── Install ──────────────────────────────────────────────────────────
ensure_python
ensure_pip
PIP=$(find_pip)

info "Installing TermZilla to $INSTALL_DIR ..."
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

$PIP install \
    --target="$INSTALL_DIR" \
    --no-compile \
    --no-warn-script-location \
    --no-cache-dir \
    "$SCRIPT_DIR" 2>&1 | grep -v "^WARNING" || true

# Remove unnecessary pip artifacts
rm -rf "$INSTALL_DIR/bin"
find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$INSTALL_DIR" -name "*.pyc" -delete 2>/dev/null || true

# ── Wrapper script ───────────────────────────────────────────────────
cat > "$BIN" <<'SCRIPT'
#!/bin/bash
PYTHONPATH=/usr/lib/termzilla exec python3 -c \
    "import termzilla.main; termzilla.main.main()" "$@"
SCRIPT
chmod 755 "$BIN"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
printf "${GREEN}║  TermZilla %-5s installed!              ║${NC}\n" "$VERSION"
echo -e "${GREEN}║  Run: termzilla                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"

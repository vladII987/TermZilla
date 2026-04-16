#!/bin/bash
# Build a .deb package for TermZilla
# Usage: ./build-deb.sh [--install]
set -e

VERSION="1.0.0"
PKG_NAME="termzilla"
BUILD_DIR="$HOME/termzilla-deb-build"
DEST_DIR="$(pwd)/dist"
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Building .deb package v${VERSION}..."

# Clean previous build
rm -rf "$BUILD_DIR"

# Create directory structure
DEB_DIR="$BUILD_DIR/$PKG_NAME-$VERSION"
mkdir -p "$DEB_DIR/DEBIAN"
mkdir -p "$DEB_DIR/usr/bin"
mkdir -p "$DEB_DIR/usr/lib/termzilla"

# ── Control file ────────────────────────────────────────────────────
cat > "$DEB_DIR/DEBIAN/control" <<EOF
Package: termzilla
Version: $VERSION
Section: net
Priority: optional
Architecture: all
Depends: python3 (>= 3.10)
Maintainer: TermZilla Contributors
Description: TUI file transfer client (SFTP/FTP) alternative to FileZilla/WinSCP
 A terminal-based file manager with dual-pane layout,
 remote SFTP access, and file transfer capabilities.
EOF

# ── Install Python package into /usr/lib/termzilla ──────────────────
echo "==> Installing Python package into build dir..."

# Use venv pip if available, otherwise try pip3
PIP_CMD=""
if [[ -f "$DIR/.venv/bin/pip" ]]; then
    PIP_CMD="$DIR/.venv/bin/pip"
elif command -v pip3 &>/dev/null; then
    PIP_CMD="pip3"
elif command -v pip &>/dev/null; then
    PIP_CMD="pip"
elif [[ -f /usr/bin/pip3 ]]; then
    PIP_CMD="/usr/bin/pip3"
else
    error "No pip found. Install python3-pip first."
fi

echo "==> Using: $PIP_CMD"
$PIP_CMD install \
    --target="$DEB_DIR/usr/lib/termzilla" \
    --no-compile \
    --no-warn-script-location \
    --no-cache-dir \
    . 2>&1 | grep -v "^WARNING" || true

# Clean up pip cache/metadata we don't need in the deb
rm -rf "$DEB_DIR/usr/lib/termzilla/bin"
rm -rf "$DEB_DIR/usr/lib/termzilla/termzilla.egg-info"
find "$DEB_DIR/usr/lib/termzilla" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$DEB_DIR/usr/lib/termzilla" -type f -name "*.pyc" -delete 2>/dev/null || true

# ── Wrapper script ──────────────────────────────────────────────────
cat > "$DEB_DIR/usr/bin/termzilla" <<'SCRIPT'
#!/bin/bash
PYTHONPATH=/usr/lib/termzilla exec python3 -c \
    "import termzilla.main; termzilla.main.main()" "$@"
SCRIPT
chmod 755 "$DEB_DIR/usr/bin/termzilla"

# ── Build the .deb ─────────────────────────────────────────────────
mkdir -p "$DEST_DIR"
dpkg-deb --build "$DEB_DIR" "$DEST_DIR/termzilla_${VERSION}_all.deb" 2>&1 | tail -1

echo "==> .deb package built: $DEST_DIR/termzilla_${VERSION}_all.deb"

# ── Optional install ───────────────────────────────────────────────
if [[ "$1" == "--install" ]]; then
    echo "==> Installing .deb package..."
    sudo dpkg -i "$DEST_DIR/termzilla_${VERSION}_all.deb" || sudo apt -f install -y
    echo "==> Done! Run 'termzilla' to launch."
fi

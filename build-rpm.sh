#!/bin/bash
# Build an .rpm package for TermZilla
# Requires: rpm-build (sudo dnf install rpm-build / sudo yum install rpm-build)
# Usage: bash build-rpm.sh [--install]
set -e

VERSION="1.0.0"
PKG_NAME="termzilla"
BUILD_DIR="$HOME/termzilla-rpm-build"
DEST_DIR="$(pwd)/dist"
DIR="$(cd "$(dirname "$0")" && pwd)"

command -v rpmbuild &>/dev/null || {
    echo "rpmbuild not found. Install it first:"
    echo "  Fedora/RHEL:  sudo dnf install rpm-build"
    echo "  CentOS:       sudo yum install rpm-build"
    exit 1
}

echo "==> Building .rpm package v${VERSION}..."

# ── Prepare rpmbuild tree ────────────────────────────────────────────
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

STAGE="$BUILD_DIR/stage"
mkdir -p "$STAGE/usr/bin"
mkdir -p "$STAGE/usr/lib/termzilla"

# ── Install Python package into staging dir ──────────────────────────
echo "==> Installing Python package into staging dir..."

PIP_CMD=""
if [[ -f "$DIR/.venv/bin/pip" ]]; then
    PIP_CMD="$DIR/.venv/bin/pip"
elif command -v pip3 &>/dev/null; then PIP_CMD="pip3"
elif command -v pip  &>/dev/null; then PIP_CMD="pip"
else echo "No pip found. Install python3-pip first." && exit 1; fi

echo "==> Using: $PIP_CMD"
$PIP_CMD install \
    --target="$STAGE/usr/lib/termzilla" \
    --no-compile \
    --no-warn-script-location \
    --no-cache-dir \
    "$DIR" 2>&1 | grep -v "^WARNING" || true

rm -rf "$STAGE/usr/lib/termzilla/bin"
find "$STAGE/usr/lib/termzilla" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/usr/lib/termzilla" -name "*.pyc" -delete 2>/dev/null || true

# ── Wrapper script ───────────────────────────────────────────────────
cat > "$STAGE/usr/bin/termzilla" <<'SCRIPT'
#!/bin/bash
PYTHONPATH=/usr/lib/termzilla exec python3 -c \
    "import termzilla.main; termzilla.main.main()" "$@"
SCRIPT
chmod 755 "$STAGE/usr/bin/termzilla"

# ── Create source tarball for rpmbuild ───────────────────────────────
tar -czf "$BUILD_DIR/SOURCES/${PKG_NAME}-${VERSION}.tar.gz" -C "$STAGE" .

# ── Spec file ────────────────────────────────────────────────────────
cat > "$BUILD_DIR/SPECS/${PKG_NAME}.spec" <<EOF
Name:           ${PKG_NAME}
Version:        ${VERSION}
Release:        1%{?dist}
Summary:        Terminal file transfer client (SFTP/FTP/FTPS) — TUI alternative to FileZilla
License:        MIT
BuildArch:      noarch
Requires:       python3 >= 3.10

%description
TermZilla is a terminal-based file transfer client with a dual-pane browser.
Supports SFTP, FTP, and FTPS. Features multi-file selection, clipboard copy/move,
upload/download, and connection history. Keyboard-driven, no mouse required.

%install
tar -xzf %{_sourcedir}/${PKG_NAME}-${VERSION}.tar.gz -C %{buildroot}

%files
/usr/bin/termzilla
/usr/lib/termzilla

%changelog
* $(date "+%a %b %d %Y") TermZilla Contributors <noreply@termzilla> - ${VERSION}-1
- Initial release
EOF

# ── Build RPM ────────────────────────────────────────────────────────
rpmbuild \
    --define "_topdir $BUILD_DIR" \
    --define "_rpmdir $DEST_DIR" \
    --define "buildroot $BUILD_DIR/BUILDROOT" \
    -bb "$BUILD_DIR/SPECS/${PKG_NAME}.spec" 2>&1 | tail -5

RPM_FILE=$(find "$DEST_DIR" -name "${PKG_NAME}-${VERSION}*.rpm" | head -1)
echo "==> .rpm package built: $RPM_FILE"

# ── Optional install ─────────────────────────────────────────────────
if [[ "$1" == "--install" ]]; then
    echo "==> Installing .rpm package..."
    sudo rpm -ivh --force "$RPM_FILE" || sudo dnf install -y "$RPM_FILE"
    echo "==> Done! Run 'termzilla' to launch."
fi

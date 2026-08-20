#!/usr/bin/env bash
# install.sh — install upstream midscroll (if needed), then midscroll-patched
set -euo pipefail

# ----- paths -----
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAEMON_SRC="$REPO_DIR/midscroll.py"
OVERLAY_SRC="$REPO_DIR/midscroll-overlay-x11.py"
DAEMON_DST="/usr/bin/midscroll"
OVERLAY_DST="/usr/local/bin/midscroll-overlay-x11"
CONF="/etc/midscroll.conf"
DROPIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/midscroll-overlay.service.d"
DROPIN="$DROPIN_DIR/x11.conf"

die() { echo "error: $*" >&2; exit 1; }

# ----- safety checks -----
[[ -f "$DAEMON_SRC" && -f "$OVERLAY_SRC" ]] || die "run this from the midscroll-patched repo root"
[[ "$(id -u)" -ne 0 ]] || die "do not run as root; the script will sudo when needed"
[[ "${XDG_SESSION_TYPE:-}" == "x11" ]] || echo "warning: session is not x11; overlay may not work"

command -v systemctl >/dev/null || die "systemctl not found"
command -v dpkg-divert >/dev/null || die "dpkg-divert not found (Debian/Ubuntu/Mint expected)"
command -v git >/dev/null || die "git not found (needed if midscroll must be cloned)"

# ----- install upstream midscroll if missing -----
ensure_upstream() {
  if systemctl cat midscroll &>/dev/null && [[ -f "$CONF" ]]; then
    echo "==> upstream midscroll already present"
    return 0
  fi

  echo "==> upstream midscroll not found — trying apt"
  if command -v apt-get >/dev/null; then
    sudo apt-get update
    if apt-cache show midscroll &>/dev/null; then
      sudo apt-get install -y midscroll
      systemctl cat midscroll &>/dev/null && [[ -f "$CONF" ]] && return 0
    fi
  fi

  echo "==> no package; cloning upstream and running its install.sh"
  local tmp
  tmp="$(mktemp -d)"
  # clean temp dir when this function returns
  trap 'rm -rf "$tmp"' RETURN
  git clone --depth 1 https://github.com/gnhen/midscroll.git "$tmp/midscroll"
  ( cd "$tmp/midscroll" && sudo ./install.sh )

  systemctl cat midscroll &>/dev/null || die "upstream midscroll install failed"
  [[ -f "$CONF" ]] || die "$CONF missing after upstream install"
}

ensure_upstream

# ----- protect / replace daemon binary -----
echo "==> diverting packaged $DAEMON_DST (if needed)"
if ! dpkg-divert --list "$DAEMON_DST" 2>/dev/null | grep -q .; then
  sudo dpkg-divert --add --rename --divert /usr/bin/midscroll.dist "$DAEMON_DST"
else
  echo "    divert already present"
fi

echo "==> installing patched daemon"
sudo cp "$DAEMON_SRC" "$DAEMON_DST"
sudo chmod 755 "$DAEMON_DST"

# ----- config keys -----
echo "==> ensuring TOGGLE_MODE / GHOST_CURSOR in $CONF"
ensure_conf_key() {
  local key="$1" val="$2"
  if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$CONF"; then
    sudo sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*|${key} = ${val}|" "$CONF"
  else
    echo "${key} = ${val}" | sudo tee -a "$CONF" >/dev/null
  fi
}
ensure_conf_key TOGGLE_MODE true
ensure_conf_key GHOST_CURSOR true
sudo chown root:root "$CONF"
sudo chmod 644 "$CONF"

echo "==> restarting system midscroll"
sudo systemctl restart midscroll

# ----- overlay -----
echo "==> installing X11 overlay"
sudo install -m 755 "$OVERLAY_SRC" "$OVERLAY_DST"

echo "==> user unit drop-in"
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN" <<'EOF'
[Service]
ExecStart=
ExecStart=/usr/local/bin/midscroll-overlay-x11
EOF

systemctl --user daemon-reload
systemctl --user enable --now midscroll-overlay

echo
echo "Done."
echo "  system midscroll:  $(systemctl is-active midscroll 2>/dev/null || true)"
echo "  user overlay:      $(systemctl --user is-active midscroll-overlay 2>/dev/null || true)"
echo "  XDG_SESSION_TYPE:  ${XDG_SESSION_TYPE:-unknown}"
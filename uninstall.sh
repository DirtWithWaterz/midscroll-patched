#!/usr/bin/env bash
# uninstall.sh — remove midscroll-patched, optionally remove midscroll entirely
set -euo pipefail

die() { echo "error: $*" >&2; exit 1; }

[[ "$(id -u)" -ne 0 ]] || die "do not run as root; the script will sudo when needed"

DROPIN_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/midscroll-overlay.service.d"
DROPIN="$DROPIN_DIR/x11.conf"
OVERLAY_DST="/usr/local/bin/midscroll-overlay-x11"
DAEMON_DST="/usr/bin/midscroll"

REMOVE_ALL=0

case "${1:-}" in
  --remove-all)  REMOVE_ALL=1 ;;
  --patch-only)  REMOVE_ALL=0 ;;
  "")
    echo "What do you want to uninstall?"
    echo "  y = midscroll completely (daemon, config, services, and this patch)"
    echo "  n = only this patch (put the original midscroll binary back if possible)"
    read -r -p "Remove midscroll completely? [y/N] " ans
    case "${ans:-}" in
      y|Y|yes|YES) REMOVE_ALL=1 ;;
      *)           REMOVE_ALL=0 ;;
    esac
    ;;
  *)
    die "usage: $0 [--remove-all|--patch-only]"
    ;;
esac

echo "==> stopping custom overlay"
systemctl --user disable --now midscroll-overlay 2>/dev/null || true
rm -f "$DROPIN"
rmdir "$DROPIN_DIR" 2>/dev/null || true
systemctl --user daemon-reload 2>/dev/null || true
sudo rm -f "$OVERLAY_DST"

if [[ "$REMOVE_ALL" -eq 1 ]]; then
  echo "==> removing midscroll completely"

  # Undo divert so package removal can work
  if dpkg-divert --list "$DAEMON_DST" 2>/dev/null | grep -q .; then
    sudo rm -f "$DAEMON_DST"
    sudo dpkg-divert --rename --remove "$DAEMON_DST" || true
  fi

  sudo systemctl stop midscroll 2>/dev/null || true
  sudo systemctl disable midscroll 2>/dev/null || true

  # If it was installed as a .deb package
  if command -v apt-get >/dev/null && dpkg -l midscroll 2>/dev/null | grep -q '^ii'; then
    sudo apt-get remove -y --purge midscroll || true
  fi

  # Files commonly left by midscroll's own install.sh
  sudo rm -f /usr/bin/midscroll /usr/bin/midscroll.dist
  sudo rm -f /etc/midscroll.conf
  sudo rm -rf /run/midscroll
  # Optional: only if you know this tree is only midscroll
  # sudo rm -rf /usr/share/midscroll

  systemctl --user disable --now midscroll-overlay 2>/dev/null || true

  echo "Done. midscroll should be fully removed."
else
  echo "==> removing patch only; restoring original midscroll binary"
  if dpkg-divert --list "$DAEMON_DST" 2>/dev/null | grep -q .; then
    sudo rm -f "$DAEMON_DST"
    sudo dpkg-divert --rename --remove "$DAEMON_DST"
  fi
  sudo systemctl restart midscroll 2>/dev/null || true
  echo "Done. Original midscroll kept; custom overlay removed."
fi

echo "  midscroll service: $(systemctl is-active midscroll 2>/dev/null || echo not-running)"
echo "  custom overlay:    $(systemctl --user is-active midscroll-overlay 2>/dev/null || echo not-running)"
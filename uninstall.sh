#!/usr/bin/env bash
set -euo pipefail

systemctl --user disable --now midscroll-overlay 2>/dev/null || true
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/midscroll-overlay.service.d/x11.conf"
systemctl --user daemon-reload 2>/dev/null || true
sudo rm -f /usr/local/bin/midscroll-overlay-x11

# Restore packaged daemon if divert exists
if dpkg-divert --list /usr/bin/midscroll | grep -q .; then
  sudo rm -f /usr/bin/midscroll
  sudo dpkg-divert --rename --remove /usr/bin/midscroll
fi

sudo systemctl restart midscroll 2>/dev/null || true
echo "Uninstalled midscroll-patched files (upstream midscroll left installed)."

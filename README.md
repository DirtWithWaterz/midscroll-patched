# midscroll-patched

Local patch on top of [gnhen/midscroll](https://github.com/gnhen/midscroll):
Based on gnhen/midscroll (Unlicense); this tree is the same unless noted.

- **Toggle mode** keeps the real pointer **anchored** at the middle-click
  point, so scrolling stays on the window you started in (same as hold mode).
- Still sends `pos` lines so a custom X11 overlay can draw a badge, line, and
  target circle.

If you want to install this all manually than install **upstream midscroll first** (package or upstream `install.sh`) so
devices, `/etc/midscroll.conf`, and the systemd units already exist.

---

# Quick install

```bash
git clone https://github.com/DirtWithWaterz/midscroll-patched.git
cd midscroll-patched
chmod +x install.sh
./install.sh
```
---

# Manual Install

## 1. Patch the system daemon

Protect the packaged binary from upgrades, then install this repo’s daemon:

```bash
sudo dpkg-divert --add --rename --divert /usr/bin/midscroll.dist /usr/bin/midscroll

sudo cp /path/to/this/repo/midscroll.py /usr/bin/midscroll
sudo chmod 755 /usr/bin/midscroll
```

Edit the real config that the service loads:

```bash
sudo nano /etc/midscroll.conf
```

Set at least:

```text
TOGGLE_MODE = true
GHOST_CURSOR = true
```
Note that the packaged .conf may differ and only those two keys must be set.

Permissions must stay root-owned and not group/world-writable (otherwise the
daemon ignores the file):

```bash
sudo chown root:root /etc/midscroll.conf
sudo chmod 644 /etc/midscroll.conf
sudo systemctl restart midscroll
```

---

## 2. Custom X11 overlay

```bash
sudo install -m 755 /path/to/this/repo/midscroll-overlay-x11.py /usr/local/bin/midscroll-overlay-x11

mkdir -p ~/.config/systemd/user/midscroll-overlay.service.d
nano ~/.config/systemd/user/midscroll-overlay.service.d/x11.conf
```

Put **exactly** this in the file (no quotes):

```ini
[Service]
ExecStart=
ExecStart=/usr/local/bin/midscroll-overlay-x11
```

Save, then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now midscroll-overlay
systemctl --user status midscroll-overlay
```

Use an **X11** session (`echo $XDG_SESSION_TYPE` should print `x11`). This
overlay script is not for Wayland.

---

## After a reboot

If both units are **enabled**, they should start on their own:

```bash
systemctl is-enabled midscroll
systemctl --user is-enabled midscroll-overlay

systemctl is-active midscroll
systemctl --user is-active midscroll-overlay
```

You should not need to start them by hand each login.

---

## Updating the patch later

Re-copy after you change the repo files:

```bash
sudo cp /path/to/this/repo/midscroll.py /usr/bin/midscroll
sudo install -m 755 /path/to/this/repo/midscroll-overlay-x11.py /usr/local/bin/midscroll-overlay-x11

sudo systemctl restart midscroll
systemctl --user restart midscroll-overlay
```

`dpkg-divert` keeps package upgrades from overwriting `/usr/bin/midscroll`;
it does not install new versions of *your* patch for you.

---

## Notes

- System daemon = root, package unit `midscroll`.
- Overlay = your user session, unit `midscroll-overlay`.
- Replace `/path/to/this/repo` with the real clone path (e.g. `~/midscroll`).

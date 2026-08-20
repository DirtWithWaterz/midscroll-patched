#!/usr/bin/env python3

import array
import cairo
import gi
import os
import re
import socket
import struct
import subprocess
import threading
import time

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib

from Xlib import display
from Xlib.ext import xfixes


# ============================================================
# Configuration
# ============================================================

SOCK_PATH = "/run/midscroll/state.sock"

ICON_PATH = "/usr/share/midscroll/move-vertical.svg"

BADGE_SIZE = 42
ICON_SIZE = 24

GHOST_ALPHA = 0.85

FOCUS_POLL_SEC = 1.0

MAX_OFFSET = 100000

DEFAULT_CURSOR_SIZE = 24
MAX_CURSOR_SIZE = 256


# Xcursor constants
XCURSOR_IMAGE = 0xfffd0002


# ============================================================
# Xcursor handling
# ============================================================

CURSOR_DIRS = (
    "~/.local/share/icons",
    "~/.icons",
    "/usr/share/icons",
    "/usr/local/share/icons",
    "/usr/share/pixmaps",
)

CURSOR_NAMES = (
    "default",
    "left_ptr",
    "arrow",
    "top_left_arrow",
)


def cursor_theme_name():
    """
    Get the cursor theme used by Cinnamon.
    """

    env = os.environ.get("XCURSOR_THEME")

    if env:
        return env

    try:
        result = subprocess.run(
            [
                "gsettings",
                "get",
                "org.cinnamon.desktop.interface",
                "cursor-theme",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode == 0:
            value = result.stdout.strip()

            # gsettings returns strings like:
            # 'Bibata-Modern-Classic'
            if value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            return value

    except Exception:
        pass

    return "default"


def cursor_size():

    env = os.environ.get("XCURSOR_SIZE")

    if env:
        try:
            value = int(env)

            if 0 < value <= MAX_CURSOR_SIZE:
                return value

        except ValueError:
            pass

    try:
        result = subprocess.run(
            [
                "gsettings",
                "get",
                "org.cinnamon.desktop.interface",
                "cursor-size",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode == 0:
            value = int(result.stdout.strip())

            if 0 < value <= MAX_CURSOR_SIZE:
                return value

    except Exception:
        pass

    return DEFAULT_CURSOR_SIZE


def find_cursor_file(theme, seen=None):

    if seen is None:
        seen = set()

    if not theme:
        return None

    if theme in seen:
        return None

    if len(seen) > 8:
        return None

    seen.add(theme)

    inherits = []

    for directory in CURSOR_DIRS:

        base = os.path.join(
            os.path.expanduser(directory),
            theme,
        )

        for name in CURSOR_NAMES:

            path = os.path.join(
                base,
                "cursors",
                name,
            )

            if os.path.isfile(path):
                return path

        index_path = os.path.join(
            base,
            "index.theme",
        )

        try:

            with open(index_path, "r", encoding="utf-8") as f:

                for line in f:

                    if line.startswith("Inherits"):

                        inherits.extend(
                            part.strip()
                            for part in line.partition("=")[2].split(",")
                            if part.strip()
                        )

        except OSError:
            pass

    for parent in inherits:

        path = find_cursor_file(
            parent,
            seen,
        )

        if path:
            return path

    return None


def read_xcursor(path, wanted_size):

    try:

        with open(path, "rb") as f:
            data = f.read(4 << 20)

    except OSError:
        return None

    if len(data) < 16:
        return None

    if data[:4] != b"Xcur":
        return None

    try:

        _magic, header, _version, toc_count = struct.unpack_from(
            "<4sIII",
            data,
        )

    except struct.error:
        return None

    best = None

    for i in range(min(toc_count, 1024)):

        try:

            chunk_type, nominal_size, position = struct.unpack_from(
                "<III",
                data,
                header + i * 12,
            )

        except struct.error:
            break

        if chunk_type != XCURSOR_IMAGE:
            continue

        if (
            best is None
            or abs(nominal_size - wanted_size)
            < abs(best[0] - wanted_size)
        ):
            best = (
                nominal_size,
                position,
            )

    if best is None:
        return None

    try:

        (
            _size,
            _type,
            _subtype,
            _version,
            width,
            height,
            hot_x,
            hot_y,
            _delay,
        ) = struct.unpack_from(
            "<9I",
            data,
            best[1],
        )

    except struct.error:
        return None

    if not (
        0 < width <= MAX_CURSOR_SIZE
        and 0 < height <= MAX_CURSOR_SIZE
    ):
        return None

    if hot_x > width or hot_y > height:
        return None

    offset = best[1] + 36

    count = width * height

    try:

        pixels = struct.unpack_from(
            f"<{count}I",
            data,
            offset,
        )

    except struct.error:
        return None

    return (
        array.array("I", pixels).tobytes(),
        width,
        height,
        hot_x,
        hot_y,
    )

# ============================================================
# X11 pointer
# ============================================================

class X11Pointer:

    def __init__(self):

        self.display = display.Display()

        self.root = self.display.screen().root

        self.xfixes_available = False
        self.cursor_hidden = False

        try:
            if self.display.query_extension("XFIXES") is None:
                raise RuntimeError("XFIXES extension not present")
            
            ver = self.display.xfixes_query_version()
            if ver.major_version < 4:
                raise RuntimeError(
                    f"XFIXES version too old: {ver.major_version}.{ver.minor_version}"
                )

            self.xfixes_available = True

        except Exception:
            print(
                "WARNING: XFixes extension is unavailable; "
                "the real cursor cannot be hidden."
            )

    def position(self):

        pointer = self.root.query_pointer()

        return (
            pointer.root_x,
            pointer.root_y,
        )

    def hide_cursor(self):

        if not self.xfixes_available or self.cursor_hidden:
            return

        try:

            self.root.xfixes_hide_cursor()

            self.display.flush()
            self.cursor_hidden = True

        except Exception as exc:

            print(
                "WARNING: Could not hide X11 cursor:",
                exc,
            )

    def show_cursor(self):

        if not self.xfixes_available or not self.cursor_hidden:
            return

        try:

            self.root.xfixes_show_cursor()

            self.display.flush()
            self.cursor_hidden = False

        except Exception as exc:

            print(
                "WARNING: Could not show X11 cursor:",
                exc,
            )


# ============================================================
# Drawing
# ============================================================

class Overlay(Gtk.Window):

    def __init__(self):

        super().__init__(
            type=Gtk.WindowType.POPUP
        )

        self.set_decorated(False)

        self.set_app_paintable(True)

        self.set_accept_focus(False)

        self.set_focus_on_map(False)

        self.set_skip_taskbar_hint(True)

        self.set_skip_pager_hint(True)

        self.set_keep_above(True)

        self.set_title("midscroll-x11")

        self._redraw_id = None

        self.locked_focus = None

        screen = Gdk.Screen.get_default()

        visual = screen.get_rgba_visual()

        if visual is not None:
            self.set_visual(visual)

        # X11 connection used for pointer position and root geometry.
        self.pointer = X11Pointer()

        root_geometry = self.pointer.display.screen().root.get_geometry()

        self.root_width = root_geometry.width
        self.root_height = root_geometry.height

        self.set_default_size(
            self.root_width,
            self.root_height,
        )

        self.move(0, 0)

        self.connect(
            "draw",
            self.on_draw,
        )

        self.connect(
            "realize",
            self.on_realize,
        )

        self.active = False

        self.anchor = (0, 0)

        self.offset = (0, 0)

        # True while the midscroll daemon socket is connected.
        self.socket_connected = False

        self.icon = None

        try:

            self.icon = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                ICON_PATH,
                ICON_SIZE,
                ICON_SIZE,
                True,
            )

        except Exception as exc:

            print(
                "Could not load autoscroll icon:",
                exc,
            )

    def on_realize(self, *_args):

        window = self.get_window()

        # Don't let the window manager decorate/manage this surface.
        window.set_override_redirect(True)

        # Completely empty input region.
        #
        # This is critical.
        #
        # The overlay exists visually but cannot receive
        # mouse clicks.
        window.input_shape_combine_region(
            cairo.Region(),
            0,
            0,
        )

    def make_click_through(self):

        window = self.get_window()

        if window is not None:

            window.input_shape_combine_region(
                cairo.Region(),
                0,
                0,
            )

    def draw_badge(self, cr, x, y):
        radius = BADGE_SIZE / 2

        # Background
        cr.set_source_rgba(0.12, 0.12, 0.13, 0.82)
        cr.arc(x, y, radius, 0, 6.283185307179586)
        cr.fill()

        # Border
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.28)
        cr.set_line_width(1.0)
        cr.arc(x, y, radius - 0.5, 0, 6.283185307179586)
        cr.stroke()

        # Always use the outlined white arrows (more visible on dark themes)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        cr.set_line_width(2.0)

        # Up arrow
        cr.move_to(x, y - 11)
        cr.line_to(x, y - 3)
        cr.stroke()
        cr.move_to(x, y - 11)
        cr.line_to(x - 4, y - 6)
        cr.stroke()
        cr.move_to(x, y - 11)
        cr.line_to(x + 4, y - 6)
        cr.stroke()

        # Down arrow
        cr.move_to(x, y + 11)
        cr.line_to(x, y + 3)
        cr.stroke()
        cr.move_to(x, y + 11)
        cr.line_to(x - 4, y + 6)
        cr.stroke()
        cr.move_to(x, y + 11)
        cr.line_to(x + 4, y + 6)
        cr.stroke()

    def draw_target(self, cr, x, y):
        """Small circle at the current offset position."""
        # Outer ring (white)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)
        cr.set_line_width(1.5)
        cr.arc(x, y, 6.0, 0, 6.283185307179586)
        cr.stroke()

        # Inner fill (semi-transparent)
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.35)
        cr.arc(x, y, 4.0, 0, 6.283185307179586)
        cr.fill()

    def draw_line(self, cr, x1, y1, x2, y2):
        """Thin white line from badge centre to the target circle."""
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.55)
        cr.set_line_width(1.25)
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()

    def on_draw(self, _widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()

        if not self.active:
            return False

        anchor_x, anchor_y = self.anchor
        dx, dy = self.offset

        target_x = anchor_x + dx
        target_y = anchor_y + dy

        target_x = max(0, min(target_x, self.root_width - 1))
        target_y = max(0, min(target_y, self.root_height - 1))

        self.draw_line(cr, anchor_x, anchor_y, target_x, target_y)
        self.draw_badge(cr, anchor_x, anchor_y)
        self.draw_target(cr, target_x, target_y)
        return False

    def start(self):
        self.anchor = self.pointer.position()
        self.offset = (0, 0)
        self.active = True

        self.locked_focus = active_window_class()

        self.pointer.hide_cursor()
        self.make_click_through()
        self.show_all()
        self.queue_draw()

        # Redraw ~60 fps so the circle tracks the pointer smoothly
        if self._redraw_id is None:
            self._redraw_id = GLib.timeout_add(16, self._tick)

    def stop(self):
        self.active = False
        self.locked_focus = None
        self.hide()
        self.pointer.show_cursor()

        if self._redraw_id is not None:
            GLib.source_remove(self._redraw_id)
            self._redraw_id = None

    def _tick(self):
        if self.active:
            self.queue_draw()
            return True          # keep the timer running
        return False

    def set_offset(
        self,
        dx,
        dy,
    ):

        if abs(dx) > MAX_OFFSET:
            return

        if abs(dy) > MAX_OFFSET:
            return

        self.offset = (
            dx,
            dy,
        )

        print(f"pos {dx} {dy}")

        if self.active:

            self.queue_draw()


# ============================================================
# Focus / blacklist support
# ============================================================

def active_window_class():

    try:

        root = subprocess.run(
            [
                "xprop",
                "-root",
                "_NET_ACTIVE_WINDOW",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if root.returncode != 0:
            return ""

        match = re.search(
            r"window id # (0x[0-9a-fA-F]+)",
            root.stdout,
        )

        if not match:
            return ""

        window_id = match.group(1)

        result = subprocess.run(
            [
                "xprop",
                "-id",
                window_id,
                "WM_CLASS",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )

        if result.returncode != 0:
            return ""

        match = re.search(
            r'=\s*"([^"]*)",\s*"([^"]*)"',
            result.stdout,
        )

        if not match:
            return ""

        instance = match.group(1)
        window_class = match.group(2)

        return (
            f"{instance} "
            f"{window_class}"
        )

    except Exception:

        return ""


def report_focus(sock, overlay):
    last = None

    while True:
        if overlay.locked_focus is not None:
            current = overlay.locked_focus
        else:
            current = active_window_class()

        if current != last:
            last = current
            try:
                sock.sendall(
                    b"focus "
                    + current.encode("utf-8", "replace")
                    + b"\n"
                )
            except OSError:
                return

        time.sleep(FOCUS_POLL_SEC)


# ============================================================
# Socket reader
# ============================================================

def socket_reader(overlay):

    while True:

        try:

            sock = socket.socket(
                socket.AF_UNIX,
                socket.SOCK_STREAM,
            )

            sock.connect(
                SOCK_PATH
            )

            GLib.idle_add(
                set_socket_connected,
                overlay,
                True,
            )

            focus_thread = threading.Thread(
                target=report_focus,
                args=(sock, overlay),
                daemon=True,
            )

            focus_thread.start()

            buffer = b""

            while True:

                data = sock.recv(4096)

                if not data:
                    GLib.idle_add(
                        set_socket_connected,
                        overlay,
                        False,
                    )

                    break

                buffer += data

                while b"\n" in buffer:

                    line, buffer = buffer.split(
                        b"\n",
                        1,
                    )

                    try:

                        text = line.decode(
                            "utf-8",
                            "replace",
                        ).strip()

                    except Exception:

                        continue

                    GLib.idle_add(
                        handle_line,
                        overlay,
                        text,
                    )

        except Exception:

            GLib.idle_add(
                set_socket_connected,
                overlay,
                False,
            )

        time.sleep(1)


def set_socket_connected(
    overlay,
    connected,
):

    overlay.socket_connected = connected

    if not connected and overlay.active:

        print(
            "midscroll daemon connection lost; hiding overlay"
        )

        overlay.stop()

    return False

def handle_line(
    overlay,
    text,
):

    if text == "1":

        overlay.start()

    elif text == "0":

        overlay.stop()

    elif text.startswith("pos "):

        parts = text.split()

        if len(parts) != 3:
            return False

        try:

            dx = int(parts[1])
            dy = int(parts[2])

        except ValueError:

            return False

        overlay.set_offset(
            dx,
            dy,
        )

    return False


# ============================================================
# Watchdog
# ============================================================

def watchdog(overlay):

    if overlay.active:

        # Keep the overlay click-through.
        overlay.make_click_through()

        # Only hide the overlay if the daemon socket
        # has actually disconnected.
        if not overlay.socket_connected:

            print(
                "midscroll daemon connection lost; hiding overlay"
            )

            overlay.stop()

    return True


# ============================================================
# Main
# ============================================================

def main():

    if os.environ.get("XDG_SESSION_TYPE") != "x11":

        print(
            "This overlay is specifically for X11."
        )

        return 1

    overlay = Overlay()

    thread = threading.Thread(
        target=socket_reader,
        args=(overlay,),
        daemon=True,
    )

    thread.start()

    GLib.timeout_add_seconds(
        1,
        watchdog,
        overlay,
    )

    try:

        Gtk.main()

    finally:

        # Always restore the real cursor if the overlay exits.
        overlay.pointer.show_cursor()

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )

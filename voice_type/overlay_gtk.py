"""Recording capsule at the bottom of the screen, Typeless-style: a small black pill with a
light waveform and no buttons. The waveform motion follows Handy's overlay
(github.com/cjpais/Handy): spectrum band levels, smoothed per bar, flat dots in silence.

Runs as a child process under the *system* python, because python3-gi is not in the venv.
voice_type.overlay drives it over stdin, one command per line:
    show <state>\t<detail>     state: recording | transcribing | done | error
    levels <v1,v2,...>         0..1 band levels while recording
    hide
Exits when stdin closes. The window is fully click-through.
"""
import math
import os
import sys
import threading

# Native Wayland clients cannot position their own windows on GNOME; XWayland can.
os.environ["GDK_BACKEND"] = "x11"

import cairo  # noqa: E402
import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import GLib, Gtk, Pango, PangoCairo  # noqa: E402

FONT_PX = 15
CARD_H = 44                     # ~3x the text height
CARD_W = 148
MAX_CARD_W = 260                # error text may widen the card up to this
SHADOW = 12                     # transparent margin around the card for the soft shadow
WIN_W, WIN_H = MAX_CARD_W + 2 * SHADOW, CARD_H + 2 * SHADOW
BOTTOM_OFFSET = 28
HALF = 7                        # band levels received; mirrored around the centre bar
BARS = 2 * HALF - 1
BAR_W, BAR_GAP = 3, 4
BAR_MIN, BAR_MAX = 3, 24

FILL_TOP = (0.11, 0.11, 0.12, 0.94)
FILL_BOTTOM = (0.04, 0.04, 0.05, 0.94)
EDGE = (1.0, 1.0, 1.0, 0.07)
HIGHLIGHT = (1.0, 1.0, 1.0, 0.10)
WAVE = (0.92, 0.93, 0.96)
TEXT = (0.88, 0.89, 0.92, 0.92)
ERROR = (1.0, 0.62, 0.52, 1.0)


class Pill(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_app_paintable(True)
        self.set_accept_focus(False)
        self.set_keep_above(True)
        self.set_default_size(WIN_W, WIN_H)
        self.set_size_request(WIN_W, WIN_H)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        self.alpha_ok = visual is not None and screen.is_composited()
        if self.alpha_ok:
            self.set_visual(visual)
        self.connect("draw", self.on_draw)
        self.connect("realize", lambda w: w.get_window().input_shape_combine_region(cairo.Region(), 0, 0))

        self.state = ""
        self.detail = ""
        self.target = [0.0] * BARS
        self.shown = [0.0] * BARS
        self.card_w = float(CARD_W)
        self.alpha = 0.0
        self.alpha_target = 0.0
        self.hide_id = 0
        GLib.timeout_add(33, self.tick)

    # ---------------- commands
    def command(self, line: str) -> bool:
        cmd, _, arg = line.rstrip("\n").partition(" ")
        if cmd == "levels":
            try:
                vals = [max(0.0, min(1.0, float(v))) for v in arg.split(",") if v]
            except ValueError:
                vals = []
            half = (vals + [0.0] * HALF)[:HALF]     # lowest band (most voice energy) in the middle
            self.target = half[:0:-1] + half
        elif cmd == "show":
            state, _, detail = arg.partition("\t")
            self.show_state(state, detail)
        elif cmd == "hide":
            self.fade_out()
        return False

    def show_state(self, state: str, detail: str) -> None:
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = 0
        if state == "done":           # the text is in; just go away
            self.fade_out()
            return
        if state == "recording" and self.state != "recording":
            self.target = [0.0] * BARS
            self.shown = [0.0] * BARS
        if not self.get_visible():
            self.card_w = float(self.card_width(state, detail))
            self.place()
            self.show()
        self.state, self.detail = state, detail
        self.alpha_target = 1.0
        self.queue_draw()
        if state == "error":
            self.hide_id = GLib.timeout_add(2500, self.fade_out)

    def fade_out(self) -> bool:
        self.hide_id = 0
        self.alpha_target = 0.0
        return False

    def card_width(self, state: str, detail: str) -> int:
        if state == "error":
            return max(CARD_W, min(MAX_CARD_W, 48 + (FONT_PX + 1) * len(self.error_label(detail))))
        return CARD_W

    def error_label(self, detail: str) -> str:
        return "出错：" + detail if detail else "出错"

    def place(self) -> None:
        display = self.get_display()
        mon = display.get_primary_monitor() or display.get_monitor(0)
        g = mon.get_workarea()
        self.move(g.x + (g.width - WIN_W) // 2, g.y + g.height - WIN_H - BOTTOM_OFFSET)

    # ---------------- animation
    def tick(self) -> bool:
        dirty = False
        if self.alpha != self.alpha_target:
            step = 0.033 / 0.2                     # 200 ms fade
            self.alpha = min(self.alpha_target, self.alpha + step) if self.alpha < self.alpha_target \
                else max(self.alpha_target, self.alpha - step)
            dirty = True
            if self.alpha == 0.0:
                self.state = ""
                self.hide()
                return True
        want = self.card_width(self.state, self.detail) if self.state else self.card_w
        if abs(want - self.card_w) > 0.5:
            self.card_w += (want - self.card_w) * 0.3
            dirty = True
        if self.state == "recording":
            for i in range(BARS):
                new = self.shown[i] * 0.7 + self.target[i] * 0.3   # Handy's per-bar smoothing
                if abs(new - self.shown[i]) > 0.002:
                    dirty = True
                self.shown[i] = new
        if dirty and self.get_visible():
            self.queue_draw()
        return True

    # ---------------- drawing
    def on_draw(self, _w, cr) -> bool:
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        if not self.state or self.alpha <= 0:
            return True
        cr.push_group()
        self.draw_card(cr)
        cr.pop_group_to_source()
        cr.paint_with_alpha(self.alpha)
        return True

    def draw_card(self, cr) -> None:
        w, h = self.card_w, CARD_H
        x0, y0 = (WIN_W - w) / 2, SHADOW
        r = h / 2

        for k in range(1, SHADOW + 1, 2):            # soft shadow, slightly below the card
            rounded(cr, x0 - k / 2, y0 + 3 - k / 2, w + k, h + k, r + k / 2)
            cr.set_source_rgba(0, 0, 0, 0.05 * (1 - k / SHADOW))
            cr.fill()

        rounded(cr, x0, y0, w, h, r)
        grad = cairo.LinearGradient(0, y0, 0, y0 + h)
        grad.add_color_stop_rgba(0, *FILL_TOP)
        grad.add_color_stop_rgba(1, *FILL_BOTTOM)
        cr.set_source(grad)
        cr.fill()
        rounded(cr, x0 + 0.5, y0 + 0.5, w - 1, h - 1, r - 0.5)
        cr.set_source_rgba(*EDGE)
        cr.set_line_width(1)
        cr.stroke()
        cr.new_sub_path()                             # thin highlight along the top edge
        cr.arc(x0 + r, y0 + r, r - 1, math.pi * 1.25, math.pi * 1.5)
        cr.line_to(x0 + w - r, y0 + 1)
        cr.arc(x0 + w - r, y0 + r, r - 1, math.pi * 1.5, math.pi * 1.75)
        cr.set_source_rgba(*HIGHLIGHT)
        cr.stroke()
        cy = y0 + h / 2

        if self.state == "recording":
            group = BARS * BAR_W + (BARS - 1) * BAR_GAP
            bx = x0 + (w - group) / 2
            for i, v in enumerate(self.shown):
                d = abs(i - (BARS - 1) / 2) / ((BARS - 1) / 2)   # 0 centre .. 1 edge
                bh = max(BAR_MIN, min(BAR_MAX, BAR_MIN + (v ** 0.7) * (BAR_MAX - BAR_MIN)))
                cr.set_source_rgba(*WAVE, 0.95 - 0.5 * d ** 1.5)
                rounded(cr, bx + i * (BAR_W + BAR_GAP), cy - bh / 2, BAR_W, bh, BAR_W / 2)
                cr.fill()
        elif self.state == "transcribing":
            self.text(cr, "识别中…", x0 + w / 2, cy, TEXT, w - 24)
        elif self.state == "error":
            self.text(cr, self.error_label(self.detail), x0 + w / 2, cy, ERROR, w - 24)

    def text(self, cr, s, cx, cy, rgba, max_w) -> None:
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription("Sans")
        fd.set_absolute_size(FONT_PX * Pango.SCALE)
        fd.set_weight(Pango.Weight.MEDIUM)
        layout.set_font_description(fd)
        attrs = Pango.AttrList()
        spacing = Pango.attr_letter_spacing_new(int(1.0 * Pango.SCALE))
        # spacing goes after each glyph, so stop before the last character to keep "…" tight
        spacing.end_index = len(s.rstrip("…")[:-1].encode("utf-8"))
        attrs.insert(spacing)
        layout.set_attributes(attrs)
        layout.set_text(s, -1)
        layout.set_width(int(max_w) * Pango.SCALE)
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        ink, _ = layout.get_pixel_extents()           # centre the visible glyphs, not the line box
        cr.move_to(cx - (ink.x + ink.width / 2), cy - (ink.y + ink.height / 2))
        cr.set_source_rgba(*rgba)
        PangoCairo.show_layout(cr, layout)


def rounded(cr, x, y, w, h, r) -> None:
    r = min(r, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def main() -> None:
    pill = Pill()

    def reader() -> None:
        for line in sys.stdin:
            GLib.idle_add(pill.command, line)
        GLib.idle_add(Gtk.main_quit)

    threading.Thread(target=reader, daemon=True).start()
    Gtk.main()


if __name__ == "__main__":
    main()

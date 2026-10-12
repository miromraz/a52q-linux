#!/usr/bin/env python3
# Full-screen GTK4 window that redraws every frame with random rectangles, to load the
# Wayland/compositor/display path like Electron does. GSK_RENDERER=cairo => wl_shm
# software buffers (like Electron with GPU disabled); =gl => GPU. Usage: rendstress.py SECS
import random, sys, time, gi
gi.require_version("Gtk", "4.0"); gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gtk
secs = float(sys.argv[1]); t_end = time.time() + secs; frames = [0]

class Noise(Gtk.Widget):
    def do_snapshot(self, snap):
        w, h = self.get_width(), self.get_height()
        for _ in range(200):
            c = Gdk.RGBA(); c.red, c.green, c.blue, c.alpha = random.random(), random.random(), random.random(), 1
            r = Graphene.Rect().init(random.random() * w, random.random() * h, 40 + random.random() * 200, 40 + random.random() * 200)
            snap.append_color(c, r)
        frames[0] += 1

def tick(widget, _clock):
    widget.queue_draw()
    if time.time() > t_end:
        print(f"frames {frames[0]}", flush=True); app.quit()
    return GLib.SOURCE_CONTINUE

def activate(app):
    win = Gtk.ApplicationWindow(application=app)
    n = Noise(); n.set_hexpand(True); n.set_vexpand(True); n.add_tick_callback(tick)
    win.set_child(n); win.fullscreen(); win.present()

app = Gtk.Application(application_id="org.a52.rendstress"); app.connect("activate", activate); app.run(None)

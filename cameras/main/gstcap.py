#!/usr/bin/env python3
# gstcap.py - capture processed (libcamera soft ISP) frames on BengalOS without
# gst-launch/typelibs: drives libgstreamer through ctypes.
#
#   gstcap.py OUTDIR SECONDS [CAMERA_ID] [WxH] [SRC_WxH]
#
# Runs libcamerasrc for SECONDS (AE/AWB converge), keeps the last 3 frames as
# PNG (scaled to WxH, default 1156x867; SRC_WxH = soft-ISP output size, default
# 4608x3456 so libcamerasrc does not pick a cropped 4096x2160), then EOS. Tuning override:
#   LIBCAMERA_IPA_CONFIG_PATH=/dir/with/s5kgw1p.yaml gstcap.py ...
import ctypes, os, sys, time

g = ctypes.CDLL("libgstreamer-1.0.so.0")
g.gst_parse_launch.restype = ctypes.c_void_p
g.gst_parse_launch.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
g.gst_element_set_state.argtypes = [ctypes.c_void_p, ctypes.c_int]
g.gst_element_get_bus.restype = ctypes.c_void_p
g.gst_element_get_bus.argtypes = [ctypes.c_void_p]
g.gst_bus_timed_pop_filtered.restype = ctypes.c_void_p
g.gst_bus_timed_pop_filtered.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_int]
g.gst_event_new_eos.restype = ctypes.c_void_p
g.gst_element_send_event.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

GST_MESSAGE_EOS, GST_MESSAGE_ERROR = 1 << 0, 1 << 1
PLAYING, NULL = 4, 1

out, secs = sys.argv[1], float(sys.argv[2])
cam = sys.argv[3] if len(sys.argv) > 3 else ""
w, h = (sys.argv[4] if len(sys.argv) > 4 else "1156x867").split("x")
sw, sh = (sys.argv[5] if len(sys.argv) > 5 else "4608x3456").split("x")
os.makedirs(out, exist_ok=True)
src = "libcamerasrc" + (f" camera-name={cam}" if cam else "")
desc = (f"{src} ! video/x-raw,width={sw},height={sh} ! queue ! videoconvertscale ! video/x-raw,format=RGB,width={w},height={h} "
        f"! pngenc compression-level=1 ! multifilesink location={out}/f%04d.png max-files=3")
g.gst_init(None, None)
err = ctypes.c_void_p()
p = g.gst_parse_launch(desc.encode(), ctypes.byref(err))
if not p:
    sys.exit("parse failed")
bus = g.gst_element_get_bus(p)
g.gst_element_set_state(p, PLAYING)
t0 = time.time()
while time.time() - t0 < secs:
    m = g.gst_bus_timed_pop_filtered(bus, 200 * 1000000, GST_MESSAGE_ERROR | GST_MESSAGE_EOS)
    if m:
        sys.exit("pipeline error/EOS early (run with GST_DEBUG=2)")
g.gst_element_send_event(p, g.gst_event_new_eos())
g.gst_bus_timed_pop_filtered(bus, 5 * 1000000000, GST_MESSAGE_ERROR | GST_MESSAGE_EOS)
g.gst_element_set_state(p, NULL)
print("frames:", sorted(os.listdir(out))[-3:])

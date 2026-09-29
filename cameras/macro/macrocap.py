#!/usr/bin/env python3
# Raw capture of the a52q MACRO gc5035 (22-003f) through the gpio66 video-mux
# -> csiphy3 -> csid2 -> vfe2(lite) rdi0, without media-ctl. Uses camcap.py helpers.
# Run under the camera lock:  flock /run/a52cam.lock python3 macrocap.py OUT.raw [FRAMES]
# Env: EXP=<lines> AG=<analogue gain code> DG=<digital gain code> TP=<test pattern>
#      TORCH=<0..8> (white:torch brightness while streaming)
#      OTP=<file>: dump the sensor OTP (1 KiB) over i2c-dev while streaming
#      SWEEP=<max AG code>: AG sweep, torch off/on per code, saves centre rows 700..1243
# Always restores the UW (s5k3l6xx) mux link and the torch on exit.
import os, sys, struct, fcntl, mmap, select, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camcap import *

SENSOR, UW, MUX = '22-003f', 's5k3l6xx', 'video-mux'  # macro may be named gc5035_macro
CSID, VIDEO = 'msm_csid2', 'msm_vfe2_video0'
CID = dict(EXP=0x00980911, AG=0x009e0903, DG=0x009f0905, TP=0x009f0903,
           VBLANK=0x009e0901, HBLANK=0x009e0902)
VIDIOC_S_CTRL, VIDIOC_G_CTRL = IOWR(V, 28, 8), IOWR(V, 27, 8)
TORCH = '/sys/class/leds/white:torch/brightness'

def ctrl(fd, cid, val=None):
    b = bytearray(struct.pack('<Ii', cid, val or 0))
    fcntl.ioctl(fd, VIDIOC_G_CTRL if val is None else VIDIOC_S_CTRL, b, True)
    return struct.unpack('<Ii', b)[1]

def link(mfd, E, P, L, src, dst, enable):
    for l in L:
        sp, kp = P.get(l['src']), P.get(l['snk'])
        if sp and kp and src in E[sp['ent']]['name'] and E[kp['ent']]['name'] == dst:
            setup_link(mfd, sp['ent'], sp['idx'], kp['ent'], kp['idx'], enable)
            return

def main(out, frames):
    mfd = os.open('/dev/media0', os.O_RDWR)
    E, I, P, L = g_topology(mfd)
    by = {e['name']: i for i, e in E.items()}
    link(mfd, E, P, L, UW, MUX, False)
    link(mfd, E, P, L, SENSOR, MUX, True)
    try:
        phy, csid, vid = by['msm_csiphy3'], by[CSID], by[VIDEO]
        vfe = next(P[l['src']]['ent'] for l in L if l['snk'] in P and P[l['snk']]['ent'] == vid)
        for l in L:  # free csiphy3 source / csid2 / vfe2_rdi0 links left by others
            if is_data_link(l['flags']) and l['flags'] & 1 and not l['flags'] & 2 and \
               l['snk'] in P and (P[l['snk']]['ent'] in (csid, vfe) or P[l['src']]['ent'] == phy):
                sp, kp = P[l['src']], P[l['snk']]
                setup_link(mfd, sp['ent'], sp['idx'], kp['ent'], kp['idx'], False)
        setup_link(mfd, phy, 1, csid, 0, True)
        setup_link(mfd, csid, 1, vfe, 0, True)
        sd = lambda ent: find_dev('/dev/v4l-subdev', *devnode_of(I, L, ent))
        sfd = os.open(sd(next(i for n, i in by.items() if SENSOR in n)), os.O_RDWR)
        code, w, h = subdev_fmt(sfd, 0, True)
        for k in ('EXP', 'AG', 'DG', 'TP'):
            if k in os.environ:
                ctrl(sfd, CID[k], int(os.environ[k]))
        def g(c):
            try: return ctrl(sfd, c)
            except OSError: return None  # control not provided by this driver build
        print('sensor %dx%d code 0x%x ' % (w, h, code) +
              ' '.join('%s=%s' % (k, g(c)) for k, c in CID.items()))
        for dev, pads in ((sd(by[MUX]), (1, 2)), (sd(phy), (0, 1)), (sd(csid), (0, 1)), (sd(vfe), (0, 1))):
            f = os.open(dev, os.O_RDWR)
            for pad in pads:
                try: subdev_fmt(f, pad, False, code, w, h)
                except OSError as e: print('  %s pad%d: %s' % (dev, pad, e))
            os.close(f)
        vfd = os.open(find_dev('/dev/video', *devnode_of(I, L, vid)), os.O_RDWR)
        w2, h2, pf, size, _, bpl = vid_set_fmt(vfd, w, h, pick_raw_pixfmt(vfd, code))
        print('video %dx%d %s bpl=%d' % (w2, h2, pf.to_bytes(4, 'little'), bpl))
        maps = []
        for i in range(reqbufs(vfd, 4)):
            off, ln = querybuf(vfd, i)
            maps.append(mmap.mmap(vfd, ln, mmap.MAP_SHARED, mmap.PROT_READ, offset=off))
            qbuf(vfd, i)
        if 'TORCH' in os.environ:
            open(TORCH, 'w').write(os.environ['TORCH'])
        fcntl.ioctl(vfd, VIDIOC_STREAMON, struct.pack('<i', MP))

        def grab(n):  # dequeue n frames, return the last one
            for _ in range(n):
                if not select.select([vfd], [], [], 3)[0]:
                    raise TimeoutError('no frame')
                idx, used = dqbuf(vfd)
                data = bytes(maps[idx][:used or len(maps[idx])])
                qbuf(vfd, idx)
            return data
        if 'OTP' in os.environ:  # dump the 1 KiB sensor OTP over i2c-dev while powered
            grab(3)
            open(os.environ['OTP'], 'wb').write(otp_dump())
            print('otp -> %s' % os.environ['OTP'])
        elif 'SWEEP' in os.environ:  # analogue gain sweep, torch off/on, centre rows
            for ag in range(int(os.environ['SWEEP']) + 1):
                ctrl(sfd, CID['AG'], ag)
                for t in ('0', os.environ.get('TORCH', '8')):
                    open(TORCH, 'w').write(t)
                    d = grab(5)
                    open('%s.ag%02d.t%s' % (out, ag, t), 'wb').write(d[700 * bpl:1244 * bpl])
            print('sweep done')
        else:
            open(out, 'wb').write(grab(frames))  # last frame: exposure settled
        fcntl.ioctl(vfd, VIDIOC_STREAMOFF, struct.pack('<i', MP))
        print('-> %s (%dx%d bpl %d)' % (out, w2, h2, bpl))
        os.close(vfd); os.close(sfd)
    finally:
        open(TORCH, 'w').write('0')
        os.close(mfd)
        restore()

def otp_dump(bus=22, addr=0x3f):
    # same sequence as gc5035_otp_read_data(); I2C_SLAVE_FORCE, the driver owns 0x3f
    fd = os.open('/dev/i2c-%d' % bus, os.O_RDWR)
    fcntl.ioctl(fd, 0x0706, addr)
    wr = lambda r, v: os.write(fd, bytes((r, v)))
    def rd(r):
        os.write(fd, bytes((r,)))
        return os.read(fd, 1)[0]
    for r, v in ((0xfe, 0), (0xfa, 0x10), (0xfe, 2), (0x67, 0xc0), (0x59, 0x3f),
                 (0x55, 0x84), (0x65, 0x80), (0x66, 0x03)):
        wr(r, v)
    wr(0x69, 0); wr(0x6a, 0); wr(0xf3, 0x20); wr(0xf3, 0x12)
    data = bytes(rd(0x6c) for _ in range(1024))
    wr(0xf3, 0)
    for r, v in ((0xfe, 2), (0x67, 0), (0xfe, 0), (0xfa, 0)):
        wr(r, v)
    os.close(fd)
    return data

def restore():  # UW back on the CSIPHY3 mux (the default link)
    mfd = os.open('/dev/media0', os.O_RDWR)
    # enable+disable macro first: video-mux can be left with active=macro while
    # both links read disabled, and then refuses the UW link with EBUSY
    for src, en in ((SENSOR, True), (SENSOR, False), (UW, True)):
        E, I, P, L = g_topology(mfd)
        try:
            link(mfd, E, P, L, src, MUX, en)
        except OSError as e:
            if src == UW:
                raise
    os.close(mfd)

if __name__ == '__main__' and sys.argv[1] == 'restore':
    restore()
elif __name__ == '__main__':
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8)

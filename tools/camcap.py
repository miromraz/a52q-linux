#!/usr/bin/env python3
# Minimal media-controller + V4L2 RDI capture for qcom-camss, no media-ctl needed.
# Usage:
#   camcap.py dump
#   camcap.py capture <sensor-name-substr> <out.raw> [frames]
import sys, os, struct, fcntl, mmap, glob, time

# ---- ioctl helpers ----
def _IOC(d,t,nr,sz): return (d<<30)|(sz<<16)|(t<<8)|nr
IOR=2; IOW=1; IORW=3
def IOWR(t,nr,sz): return _IOC(IORW,t,nr,sz)
def IOW_(t,nr,sz):  return _IOC(IOW,t,nr,sz)
def IOR_(t,nr,sz):  return _IOC(IOR,t,nr,sz)

MI=0x7C  # '|'
# G_TOPOLOGY struct media_v2_topology (80 bytes)
TOPO_FMT="<QIIQIIQIIQIIQ"  # ver,ne,r1,pe,ni,r2,pi,np,r3,pp,nl,r4,pl -> need care
# Actually: Q ver; I ne; I r1; Q pe; I ni; I r2; Q pi; I np; I r3; Q pp; I nl; I r4; Q pl
TOPO_FMT="<Q II Q II Q II Q II Q"
TOPO_SZ=struct.calcsize(TOPO_FMT)
MEDIA_IOC_G_TOPOLOGY=IOWR(MI,4,TOPO_SZ)

ENT_FMT="<I64sII20s"     # media_v2_entity: id,name[64],function,flags,reserved[5]=20
ENT_SZ=struct.calcsize(ENT_FMT)  # 96
# media_v2_interface (packed): id,intf_type,flags,reserved[9]; union{devnode{major,minor}; raw[16]}
IFACE_FMT="<III36sII56s" # id,intf_type,flags,reserved36,major,minor,rest56
IFACE_SZ=struct.calcsize(IFACE_FMT) # 112
PAD_FMT="<IIII16s"      # id,entity_id,flags,index,reserved[4]
PAD_SZ=struct.calcsize(PAD_FMT) # 32
LINK_FMT="<IIII24s"     # id,source_id,sink_id,flags,reserved[6]
LINK_SZ=struct.calcsize(LINK_FMT) # 40

def g_topology(fd):
    buf=bytearray(struct.pack(TOPO_FMT,*([0]*13)))
    fcntl.ioctl(fd,MEDIA_IOC_G_TOPOLOGY,buf,True)
    (ver,ne,_,_pe,ni,_,_pi,npd,_,_pp,nl)=struct.unpack(TOPO_FMT,buf)[:11]
    ents=bytearray(ne*ENT_SZ); ifs=bytearray(ni*IFACE_SZ)
    pads=bytearray(npd*PAD_SZ); links=bytearray(nl*LINK_SZ)
    ea=_addr(ents); ia=_addr(ifs); pa=_addr(pads); la=_addr(links)
    buf=bytearray(struct.pack(TOPO_FMT,ver,ne,0,ea,ni,0,ia,npd,0,pa,nl,0,la))
    fcntl.ioctl(fd,MEDIA_IOC_G_TOPOLOGY,buf,True)
    E={};
    for i in range(ne):
        eid,name,func,flags,_=struct.unpack_from(ENT_FMT,ents,i*ENT_SZ)
        E[eid]=dict(id=eid,name=name.split(b'\0')[0].decode(),func=func,flags=flags)
    I={}
    for i in range(ni):
        iid,itype,iflags,_,major,minor,_=struct.unpack_from(IFACE_FMT,ifs,i*IFACE_SZ)
        I[iid]=dict(id=iid,itype=itype,major=major,minor=minor)
    P={}
    for i in range(npd):
        pid,ent,flags,idx,_=struct.unpack_from(PAD_FMT,pads,i*PAD_SZ)
        P[pid]=dict(id=pid,ent=ent,flags=flags,idx=idx)
    L=[]
    for i in range(nl):
        lid,src,snk,flags,_=struct.unpack_from(LINK_FMT,links,i*LINK_SZ)
        L.append(dict(id=lid,src=src,snk=snk,flags=flags))
    return E,I,P,L

_keep=[]
def _addr(ba):
    # get address of a bytearray's buffer via ctypes
    import ctypes
    _keep.append(ba)
    return ctypes.addressof((ctypes.c_char*len(ba)).from_buffer(ba)) if len(ba) else 0

MEDIA_LNK_FL_ENABLED=1; MEDIA_LNK_FL_IMMUTABLE=2
MEDIA_LNK_FL_LINK_TYPE=0xf0000000
MEDIA_LNK_FL_DATA_LINK=0
def is_data_link(f): return (f & MEDIA_LNK_FL_LINK_TYPE)==0

def dump(dev='/dev/media0'):
    fd=os.open(dev,os.O_RDWR)
    E,I,P,L=g_topology(fd)
    print("== entities ==")
    for eid,e in sorted(E.items()):
        print(f"  [{eid}] {e['name']} func=0x{e['func']:x} flags=0x{e['flags']:x}")
    print("== data links ==")
    for l in L:
        if not is_data_link(l['flags']): continue
        sp=P.get(l['src']); kp=P.get(l['snk'])
        if not sp or not kp: continue
        se=E.get(sp['ent'],{}).get('name','?'); ke=E.get(kp['ent'],{}).get('name','?')
        fl=[]
        if l['flags']&MEDIA_LNK_FL_ENABLED: fl.append("ENABLED")
        if l['flags']&MEDIA_LNK_FL_IMMUTABLE: fl.append("IMMUTABLE")
        print(f"  {se}:{sp['idx']} -> {ke}:{kp['idx']}  [{','.join(fl)}]")
    os.close(fd)

# ---- v4l2 ioctls ----
V=0x56
VIDIOC_ENUM_FMT   = IOWR(V,2,64)
VIDIOC_G_FMT      = IOWR(V,4,208)
VIDIOC_S_FMT      = IOWR(V,5,208)
VIDIOC_REQBUFS    = IOWR(V,8,20)
VIDIOC_QUERYBUF   = IOWR(V,9,88)
VIDIOC_QBUF       = IOWR(V,15,88)
VIDIOC_DQBUF      = IOWR(V,17,88)
VIDIOC_STREAMON   = IOW_(V,18,4)
VIDIOC_STREAMOFF  = IOW_(V,19,4)
VIDIOC_SUBDEV_G_FMT = IOWR(V,4,88)
VIDIOC_SUBDEV_S_FMT = IOWR(V,5,88)
MEDIA_IOC_SETUP_LINK = IOWR(MI,3,52)

MBUS_FMT="<5I 4H 10H"   # width,height,code,field,colorspace, ycbcr,quant,xfer,flags, reserved[10]
SDFMT_FMT="<II"+"5I4H10H"+"I28s"  # which,pad, mbus(48), stream, reserved[7]
WHICH_ACTIVE=1

def subdev_fmt(fd, pad, get, code=0,w=0,h=0):
    mb=struct.pack(MBUS_FMT, w,h,code,1,0, 0,0,0,0, *([0]*10))
    buf=bytearray(struct.pack("<II",WHICH_ACTIVE,pad)+mb+struct.pack("<I28s",0,b""))
    fcntl.ioctl(fd, VIDIOC_SUBDEV_G_FMT if get else VIDIOC_SUBDEV_S_FMT, buf, True)
    w,h,code,field,cs = struct.unpack_from("<5I",buf,8)
    return code,w,h

def setup_link(mfd, se, si, ke, ki, enable):
    # media_link_desc: source(pad_desc20) sink(pad_desc20) flags(4) reserved[2](8)=52
    # pad_desc: entity(I) index(H) 2pad flags(I) reserved[2](8) = 20
    pd=lambda ent,idx: struct.pack("<IHxxI8s",ent,idx,0,b"")
    buf=bytearray(pd(se,si)+pd(ke,ki)+struct.pack("<I8s", 1 if enable else 0, b""))
    fcntl.ioctl(mfd, MEDIA_IOC_SETUP_LINK, buf, True)

def devnode_of(I,L,ent):
    for l in L:
        if l['snk']==ent and l['src'] in I:
            i=I[l['src']]; return i['major'],i['minor']
    return None

def find_dev(prefix,major,minor):
    for p in glob.glob(prefix+'*'):
        st=os.stat(p)
        if os.major(st.st_rdev)==major and os.minor(st.st_rdev)==minor: return p
    return None

# camss video nodes are MULTIPLANAR
MP=9  # V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE
_plane_keep=[]
def _plane_buf():
    pb=bytearray(64)   # one v4l2_plane
    _plane_keep.append(pb)
    import ctypes
    return pb, ctypes.addressof((ctypes.c_char*64).from_buffer(pb))

def enum_pixfmts(fd):
    out=[]
    for i in range(64):
        buf=bytearray(struct.pack("<III32sII12s",i,MP,0,b"",0,0,b""))
        try: fcntl.ioctl(fd,VIDIOC_ENUM_FMT,buf,True)
        except OSError: break
        out.append(struct.unpack_from("<I",buf,12+32)[0])
    return out
# mbus code -> Bayer order
BAYER={0x3007:'BGGR',0x300e:'GBRG',0x300a:'GRBG',0x300f:'RGGB',   # *_1X10
       0x3001:'BGGR',0x3013:'GBRG',0x3002:'GRBG',0x3014:'RGGB'}   # *_1X8
# preferred video fourcc per (bpp10, bayer): packed 10-bit, else 8-bit
FOURCC10={'RGGB':b'pRAA','BGGR':b'pBAA','GBRG':b'pGAA','GRBG':b'pgAA'}
FOURCC8 ={'RGGB':b'RGGB','BGGR':b'BA81','GBRG':b'GBRG','GRBG':b'GRBG'}
def pick_raw_pixfmt(fd, code):
    pfs=enum_pixfmts(fd)
    names=[pf.to_bytes(4,'little') for pf in pfs]
    print("  video pixfmts:", [n.decode('latin1') for n in names])
    bayer=BAYER.get(code)
    bpp10 = code in (0x3007,0x300e,0x300a,0x300f)
    want=(FOURCC10 if bpp10 else FOURCC8).get(bayer)
    if want:
        for pf,n in zip(pfs,names):
            if n==want: return pf
    raise RuntimeError(f"no matching raw fourcc for code 0x{code:x} bayer={bayer} want={want} in {[n.decode('latin1') for n in names]}")

def vid_set_fmt(fd,w,h,pixfmt):
    # v4l2_format: type(4)+pad(4)+ pix_mp at off8:
    #   w,h,pixfmt,field,colorspace (5u32); plane_fmt[8] (8*20); num_planes(u8)@180; ...
    body=bytearray(208)
    struct.pack_into("<II",body,0,MP,0)
    struct.pack_into("<5I",body,8, w,h,pixfmt,1,0)
    struct.pack_into("<B",body,8+180,1)     # num_planes=1
    fcntl.ioctl(fd,VIDIOC_S_FMT,body,True)
    w2,h2,pf2=struct.unpack_from("<3I",body,8)
    nplanes=struct.unpack_from("<B",body,8+180)[0]
    sizeimage=struct.unpack_from("<I",body,8+20)[0]      # plane_fmt[0].sizeimage
    bpl=struct.unpack_from("<I",body,8+24)[0]            # plane_fmt[0].bytesperline
    return w2,h2,pf2,sizeimage,nplanes,bpl

def reqbufs(fd,count):
    buf=bytearray(struct.pack("<IIIIB3s",count,MP,1,0,0,b""))
    fcntl.ioctl(fd,VIDIOC_REQBUFS,buf,True)
    return struct.unpack_from("<I",buf,0)[0]

def _mkbuf(idx):
    b=bytearray(88); struct.pack_into("<II",b,0,idx,MP)
    struct.pack_into("<I",b,60,1)                 # memory=MMAP
    pb,pa=_plane_buf()
    struct.pack_into("<Q",b,64,pa)                # m.planes ptr
    struct.pack_into("<I",b,72,1)                 # length = num_planes
    return b,pb

def querybuf(fd,idx):
    b,pb=_mkbuf(idx)
    fcntl.ioctl(fd,VIDIOC_QUERYBUF,b,True)
    length=struct.unpack_from("<I",pb,4)[0]
    offset=struct.unpack_from("<I",pb,8)[0]       # plane.m.mem_offset
    return offset,length

def qbuf(fd,idx):
    b,pb=_mkbuf(idx)
    fcntl.ioctl(fd,VIDIOC_QBUF,b,True)

def dqbuf(fd):
    b,pb=_mkbuf(0)
    fcntl.ioctl(fd,VIDIOC_DQBUF,b,True)
    idx=struct.unpack_from("<I",b,0)[0]
    bytesused=struct.unpack_from("<I",pb,0)[0]
    return idx,bytesused

def capture(sensor_sub, csid_name, csid_src_pad, video_name, outpath, frames, dev='/dev/media0'):
    mfd=os.open(dev,os.O_RDWR)
    E,I,P,L=g_topology(mfd)
    byname={e['name']:eid for eid,e in E.items()}
    # find sensor entity
    sid=next(eid for eid,e in E.items() if sensor_sub in e['name'])
    # sensor -> csiphy (immutable link from sensor source pad)
    src_pads={pid for pid,p in P.items() if p['ent']==sid}
    phy=None
    for l in L:
        if not is_data_link(l['flags']): continue
        if l['src'] in src_pads:
            phy=P[l['snk']]['ent']
    csid=byname[csid_name]; vid=byname[video_name]
    # find vfe_rdi feeding this video (immutable link into video sink)
    vfe=None
    for l in L:
        if l['snk'] in P and P[l['snk']]['ent']==vid and is_data_link(l['flags']):
            vfe=P[l['src']]['ent']
    print(f"path: sensor={sid} csiphy={phy} csid={csid}(srcpad{csid_src_pad}) vfe_rdi={vfe} video={vid}")
    # clear all non-immutable enabled data links so rerouting cannot hit EBUSY
    for l in L:
        if is_data_link(l['flags']) and (l['flags']&MEDIA_LNK_FL_ENABLED) and not (l['flags']&MEDIA_LNK_FL_IMMUTABLE):
            sp=P[l['src']]; kp=P[l['snk']]
            try: setup_link(mfd, sp['ent'],sp['idx'], kp['ent'],kp['idx'], False)
            except OSError: pass
    # enable links: csiphy:1 -> csid:0 ; csid:csid_src_pad -> vfe_rdi:0
    setup_link(mfd, phy,1, csid,0, True)
    setup_link(mfd, csid,csid_src_pad, vfe,0, True)
    # subdev devnodes
    def sd(ent):
        mm=devnode_of(I,L,ent); return find_dev('/dev/v4l-subdev',*mm)
    phy_d,csid_d,vfe_d,sen_d=sd(phy),sd(csid),sd(vfe),sd(sid)
    sfd=os.open(sen_d,os.O_RDWR)
    swh=os.environ.get("SWH")               # e.g. "4000x3000:0x300a" force a sensor mode
    if swh:
        wh,_,cc=swh.partition(":")
        sw,sh=(int(x) for x in wh.split("x"))
        try:
            subdev_fmt(sfd,0,False,int(cc,16) if cc else 0x300a,sw,sh)
            print(f"  set sensor fmt {sw}x{sh}")
        except OSError as e: print(f"  sensor S_FMT failed: {e}")
    code,w,h=subdev_fmt(sfd,0,True)         # sensor current format
    print(f"sensor fmt code=0x{code:x} {w}x{h}")
    tp=os.environ.get("TP")
    if tp is not None:
        VIDIOC_S_CTRL=IOWR(V,28,8)
        try:
            fcntl.ioctl(sfd,VIDIOC_S_CTRL,struct.pack("<Ii",0x009f0903,int(tp)),True)
            print(f"  set TEST_PATTERN={tp} on sensor")
        except OSError as e: print(f"  TEST_PATTERN set failed: {e}")
    # propagate down the chain. In qcom-camss setting the sink pad (0) makes the
    # source pad mirror it; setting source pads may be rejected, so try both but
    # tolerate failures on source pads.
    for dpath,pads in [(phy_d,[0,1]),(csid_d,[0,csid_src_pad]),(vfe_d,[0,1])]:
        f=os.open(dpath,os.O_RDWR)
        for pad in pads:
            try: subdev_fmt(f,pad,False,code,w,h)
            except OSError as e: print(f"  {dpath} pad{pad} S_FMT: {e}")
        os.close(f)
    os.close(sfd)
    # video node
    vmm=devnode_of(I,L,vid); vpath=find_dev('/dev/video',*vmm)
    vfd=os.open(vpath,os.O_RDWR)
    pixfmt=pick_raw_pixfmt(vfd, code)
    w2,h2,pf,sizeimage,nplanes,bpl=vid_set_fmt(vfd,w,h,pixfmt)
    print(f"video {vpath} fmt {w2}x{h2} fourcc={pf.to_bytes(4,'little')} size={sizeimage} planes={nplanes} bpl={bpl}")
    n=reqbufs(vfd,4)
    maps=[]
    for i in range(n):
        off,length=querybuf(vfd,i)
        mm=mmap.mmap(vfd,length,mmap.MAP_SHARED,mmap.PROT_READ,offset=off)
        maps.append((mm,length)); qbuf(vfd,i)
    struct.pack("<i",2)
    fcntl.ioctl(vfd,VIDIOC_STREAMON,struct.pack("<i",9))
    import select,time
    saved=False; got=0; deadline=time.time()+12
    while got<frames and time.time()<deadline:
        r,_,_=select.select([vfd],[],[],2)
        if not r: continue           # no frame ready yet
        try: idx,used=dqbuf(vfd)
        except OSError as e:
            if e.errno==11: continue  # EAGAIN
            print("DQBUF err",e); break
        got+=1
        if not saved:
            data=bytes(maps[idx][0][:used if used else maps[idx][1]])
            open(outpath,'wb').write(data)
            mean=sum(data)/len(data)
            var=sum((b-mean)**2 for b in data[:100000])/min(len(data),100000)
            print(f"saved {outpath} {len(data)} bytes mean={mean:.1f} std={var**0.5:.1f}")
            saved=True
        qbuf(vfd,idx)
    fcntl.ioctl(vfd,VIDIOC_STREAMOFF,struct.pack("<i",9))
    print(f"captured {got} frames")
    os.close(vfd); os.close(mfd)

GPIOHANDLE_REQUEST_OUTPUT=(1<<1)
GPIOHANDLE_GET_LINEHANDLE=IOWR(0xB4,0x03,364)
def hold_gpio(chipidx, line, val):
    fd=os.open(f"/dev/gpiochip{chipidx}",os.O_RDONLY)
    b=bytearray(364)
    struct.pack_into("<I",b,0,line)                 # lineoffsets[0]
    struct.pack_into("<I",b,256,GPIOHANDLE_REQUEST_OUTPUT)  # flags
    b[260+0]=val & 1                                # default_values[0]
    b[260+64:260+64+8]=b"camcap\0\0"               # consumer_label
    struct.pack_into("<I",b,260+64+32,1)            # lines=1
    fcntl.ioctl(fd,GPIOHANDLE_GET_LINEHANDLE,b,True)
    lfd=struct.unpack_from("<i",b,360)[0]
    os.close(fd)
    print(f"gpio chip{chipidx} line{line}={val} held (fd {lfd})")
    return lfd  # keep open to hold the value

if __name__=='__main__':
    cmd=sys.argv[1] if len(sys.argv)>1 else 'dump'
    if cmd=='dump': dump()
    elif cmd=='capture':
        # capture <sensor> <csid> <csid_src_pad> <video> <out> <frames> [gpiochip gpioline gpioval]
        _held=None
        if len(sys.argv)>=11:
            _held=hold_gpio(int(sys.argv[8]),int(sys.argv[9]),int(sys.argv[10]))
        capture(sys.argv[2],sys.argv[3],int(sys.argv[4]),sys.argv[5],sys.argv[6],int(sys.argv[7]))
    elif cmd=='gpio':
        # gpio <chip> <line> <val> <hold_seconds>
        import time
        hold_gpio(int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4])); time.sleep(int(sys.argv[5]))

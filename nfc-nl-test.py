import socket, struct, os, time
NG=16; CTRL_GETFAMILY=3; A_FAMILY_ID=1; A_FAMILY_NAME=2
GET_DEVICE=1; DEV_UP=2; DEV_DOWN=3; START_POLL=6; STOP_POLL=7
A_DEV_INDEX=1; A_PROTOCOLS=3
REQ=1; ACK=4; ERR=2; pid=os.getpid(); seqn=[10]
def nlmsg(t,f,seq,p): return struct.pack("IHHII",16+len(p),t,f,seq,pid)+p
def genl(c,v,a=b""): return struct.pack("BBH",c,v,0)+a
def attr(t,d):
    l=4+len(d); return struct.pack("HH",l,t)+d+b"\x00"*((4-(l%4))%4)
def pattr(b):
    a={};i=0
    while i+4<=len(b):
        l,t=struct.unpack("HH",b[i:i+4])
        if l<4:break
        a[t]=b[i+4:i+l];i+=(l+3)&~3
    return a
s=socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,NG);s.bind((0,0));s.settimeout(3)
def rseq(seq):
    while True:
        try: buf=s.recv(16384)
        except socket.timeout: return (None,0)
        i=0
        while i+16<=len(buf):
            l,t,f,sq,pd=struct.unpack("IHHII",buf[i:i+16]); 
            if l<16:break
            if sq==seq:
                if t==ERR: return (t, struct.unpack("i",buf[i+16:i+20])[0])
                return (t,0)
            i+=(l+3)&~3
seq=seqn[0];seqn[0]+=1
s.send(nlmsg(16,REQ,seq,genl(CTRL_GETFAMILY,1,attr(A_FAMILY_NAME,b"nfc\x00"))))
# read family reply (match seq)
while True:
    buf=s.recv(16384); i=0; got=None
    while i+16<=len(buf):
        l,t,ff,sq,pd=struct.unpack("IHHII",buf[i:i+16])
        if sq==seq: got=pattr(buf[i+20:i+l])
        i+=(l+3)&~3
    if got: break
fam=struct.unpack("H",got[A_FAMILY_ID][:2])[0]; print("nfc family id:",fam)
idx=attr(A_DEV_INDEX,struct.pack("I",0))
def call(cmd,a=b""):
    seq=seqn[0];seqn[0]+=1
    s.send(nlmsg(fam,REQ|ACK,seq,genl(cmd,1,a)))
    return rseq(seq)
def show(n,r):
    e=r[1]; print("%-11s: %s"%(n,"OK" if e==0 else "err=%d %s"%(e,os.strerror(-e) if e<0 else "")))
show("DEV_UP",   call(DEV_UP,idx));   time.sleep(1)
show("START_POLL",call(START_POLL, idx+attr(A_PROTOCOLS,struct.pack("I",0x1e)))); time.sleep(2)
show("STOP_POLL",call(STOP_POLL,idx)); time.sleep(0.3)
show("DEV_DOWN", call(DEV_DOWN,idx))

import struct, os, zlib, bz2, lzma

def read_varint(buf, i):
    v = shift = 0
    while True:
        b = buf[i]; i += 1
        v |= (b & 0x7f) << shift
        if not (b & 0x80): return v, i
        shift += 7

def iter_fields(buf):
    i = 0
    while i < len(buf):
        tag, i = read_varint(buf, i)
        fn, wt = tag >> 3, tag & 7
        if wt == 0: val, i = read_varint(buf, i)
        elif wt == 2:
            ln, i = read_varint(buf, i)
            val = buf[i:i+ln]; i += ln
        elif wt == 1: val = buf[i:i+8]; i += 8
        elif wt == 5: val = buf[i:i+4]; i += 4
        else: break
        yield fn, wt, val

os.makedirs(r"C:\mtk\stock", exist_ok=True)
want = {
    "audio_dsp","boot","cam_vpu1","cam_vpu2","cam_vpu3","dpm","dtbo","gz","lk",
    "mcupm","md1img","mitee","pi_img","preloader_raw","scp","spmfw","sspm",
    "tee","vbmeta","vbmeta_system","vbmeta_vendor","system_ext"
}
# Type enum: REPLACE=0, REPLACE_BZ=1, ZERO=6, REPLACE_XZ=8
with open(r"C:\Users\met\Desktop\telefon-yedek\firmware\payload.bin", "rb") as f:
    assert f.read(4) == b"CrAU"
    ver = struct.unpack(">Q", f.read(8))[0]
    msize = struct.unpack(">Q", f.read(8))[0]
    sigsz = struct.unpack(">I", f.read(4))[0]
    man = f.read(msize)
    f.read(sigsz)
    data_off = f.tell()
    blk_sz = 4096
    for fn, wt, val in iter_fields(man):
        if fn == 1 and wt == 0: blk_sz = val

    for fn, wt, val in iter_fields(man):
        if fn == 13 and wt == 2:
            pname = None; ops = []; new_sz = 0
            for pfn, pwt, pval in iter_fields(val):
                if pfn == 1 and pwt == 2: pname = pval.decode()
                elif pfn == 7 and pwt == 2:
                    for nfn, nwt, nval in iter_fields(pval):
                        if nfn == 1 and nwt == 0: new_sz = nval
                elif pfn == 8 and pwt == 2:
                    op_type = 0; doff = 0; dlen = 0; dst_ext = []
                    for ofn, owt, oval in iter_fields(pval):
                        if ofn == 1 and owt == 0: op_type = ofn if False else oval
                        elif ofn == 2 and owt == 0: doff = oval
                        elif ofn == 3 and owt == 0: dlen = oval
                        elif ofn == 6 and owt == 2:
                            sb = 0; nb = 0
                            for efn, ewt, evalv in iter_fields(oval):
                                if efn == 1 and ewt == 0: sb = evalv
                                elif efn == 2 and ewt == 0: nb = evalv
                            dst_ext.append((sb, nb))
                    ops.append((op_type, doff, dlen, dst_ext))
            if pname in want:
                outp = rf"C:\mtk\stock\{pname}.img"
                with open(outp, "wb") as o:
                    for op_type, doff, dlen, dst_ext in ops:
                        f.seek(data_off + doff)
                        raw = f.read(dlen)
                        if op_type == 0: dec = raw
                        elif op_type == 1: dec = bz2.decompress(raw)
                        elif op_type == 8: dec = lzma.decompress(raw)
                        elif op_type == 6: dec = b"\x00" * sum(nb*blk_sz for _, nb in dst_ext)
                        else: raise ValueError(f"Unsupported op {op_type} in {pname}")
                        pos = 0
                        for sb, nb in dst_ext:
                            o.seek(sb * blk_sz)
                            chunk = dec[pos:pos + nb*blk_sz]
                            o.write(chunk)
                            pos += len(chunk)
                    o.truncate(new_sz)
                print(f"Extracted {pname:15s} ({new_sz/1048576:7.2f} MB)")

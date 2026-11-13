import struct, os

def simg2img(src, dst):
    with open(src, "rb") as f, open(dst, "wb") as out:
        hdr = f.read(28)
        magic, maj, minv, fhdr_sz, chdr_sz, blk_sz, tot_blks, tot_chunks, csum = struct.unpack("<IHHHHIIII", hdr)
        assert magic == 0xED26FF3A, f"Not sparse: {hex(magic)}"
        if fhdr_sz > 28:
            f.read(fhdr_sz - 28)
        total_out = 0
        for i in range(tot_chunks):
            chdr = f.read(12)
            ctype, resv, chunk_sz, total_sz = struct.unpack("<HHII", chdr)
            if chdr_sz > 12:
                f.read(chdr_sz - 12)
            data_sz = total_sz - chdr_sz
            out_bytes = chunk_sz * blk_sz
            if ctype == 0xCAC1:  # RAW
                rem = data_sz
                while rem > 0:
                    buf = f.read(min(rem, 4 * 1024 * 1024))
                    out.write(buf)
                    rem -= len(buf)
            elif ctype == 0xCAC2:  # FILL
                fill = f.read(4)
                if data_sz > 4: f.read(data_sz - 4)
                pat = fill * (blk_sz // 4)
                chunk_pat = pat * 256  # 1MB
                blks_rem = chunk_sz
                while blks_rem >= 256:
                    out.write(chunk_pat)
                    blks_rem -= 256
                if blks_rem > 0:
                    out.write(pat * blks_rem)
            elif ctype == 0xCAC3:  # DONT_CARE
                if data_sz > 0: f.read(data_sz)
                out.seek(out_bytes, os.SEEK_CUR)
            elif ctype == 0xCAC4:  # CRC32
                f.read(data_sz)
            else:
                raise ValueError(f"Unknown chunk {hex(ctype)}")
            if ctype != 0xCAC4:
                total_out += out_bytes
        # Ensure exact file size when trailing DONT_CARE
        out.truncate(tot_blks * blk_sz)
    print(f"Converted {src} -> {dst} ({os.path.getsize(dst)/1048576:.1f} MB)")

simg2img(r"C:\mtk\images\super.img", r"C:\mtk\super_raw.img")
simg2img(r"C:\mtk\images\userdata.img", r"C:\mtk\userdata_raw.img")

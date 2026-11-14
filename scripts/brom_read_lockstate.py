import os
import sys
import struct

sys.path.insert(0, r"C:\mtk")
import flash_eng_cached  # noqa: F401

from mtkclient.Library.DA.mtk_da_handler import DaHandler
from mtkclient.Library.Hardware.seccfg import SecCfgV4
from mtkclient import mtk as mtk_entry

OUT_SECCFG = r"C:\mtk\v125\cur_seccfg.bin"
OUT_OEM_MISC1 = r"C:\mtk\v125\cur_oem_misc1.bin"

_orig_handle = DaHandler.handle_da_cmds


def _patched_handle(self, mtk, cmd: str, args):
    if cmd == "da" and getattr(args, "subcmd", None) == "seccfg" and getattr(args, "flag", None) == "diag_lock":
        print("[diag_lock] Reading seccfg and oem_misc1...", flush=True)
        self.da_read("seccfg,oem_misc1", "user", f"{OUT_SECCFG},{OUT_OEM_MISC1}", display=True)

        if os.path.exists(OUT_SECCFG):
            sec = open(OUT_SECCFG, "rb").read()
            print(f"[diag_lock] seccfg size={len(sec)}, head64={sec[:64].hex()}", flush=True)
            if len(sec) >= 28:
                vals = struct.unpack("<7I", sec[:28])
                print(
                    f"[diag_lock] seccfg raw: magic={hex(vals[0])} ver={vals[1]} size={vals[2]} "
                    f"lock_state={vals[3]} dm_verity={vals[4]} sboot_rt={vals[5]} endflag={hex(vals[6])}",
                    flush=True,
                )
            v4 = SecCfgV4(mtk.daloader.xflash.hwcrypto if hasattr(mtk.daloader, "xflash") else None, mtk)
            try:
                parsed = v4.parse(sec)
                print(f"[diag_lock] SecCfgV4.parse={parsed} hwtype={v4.hwtype} lock_state={v4.lock_state}", flush=True)
            except Exception as e:
                print(f"[diag_lock] SecCfgV4.parse error: {e}", flush=True)

        if os.path.exists(OUT_OEM_MISC1):
            om = open(OUT_OEM_MISC1, "rb").read()
            nz_blocks = []
            for off in range(0, len(om), 512):
                blk = om[off:off + 512]
                if any(b != 0 for b in blk):
                    nz_blocks.append(off)
            print(f"[diag_lock] oem_misc1 size={len(om)}, nonzero 512B blocks={len(nz_blocks)}", flush=True)
            for off in nz_blocks[:16]:
                blk = om[off:off + 64]
                asc = "".join(chr(b) if 32 <= b < 127 else "." for b in blk)
                print(f"  @{hex(off)}: {blk.hex()}  |{asc}|", flush=True)

        if os.path.exists(os.path.join(self.mtk.config.hwparam_path, ".state")):
            os.remove(os.path.join(self.mtk.config.hwparam_path, ".state"))
        print("[diag_lock] Resetting device...", flush=True)
        mtk.daloader.shutdown(bootmode=0)
        return
    return _orig_handle(self, mtk, cmd, args)


DaHandler.handle_da_cmds = _patched_handle

if __name__ == "__main__":
    sys.argv = [
        sys.argv[0],
        "da", "seccfg", "diag_lock",
        "--preloader", r"C:\mtk\v125\agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global\images\preloader_agate.bin",
        "--auth", r"C:\mtk\auth_sv5.auth",
    ]
    sys.exit(mtk_entry.main() or 0)

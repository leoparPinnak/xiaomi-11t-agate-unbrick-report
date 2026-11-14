import os
import sys

sys.path.insert(0, r"C:\mtk")
import flash_eng_cached  # noqa: F401

from mtkclient.Library.DA.mtk_da_handler import DaHandler
from mtkclient import mtk as mtk_entry

ZERO_64K = r"C:\mtk\v125\zero_64k.bin"
V13_LK = r"C:\mtk\stock\lk.img"
VERIFY_OEM = r"C:\mtk\v125\verify_oem_misc1_head.bin"

_orig_handle = DaHandler.handle_da_cmds


def _patched_handle(self, mtk, cmd: str, args):
    if cmd == "da" and getattr(args, "subcmd", None) == "seccfg" and getattr(args, "flag", None) == "unlock_lk13":
        print("[unlock_lk13] 1) Zeroing first 64KB of oem_misc1 & writing V13.0.2.0 lk.img to lk_a...", flush=True)
        self.da_write("user", [ZERO_64K, V13_LK], ["oem_misc1", "lk_a"])

        print("[unlock_lk13] 2) Reading back oem_misc1 first 64KB to verify...", flush=True)
        self.da_read("oem_misc1", "user", VERIFY_OEM, offset=0, length=65536, display=False)
        if os.path.exists(VERIFY_OEM):
            d = open(VERIFY_OEM, "rb").read()
            nz = sum(1 for b in d if b != 0)
            print(f"[unlock_lk13] oem_misc1 head64KB nonzero bytes = {nz}, first16 = {d[:16].hex()}", flush=True)

        if os.path.exists(os.path.join(self.mtk.config.hwparam_path, ".state")):
            os.remove(os.path.join(self.mtk.config.hwparam_path, ".state"))
        print("[unlock_lk13] 3) Resetting device...", flush=True)
        mtk.daloader.shutdown(bootmode=0)
        return
    return _orig_handle(self, mtk, cmd, args)


DaHandler.handle_da_cmds = _patched_handle

if __name__ == "__main__":
    sys.argv = [
        sys.argv[0],
        "da", "seccfg", "unlock_lk13",
        "--preloader", r"C:\mtk\v125\agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global\images\preloader_agate.bin",
        "--auth", r"C:\mtk\auth_sv5.auth",
    ]
    sys.exit(mtk_entry.main() or 0)

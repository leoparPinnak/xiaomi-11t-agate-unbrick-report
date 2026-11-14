import sys
import os

sys.path.insert(0, r"C:\mtk")
import flash_eng_cached  # noqa: F401

from mtkclient.Library.DA.mtk_da_handler import DaHandler
from mtkclient import mtk as mtk_entry

_orig_handle = DaHandler.handle_da_cmds

def _patched_handle(self, mtk, cmd: str, args):
    if cmd == "da" and getattr(args, "subcmd", None) == "seccfg" and getattr(args, "flag", None) == "reunlock":
        print("[reunlock] Step 1: seccfg lock ...", flush=True)
        r1 = mtk.daloader.seccfg("lock", critical=False)
        print("[reunlock] lock result:", r1, flush=True)
        print("[reunlock] Step 2: seccfg unlock ...", flush=True)
        r2 = mtk.daloader.seccfg("unlock", critical=False)
        print("[reunlock] unlock result:", r2, flush=True)
        print("[reunlock] Resetting device...", flush=True)
        if os.path.exists(os.path.join(self.mtk.config.hwparam_path, ".state")):
            os.remove(os.path.join(self.mtk.config.hwparam_path, ".state"))
        mtk.daloader.shutdown(bootmode=0)
        return
    return _orig_handle(self, mtk, cmd, args)

DaHandler.handle_da_cmds = _patched_handle

if __name__ == "__main__":
    sys.argv = [
        sys.argv[0],
        "da", "seccfg", "reunlock",
        "--preloader", r"C:\mtk\v125\agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global\images\preloader_agate.bin",
        "--auth", r"C:\mtk\auth_sv5.auth",
    ]
    sys.exit(mtk_entry.main() or 0)

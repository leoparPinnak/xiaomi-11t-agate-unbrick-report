import subprocess, os, time, datetime

FB = r"C:\mtk\platform-tools\fastboot.exe"
IMG_DIR = r"C:\mtk\v125\agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global\images"
LOG = r"C:\mtk\v125\flash_v1259.log"

def log(m):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {m}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)

def p(name): return os.path.join(IMG_DIR, name)

steps = [
    (["flash", "crclist", p("crclist.txt")], 30),
    (["flash", "sparsecrclist", p("sparsecrclist.txt")], 30),
    (["flash", "preloader_ab", p("preloader_agate.bin")], 60),
    (["erase", "boot_ab"], 30),
    (["erase", "expdb"], 30),
    (["erase", "metadata"], 30),
    (["flash", "vbmeta_ab", p("vbmeta.img")], 30),
    (["flash", "vbmeta_system_ab", p("vbmeta_system.img")], 30),
    (["flash", "vbmeta_vendor_ab", p("vbmeta_vendor.img")], 30),
    (["flash", "md1img_ab", p("md1img.img")], 120),
    (["flash", "spmfw_ab", p("spmfw.img")], 30),
    (["flash", "audio_dsp_ab", p("audio_dsp.img")], 60),
    (["flash", "pi_img_ab", p("pi_img.img")], 30),
    (["flash", "dpm_ab", p("dpm.img")], 30),
    (["flash", "scp_ab", p("scp.img")], 60),
    (["flash", "sspm_ab", p("sspm.img")], 60),
    (["flash", "mcupm_ab", p("mcupm.img")], 60),
    (["flash", "cam_vpu1_ab", p("cam_vpu1.img")], 60),
    (["flash", "cam_vpu2_ab", p("cam_vpu2.img")], 60),
    (["flash", "cam_vpu3_ab", p("cam_vpu3.img")], 30),
    (["flash", "gz_ab", p("gz.img")], 60),
    (["flash", "lk_ab", p("lk.img")], 60),
    (["flash", "boot_ab", p("boot.img")], 120),
    (["flash", "dtbo_ab", p("dtbo.img")], 60),
    (["flash", "tee_ab", p("tee.img")], 60),
    (["flash", "mitee_ab", p("mitee.img")], 60),
    (["flash", "logo_ab", p("logo.bin")], 60),
    (["flash", "super", p("super.img")], 900),
    (["flash", "rescue", p("rescue.img")], 60),
    (["flash", "cust", p("cust.img")], 300),
    (["flash", "userdata", p("userdata.img")], 300),
    (["oem", "cdms"], 30),
    (["set_active", "a"], 30),
    (["reboot"], 30),
]

open(LOG, "w", encoding="utf-8").close()
log("V12.5.9.0.RKWMIXM (Android 11) flash basliyor...")

for args, tout in steps:
    label = " ".join(args[:2])
    log(f">>> fastboot {label} ...")
    t0 = time.time()
    r = subprocess.run([FB] + args, capture_output=True, text=True, timeout=tout)
    dt = time.time() - t0
    out = (r.stdout + "\n" + r.stderr).strip()
    if r.returncode != 0:
        log(f"HATA! {label} rc={r.returncode} ({dt:.1f}s)\n{out}")
        raise SystemExit(1)
    summary = out.splitlines()[-1] if out else "OK"
    log(f"  OK ({dt:.1f}s): {summary}")

log(">>> TUM V12.5.9.0 (ANDROID 11) KURULUMU TAMAMLANDI! <<<")

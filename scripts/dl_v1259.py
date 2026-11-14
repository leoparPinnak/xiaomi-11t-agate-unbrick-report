import os, subprocess, threading, time

URL = "https://cdnorg.d.miui.com/V12.5.9.0.RKWMIXM/agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global_a47de69a25.tgz"
TOTAL = 5909994348
N = 8
DIR = r"C:\mtk\v125"
OUT = os.path.join(DIR, "v1259.tgz")
LOG = os.path.join(DIR, "dl.log")

def log(m):
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
    print(line, flush=True)

open(LOG, "w", encoding="utf-8").close()
chunk = TOTAL // N
ranges = [(i, i*chunk, (TOTAL-1) if i==N-1 else ((i+1)*chunk - 1)) for i in range(N)]
errs = []

def worker(i, s, e):
    part = os.path.join(DIR, f"part_{i}.bin")
    expected = e - s + 1
    for attempt in range(1, 6):
        if os.path.exists(part) and os.path.getsize(part) == expected:
            log(f"part_{i} hazir ({expected} B)")
            return
        cmd = ["curl.exe", "-s", "-L", "--fail", "--retry", "5", "--retry-delay", "3",
               "-r", f"{s}-{e}", "-o", part, URL]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        sz = os.path.getsize(part) if os.path.exists(part) else 0
        if r.returncode == 0 and sz == expected:
            log(f"part_{i} OK ({sz/1048576:.1f} MB)")
            return
        log(f"part_{i} deneme {attempt} fail rc={r.returncode} sz={sz}/{expected}")
        time.sleep(2)
    errs.append(i)

log(f"8 parcali indirme basladi -> {OUT}")
t0 = time.time()
ts = [threading.Thread(target=worker, args=rng) for rng in ranges]
for t in ts: t.start()
for t in ts: t.join()

if errs:
    log(f"HATA: basarisiz parcalar {errs}")
    raise SystemExit(1)

log("Parcalar birlestiriliyor...")
with open(OUT, "wb") as fo:
    for i, s, e in ranges:
        part = os.path.join(DIR, f"part_{i}.bin")
        with open(part, "rb") as fi:
            while True:
                buf = fi.read(4*1048576)
                if not buf: break
                fo.write(buf)
        os.remove(part)

final_sz = os.path.getsize(OUT)
log(f"TAMAM! {OUT} = {final_sz} B (beklenen {TOTAL}) sure={time.time()-t0:.1f}s")
assert final_sz == TOTAL

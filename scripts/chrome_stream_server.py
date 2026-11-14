#!/usr/bin/env python3
import asyncio
import base64
import glob
import json
import os
import re
import struct
import subprocess
import time
from urllib.parse import quote
import aiohttp
from aiohttp import web

CDP_PORT = 9222
HTTP_PORT = 8080
USER_DIR = "/tmp/chrome_profile"
XDG_DIR = "/tmp/xdg_chrome_rt"
HWJPEG_SOCK = "/tmp/weston_hwjpeg.sock"

active_target_id = None
latest_frame = None
last_frame_ts = 0.0
frame_event = asyncio.Event()
ws_clients = set()

# Default mode: hardware JPEG (/dev/video3 via weston_hwjpeg.so) at 1920x1080
stream_cfg = {
    "engine": "hwjpeg",     # "hwjpeg" (hardware /dev/video3) | "cdp" (Native PNG / 2K / 4K)
    "format": "jpeg",
    "quality": 90,
    "everyNthFrame": 1,
    "maxWidth": 1920,
    "maxHeight": 1080,
}

_prev_cpu = None
_cached_cpu_pct = 0.0

cdp_lock = asyncio.Lock()
active_ws = None
active_sess = None
cmd_id = 0
reader_task = None


def _rfile(path, default=""):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return default


def sample_cpu_pct():
    global _prev_cpu, _cached_cpu_pct
    line = _rfile("/proc/stat").splitlines()[0]
    parts = [int(x) for x in line.split()[1:8]]
    idle = parts[3] + parts[4]
    total = sum(parts)
    if _prev_cpu is not None:
        dt = total - _prev_cpu[0]
        di = idle - _prev_cpu[1]
        if dt > 0:
            _cached_cpu_pct = round(100.0 * (dt - di) / dt, 1)
    _prev_cpu = (total, idle)
    return _cached_cpu_pct


def collect_telemetry():
    cpu_pct = sample_cpu_pct()
    freqs = []
    for c in ("cpu0", "cpu4", "cpu7"):
        v = _rfile(f"/sys/devices/system/cpu/{c}/cpufreq/scaling_cur_freq", "0")
        freqs.append(int(v) // 1000 if v.isdigit() else 0)
    gov = _rfile("/sys/devices/system/cpu/cpufreq/policy0/scaling_governor", "-")

    gpu_pct = 0
    gpu_mhz = 0
    gpu_pwr = "IDLE"
    gpu_mb = 0.0
    gpu_ctx = 0
    ged = _rfile("/sys/kernel/ged/hal/gpu_utilization", "")
    if ged:
        try:
            gpu_pct = max(gpu_pct, int(ged.split()[0]))
        except Exception:
            pass
    mali = _rfile("/proc/mali/utilization", "")
    for _ in range(3):
        mu = re.search(r"gpu/cljs0/cljs1=(\d+)/(\d+)/(\d+)", mali)
        if mu:
            gpu_pct = max(gpu_pct, int(mu.group(1)), int(mu.group(2)), int(mu.group(3)))
        mpwr = re.search(r"\):(\d+)", mali)
        if mpwr and int(mpwr.group(1)) > 0:
            gpu_pwr = "ON"
        if gpu_pct > 0:
            break
        time.sleep(0.005)
        mali = _rfile("/proc/mali/utilization", "")

    gfreq = _rfile("/proc/gpufreq/gpufreq_var_dump", "")
    mf = re.search(r"idx:\s*\d+,\s*freq:\s*(\d+)", gfreq)
    if mf:
        gpu_mhz = int(mf.group(1)) // 1000
    mrf = re.search(r"\(real\)\s*freq:\s*(\d+)", gfreq)
    if mrf and int(mrf.group(1)) > 0:
        gpu_mhz = int(mrf.group(1)) // 1000
        gpu_pwr = "ON"
    mp = re.search(r"g_power_count\s*=\s*(\d+)", gfreq)
    if mp and int(mp.group(1)) > 0:
        gpu_pwr = "ON"

    mmem = _rfile("/proc/mali/memory_usage", "")
    mm = re.search(r"\((\d+)\s+bytes\)", mmem)
    if mm:
        gpu_mb = round(int(mm.group(1)) / (1024.0 * 1024.0), 1)
    gpu_ctx = mmem.count("kctx-")
    if gpu_pct > 0:
        gpu_pwr = "ON"

    opp_txt = _rfile("/proc/gpufreq/gpufreq_opp_freq", "")
    gpu_max_mode = "fixed OPP is enabled" in opp_txt

    mem_tot = mem_avail = swap_tot = swap_free = 0
    for l in _rfile("/proc/meminfo").splitlines():
        if l.startswith("MemTotal:"):
            mem_tot = int(l.split()[1]) // 1024
        elif l.startswith("MemAvailable:"):
            mem_avail = int(l.split()[1]) // 1024
        elif l.startswith("SwapTotal:"):
            swap_tot = int(l.split()[1]) // 1024
        elif l.startswith("SwapFree:"):
            swap_free = int(l.split()[1]) // 1024
    mem_used = max(0, mem_tot - mem_avail)

    temps = {}
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        tn = _rfile(os.path.join(z, "type"))
        tv = _rfile(os.path.join(z, "temp"))
        if tn and tv:
            try:
                c = int(tv) / 1000.0
                if -20.0 < c < 130.0:
                    temps[tn] = round(c, 1)
            except Exception:
                pass

    cap = _rfile("/sys/class/power_supply/battery/capacity", "0")
    stat = _rfile("/sys/class/power_supply/battery/status", "?")
    susp = _rfile("/sys/class/power_supply/battery/input_suspend", "0")
    cur_ua = int(_rfile("/sys/class/power_supply/battery/current_now", "0") or 0)
    volt_uv = int(_rfile("/sys/class/power_supply/battery/voltage_now", "0") or 0)
    watts = round(abs(cur_ua * volt_uv) / 1e12, 2)
    ma = round(abs(cur_ua) / 1000.0, 0)
    volts = round(volt_uv / 1e6, 2)

    up_s = _rfile("/proc/uptime", "0").split()[0]
    secs = int(float(up_s))
    uptime = f"{secs // 3600}h {(secs % 3600) // 60}m {secs % 60}s"

    return {
        "cpu_pct": cpu_pct,
        "cpu_freqs": freqs,
        "cpu_gov": gov,
        "gpu_pct": gpu_pct,
        "gpu_mhz": gpu_mhz,
        "gpu_pwr": gpu_pwr,
        "gpu_vram_mb": gpu_mb,
        "gpu_ctx": gpu_ctx,
        "gpu_max_mode": gpu_max_mode,
        "mem_used_mb": mem_used,
        "mem_tot_mb": mem_tot,
        "mem_pct": round(100.0 * mem_used / mem_tot, 1) if mem_tot else 0.0,
        "swap_used_mb": max(0, swap_tot - swap_free),
        "swap_tot_mb": swap_tot,
        "temps": {
            "cpu": temps.get("mtktscpu", 0.0),
            "ap": temps.get("mtktsAP", 0.0),
            "pmic": temps.get("mtktspmic", 0.0),
            "wifi": temps.get("mtktswmt", 0.0),
            "bat": temps.get("battery", 0.0),
        },
        "bat_pct": int(cap) if cap.isdigit() else 0,
        "bat_status": stat,
        "input_suspend": susp == "1",
        "watts": watts,
        "ma": int(ma),
        "volts": volts,
        "uptime": uptime,
        "stream_cfg": stream_cfg,
    }


async def cdp_send(method, params=None, fixed_id=None):
    global cmd_id
    async with cdp_lock:
        if active_ws is None or active_ws.closed:
            return False
        if fixed_id is None:
            cmd_id += 1
            mid = cmd_id
        else:
            mid = fixed_id
        await active_ws.send_json({"id": mid, "method": method, "params": params or {}})
        return True


async def fetch_pages():
    try:
        async with active_sess.get(f"http://127.0.0.1:{CDP_PORT}/json/list", timeout=aiohttp.ClientTimeout(total=2)) as r:
            items = await r.json()
            return [p for p in items if p.get("type") == "page" and "webSocketDebuggerUrl" in p]
    except Exception:
        return []


async def _send_one_ws(ws, raw_bytes):
    try:
        await asyncio.wait_for(ws.send_bytes(raw_bytes), timeout=0.35)
    except Exception:
        ws_clients.discard(ws)


def publish_frame(raw_bytes):
    global latest_frame, last_frame_ts
    latest_frame = raw_bytes
    last_frame_ts = time.monotonic()
    frame_event.set()
    frame_event.clear()
    for ws in list(ws_clients):
        if ws.closed:
            ws_clients.discard(ws)
        else:
            asyncio.create_task(_send_one_ws(ws, raw_bytes))


async def hwjpeg_socket_reader():
    """Reads zero-CPU hardware-encoded JPEG frames directly from Weston (/dev/video3)."""
    while True:
        try:
            if not os.path.exists(HWJPEG_SOCK):
                await asyncio.sleep(0.3)
                continue
            reader, writer = await asyncio.open_unix_connection(HWJPEG_SOCK, limit=16 * 1024 * 1024)
            try:
                while True:
                    hdr = await reader.readexactly(4)
                    sz = struct.unpack("<I", hdr)[0]
                    if sz <= 0 or sz > 16 * 1024 * 1024:
                        break
                    jpg = await reader.readexactly(sz)
                    if stream_cfg["engine"] == "hwjpeg":
                        publish_frame(jpg)
            finally:
                writer.close()
        except Exception:
            await asyncio.sleep(0.4)


async def apply_tab_stream_mode():
    if stream_cfg["engine"] == "hwjpeg":
        await cdp_send("Page.stopScreencast")
        await cdp_send("Emulation.clearDeviceMetricsOverride")
        # Trigger tiny repaint so weston_hwjpeg emits fresh frame immediately if static
        if os.path.exists("/dev/shm/weston_hw.jpg"):
            try:
                publish_frame(open("/dev/shm/weston_hw.jpg", "rb").read())
            except Exception:
                pass
    else:
        await cdp_send("Page.stopScreencast")
        await cdp_send("Emulation.setDeviceMetricsOverride", {
            "width": stream_cfg["maxWidth"], "height": stream_cfg["maxHeight"], "deviceScaleFactor": 1, "mobile": False
        })
        sc_params = {
            "format": stream_cfg["format"],
            "maxWidth": stream_cfg["maxWidth"],
            "maxHeight": stream_cfg["maxHeight"],
            "everyNthFrame": stream_cfg["everyNthFrame"],
        }
        if stream_cfg["format"] == "jpeg":
            sc_params["quality"] = stream_cfg["quality"]
        await cdp_send("Page.startScreencast", sc_params)
        shot_params = {"format": stream_cfg["format"]}
        if stream_cfg["format"] == "jpeg":
            shot_params["quality"] = stream_cfg["quality"]
        await cdp_send("Page.captureScreenshot", shot_params, fixed_id=900001)


async def attach_to_tab(target_id=None):
    global active_target_id, active_ws, reader_task

    pages = await fetch_pages()
    if not pages:
        return False

    chosen = None
    if target_id:
        for p in pages:
            if p["id"] == target_id:
                chosen = p
                break
    if not chosen:
        chosen = pages[0]

    if chosen["id"] == active_target_id and active_ws is not None and not active_ws.closed:
        return True

    if reader_task and not reader_task.done():
        reader_task.cancel()
        try:
            await reader_task
        except asyncio.CancelledError:
            pass
    if active_ws and not active_ws.closed:
        try:
            await active_ws.send_json({"id": 999999, "method": "Page.stopScreencast"})
            await active_ws.close()
        except Exception:
            pass

    active_target_id = chosen["id"]
    try:
        async with active_sess.get(f"http://127.0.0.1:{CDP_PORT}/json/activate/{active_target_id}", timeout=aiohttp.ClientTimeout(total=1.5)) as _:
            pass
    except Exception:
        pass

    active_ws = await active_sess.ws_connect(chosen["webSocketDebuggerUrl"], max_msg_size=64 * 1024 * 1024)

    async def _read_loop(ws):
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if data.get("method") == "Page.screencastFrame":
                    params = data["params"]
                    await cdp_send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
                    if stream_cfg["engine"] == "cdp":
                        publish_frame(base64.b64decode(params["data"]))
                elif data.get("id") == 900001 and "result" in data and "data" in data["result"]:
                    if stream_cfg["engine"] == "cdp":
                        publish_frame(base64.b64decode(data["result"]["data"]))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("reader error:", e, flush=True)

    reader_task = asyncio.create_task(_read_loop(active_ws))
    await cdp_send("Page.enable")
    await cdp_send("Page.bringToFront")
    await apply_tab_stream_mode()
    return True


async def launch_weston_hw():
    os.makedirs(XDG_DIR, mode=0o700, exist_ok=True)
    os.chmod(XDG_DIR, 0o700)
    if os.path.exists(os.path.join(XDG_DIR, "wayland-1")) and os.path.exists(HWJPEG_SOCK):
        return
    subprocess.run(["pkill", "-f", "weston --backend=headless"], stderr=subprocess.DEVNULL)
    await asyncio.sleep(0.3)
    env = {
        **os.environ,
        "XDG_RUNTIME_DIR": XDG_DIR,
        "HWJPEG_SOCK": HWJPEG_SOCK,
        "HWJPEG_FLIP_Y": "0",
    }
    subprocess.Popen(
        [
            "/usr/bin/weston",
            "--backend=headless-backend.so",
            "--use-pixman",
            "--shell=kiosk-shell.so",
            "--modules=/usr/local/lib/weston_hwjpeg.so",
            "--socket=wayland-1",
            "--width=1920",
            "--height=1080",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    for _ in range(40):
        if os.path.exists(os.path.join(XDG_DIR, "wayland-1")) and os.path.exists(HWJPEG_SOCK):
            break
        await asyncio.sleep(0.1)


async def launch_chromium_clean():
    chrome_env = {
        **os.environ,
        "XDG_RUNTIME_DIR": XDG_DIR,
        "WAYLAND_DISPLAY": "wayland-1",
        "LD_LIBRARY_PATH": "/usr/local/hybris/lib",
        "HYBRIS_LD_LIBRARY_PATH": (
            "/mnt/avendor/lib64:/mnt/avendor/lib64/egl:/mnt/avendor/lib64/hw:"
            "/mnt/asystem/system/lib64:/mnt/asystem/system/lib64/bootstrap:"
            "/apex/com.android.runtime/lib64/bionic"
        ),
        "HYBRIS_EGLPLATFORM": "wayland",
        "LIBEGL": "/mnt/avendor/lib64/egl/libGLES_mali.so",
        "LIBGLESV2": "/mnt/avendor/lib64/egl/libGLES_mali.so",
        "DBUS_SESSION_BUS_ADDRESS": "disabled:",
    }
    # Background tab throttling is KEPT ENABLED so opening 10+ tabs never steals FPS from active tab!
    subprocess.Popen(
        [
            "/usr/bin/chromium",
            "--no-sandbox",
            "--test-type",
            "--disable-dev-shm-usage",
            "--ozone-platform=wayland",
            "--use-gl=angle",
            "--use-angle=gles",
            "--disable-vulkan",
            "--disable-features=Vulkan,Translate,OptimizationHints,MediaRouter,InterestCohort",
            "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization",
            "--enable-webgl",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--hide-crash-restore-bubble",
            "--disable-infobars",
            "--password-store=basic",
            "--use-mock-keychain",
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            "--window-size=1920,1080",
            f"--user-data-dir={USER_DIR}",
            "https://webglsamples.org/aquarium/aquarium.html",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=chrome_env,
    )


async def cdp_supervisor():
    global active_sess
    os.makedirs(USER_DIR, exist_ok=True)
    await launch_weston_hw()
    asyncio.create_task(hwjpeg_socket_reader())

    active_sess = aiohttp.ClientSession()
    pages = await fetch_pages()
    if not pages:
        await launch_chromium_clean()
        for _ in range(40):
            pages = await fetch_pages()
            if pages:
                break
            await asyncio.sleep(0.3)

    await attach_to_tab()

    while True:
        await asyncio.sleep(1.0)
        if active_ws is None or active_ws.closed:
            pages = await fetch_pages()
            if not pages:
                await launch_weston_hw()
                await launch_chromium_clean()
                await asyncio.sleep(2.0)
            await attach_to_tab()
        elif stream_cfg["engine"] == "cdp" and time.monotonic() - last_frame_ts > 1.2 and ws_clients:
            try:
                shot_params = {"format": stream_cfg["format"]}
                if stream_cfg["format"] == "jpeg":
                    shot_params["quality"] = stream_cfg["quality"]
                await cdp_send("Page.captureScreenshot", shot_params, fixed_id=900001)
            except Exception:
                pass


HTML = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xiaomi 11T · Mali-G77 & HW-JPEG Console</title>
<style>
  :root {
    --bg: #080b10;
    --surface: #101722;
    --surface2: #16202e;
    --surface3: #1e2b3d;
    --border: #253447;
    --text: #e6eef8;
    --muted: #8496ad;
    --accent: #00e599;
    --accent2: #38bdf8;
    --danger: #ef4444;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%; background: var(--bg); color: var(--text);
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
  }
  .app { display: flex; flex-direction: column; height: 100vh; width: 100vw; }

  .tabbar {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 10px 0 10px;
    background: #06090d; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .brand {
    display: flex; align-items: center; gap: 6px; padding: 4px 8px 6px 2px;
    font-size: 11px; font-weight: 700; letter-spacing: .5px; color: var(--accent);
    white-space: nowrap;
  }
  .brand-dot {
    width: 7px; height: 7px; border-radius: 50%; background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
  }
  .tabs-wrap {
    display: flex; align-items: flex-end; gap: 4px; flex: 1; min-width: 0;
    overflow-x: auto; scrollbar-width: none;
  }
  .tabs-wrap::-webkit-scrollbar { display: none; }
  .tab {
    display: flex; align-items: center; gap: 7px;
    max-width: 210px; min-width: 100px;
    padding: 6px 9px; border-radius: 8px 8px 0 0;
    background: var(--surface); border: 1px solid transparent; border-bottom: none;
    color: var(--muted); font-size: 12px; cursor: pointer; user-select: none; flex-shrink: 0;
  }
  .tab:hover { background: var(--surface2); color: var(--text); }
  .tab.active {
    background: var(--surface2); color: var(--text);
    border-color: var(--border); box-shadow: inset 0 2px 0 var(--accent);
  }
  .tab-title { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tab-close {
    width: 16px; height: 16px; border-radius: 4px; border: 0;
    background: transparent; color: var(--muted); font-size: 13px; line-height: 1;
    display: flex; align-items: center; justify-content: center; cursor: pointer;
  }
  .tab-close:hover { background: rgba(239,68,68,.25); color: #fca5a5; }
  .new-tab-btn {
    width: 26px; height: 26px; margin-bottom: 4px; border-radius: 6px;
    border: 1px solid var(--border); background: var(--surface);
    color: var(--text); font-size: 16px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  .new-tab-btn:hover { border-color: var(--accent); color: var(--accent); }
  .stream-pills { display: flex; align-items: center; gap: 6px; padding-bottom: 4px; flex-shrink: 0; }
  .pill {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px; padding: 3px 8px; border-radius: 999px;
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    white-space: nowrap;
  }
  .pill.fps { color: var(--accent); border-color: rgba(0,229,153,.35); }
  .pill.hw { color: #86efac; border-color: rgba(34,197,94,.4); }
  .pill.gpu-max { color: #fde047; border-color: rgba(250,204,21,.45); cursor: pointer; }
  .pill.gpu-auto { color: var(--accent2); border-color: rgba(56,189,248,.4); cursor: pointer; }

  .toolbar {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 10px; background: var(--surface2);
    border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .nav-btn {
    height: 30px; min-width: 30px; padding: 0 8px;
    border-radius: 6px; border: 1px solid var(--border);
    background: var(--surface); color: var(--text); font-size: 13px; cursor: pointer;
  }
  .nav-btn:hover { background: var(--surface3); }
  .omnibox {
    flex: 1; display: flex; align-items: center; gap: 6px;
    background: #080c12; border: 1px solid var(--border);
    border-radius: 7px; padding: 0 8px; height: 30px; min-width: 0;
  }
  .omnibox:focus-within { border-color: var(--accent); }
  .omnibox input {
    flex: 1; background: transparent; border: 0; outline: none;
    color: var(--text); font-size: 12.5px; min-width: 0;
  }
  .go-btn {
    height: 22px; padding: 0 10px; border-radius: 5px; border: 0;
    background: var(--accent); color: #052014; font-weight: 700; font-size: 11.5px; cursor: pointer;
  }
  .ctrl-select {
    height: 30px; padding: 0 7px; border-radius: 6px;
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); font-size: 11.5px; cursor: pointer;
  }

  .bookmarks {
    display: flex; align-items: center; gap: 6px; padding: 4px 10px;
    background: var(--surface); border-bottom: 1px solid var(--border);
    overflow-x: auto; scrollbar-width: none; flex-shrink: 0;
  }
  .bm {
    font-size: 11px; padding: 2px 8px; border-radius: 5px;
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--muted); cursor: pointer; white-space: nowrap;
  }
  .bm:hover { color: var(--text); border-color: var(--accent2); }

  .stage {
    flex: 1 1 0; min-height: 0; width: 100%; overflow: hidden;
    display: flex; align-items: center; justify-content: center;
    background: radial-gradient(circle at center, #0e1621 0%, #05070a 100%);
    padding: 6px; position: relative;
  }
  .img-wrap {
    position: relative; max-width: 100%; max-height: 100%;
    display: flex; align-items: center; justify-content: center;
  }
  #scr {
    max-width: 100%; max-height: calc(100vh - 205px);
    width: auto; height: auto; aspect-ratio: 16 / 9;
    object-fit: contain; display: block;
    background: #000; border: 1px solid var(--border); border-radius: 8px;
    box-shadow: 0 10px 30px rgba(0,0,0,.65);
    cursor: crosshair; user-select: none; outline: none;
  }
  .hud-overlay {
    position: absolute; top: 8px; right: 8px;
    background: rgba(8, 11, 16, 0.8); backdrop-filter: blur(4px);
    border: 1px solid rgba(255,255,255,.12); border-radius: 6px;
    padding: 3px 8px; font-family: ui-monospace, monospace; font-size: 11px;
    color: var(--accent); pointer-events: none;
  }

  .telemetry {
    background: #070a0f; border-top: 1px solid var(--border);
    padding: 7px 10px;
    display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 7px;
    flex-shrink: 0;
  }
  @media (max-width: 1050px) {
    .telemetry { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    #scr { max-height: calc(100vh - 280px); }
  }
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 7px;
    padding: 6px 9px; display: flex; flex-direction: column; gap: 3px; min-width: 0;
  }
  .card-top {
    display: flex; justify-content: space-between; align-items: center;
    font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; color: var(--muted);
  }
  .card-val {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 12.5px; font-weight: 700; color: var(--text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .card-sub {
    font-family: ui-monospace, monospace; font-size: 10px; color: var(--muted);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .bar { height: 4px; border-radius: 3px; background: #1a2432; overflow: hidden; }
  .bar > i { display: block; height: 100%; width: 0%; background: var(--accent); transition: width .3s; }
  .bar.gpu > i { background: var(--accent2); }
  .bar.ram > i { background: #eab308; }
  .bar.bat > i { background: #22c55e; }
</style>
</head>
<body>
<div class="app">
  <div class="tabbar">
    <div class="brand"><span class="brand-dot"></span>AGATE · MALI-G77</div>
    <div class="tabs-wrap" id="tabs"></div>
    <button class="new-tab-btn" onclick="newTab()" title="Yeni Sekme">+</button>
    <div class="stream-pills">
      <span class="pill hw" id="pill-eng">ENC: HW /dev/video3</span>
      <span class="pill fps" id="pill-fps">FPS: --</span>
      <span class="pill" id="pill-bw">-- KB/s</span>
      <span class="pill gpu-auto" id="pill-perf" onclick="toggleGpuPerf()" title="GPU/CPU Max Performans Modunu Aç/Kapat">GPU: --</span>
    </div>
  </div>

  <div class="toolbar">
    <button class="nav-btn" onclick="sendCtrl({type:'back'})" title="Geri">←</button>
    <button class="nav-btn" onclick="sendCtrl({type:'forward'})" title="İleri">→</button>
    <button class="nav-btn" onclick="sendCtrl({type:'reload'})" title="Yenile">↻</button>
    <div class="omnibox">
      <input id="url" placeholder="URL veya Google araması yaz..." onkeydown="if(event.key==='Enter')nav()">
      <button class="go-btn" onclick="nav()">Git</button>
    </div>
    <select class="ctrl-select" id="sel-mode" onchange="applyStreamCfg()" title="Encode Motoru & Kalite">
      <option value="hwjpeg:1920x1080:jpeg:90" selected>HW-JPEG 1080p (/dev/video3 · Donanım)</option>
      <option value="cdp:1920x1080:png:100">Native 1080p (CPU Kayıpsız PNG)</option>
      <option value="cdp:2560x1440:jpeg:95">2K QHD 1440p (CPU CDP)</option>
      <option value="cdp:3840x2160:png:100">4K UHD 2160p (CPU Kayıpsız PNG)</option>
    </select>
    <button class="nav-btn" onclick="pasteClip()" title="Panoyu Yapıştır">📋</button>
    <button class="nav-btn" onclick="toggleFs()" title="Tam Ekran">⛶</button>
    <button class="nav-btn" onclick="location.href=location.protocol+'//'+location.hostname+':8090/'" title="Telefon XFCE Masaüstüne Geç" style="border-color:rgba(0,229,153,.4);color:#00e599">🖥️ XFCE</button>
  </div>

  <div class="bookmarks">
    <span style="font-size:11px;color:var(--muted);margin-right:2px">Hızlı Testler:</span>
    <span class="bm" onclick="openUrl('https://webglsamples.org/aquarium/aquarium.html')">🐠 WebGL Aquarium</span>
    <span class="bm" onclick="openUrl('https://webglreport.com/?v=2')">📊 WebGL 2.0 Report</span>
    <span class="bm" onclick="openUrl('https://www.shadertoy.com/results?query=raymarching')">✨ Shadertoy Raymarch</span>
    <span class="bm" onclick="openUrl('https://threejs.org/examples/#webgl_instancing_performance')">🔺 Three.js Instancing</span>
    <span class="bm" onclick="openUrl('https://web.basemark.com/')">🏁 Basemark Web 3.0</span>
    <span class="bm" onclick="openUrl('https://www.google.com/')">🔍 Google</span>
    <span class="bm" onclick="openUrl('https://www.youtube.com/')">▶ YouTube</span>
  </div>

  <div class="stage" id="stage">
    <div class="img-wrap">
      <img id="scr" src="/frame.jpg" tabindex="0" alt="Chromium Live Stream">
      <div class="hud-overlay" id="hud-overlay">1920×1080 HW-JPEG · Bağlanıyor...</div>
    </div>
  </div>

  <div class="telemetry">
    <div class="card">
      <div class="card-top"><span>CPU (MT6893)</span><span id="t-gov">-</span></div>
      <div class="card-val" id="t-cpu">--%</div>
      <div class="bar"><i id="b-cpu"></i></div>
      <div class="card-sub" id="t-freqs">L:- / M:- / P:- MHz</div>
    </div>
    <div class="card">
      <div class="card-top"><span>GPU (Mali-G77)</span><span id="t-gpupwr">-</span></div>
      <div class="card-val" id="t-gpu">--% · -- MHz</div>
      <div class="bar gpu"><i id="b-gpu"></i></div>
      <div class="card-sub" id="t-vram">VRAM: -- MB · -- ctx</div>
    </div>
    <div class="card">
      <div class="card-top"><span>RAM & SWAP</span><span id="t-up">UP -</span></div>
      <div class="card-val" id="t-ram">-- / -- MB</div>
      <div class="bar ram"><i id="b-ram"></i></div>
      <div class="card-sub" id="t-swap">Swap: -- / -- MB</div>
    </div>
    <div class="card">
      <div class="card-top"><span>SICAKLIKLAR</span><span id="t-tempmax">-</span></div>
      <div class="card-val" id="t-tcpu">CPU --°C · AP --°C</div>
      <div class="card-sub" id="t-tsub">PMIC --°C · WiFi --°C · Bat --°C</div>
    </div>
    <div class="card">
      <div class="card-top"><span>BATARYA & GÜÇ</span><span id="t-susp">Limit: 70%</span></div>
      <div class="card-val" id="t-bat">--% · --</div>
      <div class="bar bat"><i id="b-bat"></i></div>
      <div class="card-sub" id="t-pwr">-- W · -- mA · -- V</div>
    </div>
    <div class="card">
      <div class="card-top"><span>AKIŞ & ENCODE</span><span id="t-tabcnt">0 sekme</span></div>
      <div class="card-val" id="t-stream">-- FPS · -- KB/s</div>
      <div class="card-sub" id="t-res">HW-JPEG /dev/video3 · 1080p</div>
    </div>
  </div>
</div>

<script>
const scr = document.getElementById('scr');
const urlInput = document.getElementById('url');
let currentUrlFocused = false;
let gpuMaxMode = false;
let framesThisSec = 0;
let bytesThisSec = 0;
let lastBlobUrl = null;
let lastMoveTs = 0;
let curW = 1920;
let curH = 1080;
let curModeLabel = 'HW-JPEG /dev/video3';

urlInput.addEventListener('focus', () => currentUrlFocused = true);
urlInput.addEventListener('blur', () => currentUrlFocused = false);

function connectStreamWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/stream`);
  ws.binaryType = 'blob';
  ws.onmessage = (ev) => {
    framesThisSec++;
    bytesThisSec += ev.data.size;
    const url = URL.createObjectURL(ev.data);
    scr.src = url;
    if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
    lastBlobUrl = url;
  };
  ws.onclose = () => setTimeout(connectStreamWS, 700);
}
connectStreamWS();

setInterval(() => {
  const fps = framesThisSec;
  const kbps = Math.round(bytesThisSec / 1024);
  framesThisSec = 0;
  bytesThisSec = 0;
  document.getElementById('pill-fps').textContent = `FPS: ${fps}`;
  document.getElementById('pill-bw').textContent = `${kbps} KB/s`;
  document.getElementById('t-stream').textContent = `${fps} FPS · ${kbps} KB/s`;
  document.getElementById('hud-overlay').textContent = `${curW}×${curH} (${curModeLabel}) · ${fps} FPS · ${kbps} KB/s`;
}, 1000);

async function sendCtrl(payload) {
  const r = await fetch('/input', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  return r.json().catch(() => ({}));
}

function openUrl(u) {
  urlInput.value = u;
  sendCtrl({type: 'navigate', url: u});
}
function nav() {
  let u = urlInput.value.trim();
  if (!u) return;
  if (!/^https?:\/\//i.test(u) && !u.includes('.')) {
    u = 'https://www.google.com/search?q=' + encodeURIComponent(u);
  }
  openUrl(u);
  scr.focus();
}

async function refreshTabs() {
  try {
    const r = await fetch('/api/tabs');
    const data = await r.json();
    const wrap = document.getElementById('tabs');
    wrap.innerHTML = '';
    document.getElementById('t-tabcnt').textContent = `${data.tabs.length} sekme`;
    for (const t of data.tabs) {
      const div = document.createElement('div');
      div.className = 'tab' + (t.active ? ' active' : '');
      div.onclick = async (e) => {
        if (e.target.classList.contains('tab-close')) return;
        await fetch('/api/tabs/activate', {
          method: 'POST', headers: {'Content-Type':'application/json'},
          body: JSON.stringify({id: t.id})
        });
        refreshTabs();
      };
      const sp = document.createElement('span');
      sp.className = 'tab-title';
      sp.textContent = t.title || t.url || 'Yeni Sekme';
      sp.title = t.url;
      div.appendChild(sp);

      if (data.tabs.length > 1) {
        const cb = document.createElement('button');
        cb.className = 'tab-close';
        cb.textContent = '×';
        cb.onclick = async (e) => {
          e.stopPropagation();
          await fetch('/api/tabs/close', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({id: t.id})
          });
          refreshTabs();
        };
        div.appendChild(cb);
      }
      wrap.appendChild(div);
      if (t.active && !currentUrlFocused) {
        urlInput.value = t.url || '';
      }
    }
  } catch (e) {}
}
async function newTab() {
  await fetch('/api/tabs/new', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({url: 'https://www.google.com/'})
  });
  refreshTabs();
}
setInterval(refreshTabs, 1500);
refreshTabs();

async function refreshTelemetry() {
  try {
    const r = await fetch('/api/telemetry');
    const t = await r.json();
    document.getElementById('t-cpu').textContent = `${t.cpu_pct.toFixed(1)}%`;
    document.getElementById('b-cpu').style.width = `${Math.min(100, t.cpu_pct)}%`;
    document.getElementById('t-freqs').textContent = `L:${t.cpu_freqs[0]} / M:${t.cpu_freqs[1]} / P:${t.cpu_freqs[2]} MHz`;
    document.getElementById('t-gov').textContent = t.cpu_gov;

    document.getElementById('t-gpu').textContent = `${t.gpu_pct}% · ${t.gpu_mhz} MHz`;
    document.getElementById('b-gpu').style.width = `${Math.min(100, t.gpu_pct)}%`;
    document.getElementById('t-gpupwr').textContent = t.gpu_pwr;
    document.getElementById('t-vram').textContent = `VRAM: ${t.gpu_vram_mb} MB · ${t.gpu_ctx} ctx`;

    gpuMaxMode = !!t.gpu_max_mode;
    const pp = document.getElementById('pill-perf');
    pp.textContent = gpuMaxMode ? `GPU: MAX ${t.gpu_mhz}MHz` : `GPU: AUTO`;
    pp.className = 'pill ' + (gpuMaxMode ? 'gpu-max' : 'gpu-auto');

    document.getElementById('t-ram').textContent = `${t.mem_used_mb} / ${t.mem_tot_mb} MB (${t.mem_pct}%)`;
    document.getElementById('b-ram').style.width = `${Math.min(100, t.mem_pct)}%`;
    document.getElementById('t-swap').textContent = `Swap: ${t.swap_used_mb} / ${t.swap_tot_mb} MB`;
    document.getElementById('t-up').textContent = `UP ${t.uptime}`;

    const tmax = Math.max(t.temps.cpu, t.temps.ap);
    const tEl = document.getElementById('t-tempmax');
    tEl.textContent = tmax >= 75 ? 'SICAK' : 'NORMAL';
    tEl.style.color = tmax >= 75 ? 'var(--danger)' : 'var(--accent)';
    document.getElementById('t-tcpu').textContent = `CPU ${t.temps.cpu}°C · AP ${t.temps.ap}°C`;
    document.getElementById('t-tsub').textContent = `PMIC ${t.temps.pmic}°C · WiFi ${t.temps.wifi}°C · Bat ${t.temps.bat}°C`;

    document.getElementById('t-bat').textContent = `${t.bat_pct}% · ${t.bat_status}`;
    document.getElementById('b-bat').style.width = `${Math.min(100, t.bat_pct)}%`;
    document.getElementById('t-susp').textContent = t.input_suspend ? 'Şarj Kesildi (70%)' : 'Şarj Açık';
    document.getElementById('t-pwr').textContent = `${t.watts} W · ${t.ma} mA · ${t.volts} V`;

    curW = t.stream_cfg.maxWidth;
    curH = t.stream_cfg.maxHeight;
    const engEl = document.getElementById('pill-eng');
    if (t.stream_cfg.engine === 'hwjpeg') {
      curModeLabel = 'HW-JPEG /dev/video3';
      engEl.textContent = 'ENC: HW /dev/video3';
      engEl.style.color = '#86efac';
      engEl.style.borderColor = 'rgba(34,197,94,.45)';
    } else {
      curModeLabel = t.stream_cfg.format === 'png' ? 'CPU NATIVE PNG' : 'CPU CDP JPEG';
      engEl.textContent = `ENC: ${curModeLabel}`;
      engEl.style.color = '#fbbf24';
      engEl.style.borderColor = 'rgba(245,158,11,.5)';
    }
    document.getElementById('t-res').textContent = `${curW}×${curH} · ${curModeLabel}`;
    const mSel = document.getElementById('sel-mode');
    if (document.activeElement !== mSel) {
      const key = `${t.stream_cfg.engine}:${curW}x${curH}:${t.stream_cfg.format}:${t.stream_cfg.quality}`;
      for (const opt of mSel.options) {
        if (opt.value === key) { mSel.value = key; break; }
      }
    }
  } catch (e) {}
}
setInterval(refreshTelemetry, 1200);
refreshTelemetry();

async function toggleGpuPerf() {
  const mode = gpuMaxMode ? 'auto' : 'max';
  await fetch('/api/gpu_perf', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({mode})
  });
  refreshTelemetry();
}

async function applyStreamCfg() {
  const [engine, wh, fmt, qStr] = document.getElementById('sel-mode').value.split(':');
  const [wStr, hStr] = wh.split('x');
  curW = parseInt(wStr, 10);
  curH = parseInt(hStr, 10);
  await fetch('/api/stream_cfg', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      engine, maxWidth: curW, maxHeight: curH, format: fmt, quality: parseInt(qStr, 10), everyNthFrame: 1
    })
  });
  refreshTelemetry();
}

async function pasteClip() {
  try {
    const txt = await navigator.clipboard.readText();
    if (txt) sendCtrl({type: 'char', text: txt});
  } catch (e) {
    const txt = prompt('Yapıştırılacak metin:');
    if (txt) sendCtrl({type: 'char', text: txt});
  }
}

function toggleFs() {
  const el = document.getElementById('stage');
  if (!document.fullscreenElement) el.requestFullscreen();
  else document.exitFullscreen();
}

function coords(e) {
  const r = scr.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(curW - 1, Math.round((e.clientX - r.left) * curW / r.width))),
    y: Math.max(0, Math.min(curH - 1, Math.round((e.clientY - r.top) * curH / r.height)))
  };
}
scr.addEventListener('contextmenu', e => e.preventDefault());
scr.addEventListener('mousedown', e => {
  scr.focus();
  const btn = e.button === 2 ? 'right' : (e.button === 1 ? 'middle' : 'left');
  sendCtrl({type: 'mouse', action: 'mousePressed', button: btn, ...coords(e)});
});
scr.addEventListener('mouseup', e => {
  const btn = e.button === 2 ? 'right' : (e.button === 1 ? 'middle' : 'left');
  sendCtrl({type: 'mouse', action: 'mouseReleased', button: btn, ...coords(e)});
});
scr.addEventListener('mousemove', e => {
  const now = performance.now();
  if (now - lastMoveTs < 45) return;
  lastMoveTs = now;
  sendCtrl({type: 'mouse', action: 'mouseMoved', button: 'none', ...coords(e)});
});
scr.addEventListener('wheel', e => {
  e.preventDefault();
  sendCtrl({type: 'wheel', deltaX: e.deltaX, deltaY: e.deltaY, ...coords(e)});
}, {passive: false});
scr.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey) return;
  e.preventDefault();
  if (e.key.length === 1) sendCtrl({type: 'char', text: e.key});
  else sendCtrl({type: 'key', key: e.key});
});
</script>
</body>
</html>
"""


async def index(request):
    return web.Response(text=HTML, content_type="text/html")


async def ws_stream(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)
    if latest_frame:
        try:
            await ws.send_bytes(latest_frame)
        except Exception:
            pass
    try:
        async for _ in ws:
            pass
    finally:
        ws_clients.discard(ws)
    return ws


async def frame_jpg(request):
    if not latest_frame:
        return web.Response(status=503, text="Waiting for first frame")
    ct = "image/png" if latest_frame.startswith(b"\x89PNG") else "image/jpeg"
    return web.Response(body=latest_frame, content_type=ct)


async def stream_mjpg(request):
    resp = web.StreamResponse(status=200, headers={
        "Content-Type": "multipart/x-mixed-replace; boundary=frame",
        "Cache-Control": "no-cache",
    })
    await resp.prepare(request)
    try:
        while True:
            if latest_frame:
                part = (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(latest_frame)).encode()
                    + b"\r\n\r\n"
                    + latest_frame
                    + b"\r\n"
                )
                await resp.write(part)
            try:
                await asyncio.wait_for(frame_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
    except Exception:
        pass
    return resp


async def api_tabs(request):
    pages = await fetch_pages()
    out = []
    for p in pages:
        out.append({
            "id": p["id"],
            "title": p.get("title", ""),
            "url": p.get("url", ""),
            "active": p["id"] == active_target_id,
        })
    return web.json_response({"tabs": out, "active_id": active_target_id})


async def api_tabs_new(request):
    body = await request.json() if request.can_read_body else {}
    u = body.get("url", "https://www.google.com/")
    async with active_sess.put(f"http://127.0.0.1:{CDP_PORT}/json/new?{quote(u, safe=':/?&=')}") as r:
        data = await r.json()
    await attach_to_tab(data["id"])
    return web.json_response({"ok": True, "id": data["id"]})


async def api_tabs_activate(request):
    body = await request.json()
    ok = await attach_to_tab(body.get("id"))
    return web.json_response({"ok": ok})


async def api_tabs_close(request):
    body = await request.json()
    tid = body.get("id")
    pages = await fetch_pages()
    if len(pages) <= 1:
        return web.json_response({"ok": False, "reason": "last_tab"})
    async with active_sess.get(f"http://127.0.0.1:{CDP_PORT}/json/close/{tid}") as _:
        pass
    await asyncio.sleep(0.2)
    if tid == active_target_id:
        await attach_to_tab()
    return web.json_response({"ok": True})


async def api_telemetry(request):
    return web.json_response(collect_telemetry())


async def api_gpu_perf(request):
    body = await request.json()
    mode = "max" if body.get("mode") == "max" else "auto"
    subprocess.run(["/usr/local/bin/gpu-perf", mode], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return web.json_response({"ok": True, "mode": mode})


async def api_stream_cfg(request):
    body = await request.json()
    if body.get("engine") in ("hwjpeg", "cdp"):
        stream_cfg["engine"] = body["engine"]
    if body.get("format") in ("jpeg", "png"):
        stream_cfg["format"] = body["format"]
    if "quality" in body:
        stream_cfg["quality"] = max(20, min(100, int(body["quality"])))
    if "everyNthFrame" in body:
        stream_cfg["everyNthFrame"] = max(1, min(10, int(body["everyNthFrame"])))
    if "maxWidth" in body and "maxHeight" in body:
        stream_cfg["maxWidth"] = max(640, min(3840, int(body["maxWidth"])))
        stream_cfg["maxHeight"] = max(480, min(2160, int(body["maxHeight"])))
    await apply_tab_stream_mode()
    return web.json_response({"ok": True, "stream_cfg": stream_cfg})


async def handle_input(request):
    body = await request.json()
    t = body.get("type")
    if t == "navigate":
        u = body["url"].strip()
        if not u.startswith("http"):
            u = "https://" + u
        await cdp_send("Page.navigate", {"url": u})
    elif t == "reload":
        await cdp_send("Page.reload")
    elif t == "back":
        await cdp_send("Runtime.evaluate", {"expression": "history.back()"})
    elif t == "forward":
        await cdp_send("Runtime.evaluate", {"expression": "history.forward()"})
    elif t == "mouse":
        btn = body.get("button", "left")
        act = body["action"]
        params = {"type": act, "x": body["x"], "y": body["y"]}
        if act != "mouseMoved":
            params["button"] = btn
            params["clickCount"] = 1
        await cdp_send("Input.dispatchMouseEvent", params)
    elif t == "wheel":
        await cdp_send("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": body["x"], "y": body["y"],
            "deltaX": body["deltaX"], "deltaY": body["deltaY"]
        })
    elif t == "char":
        await cdp_send("Input.insertText", {"text": body["text"]})
    elif t == "key":
        km = {
            "Enter": 13, "Backspace": 8, "Tab": 9, "Escape": 27,
            "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40,
            "Delete": 46, "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
        }
        kc = km.get(body["key"], 0)
        await cdp_send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": body["key"], "windowsVirtualKeyCode": kc})
        await cdp_send("Input.dispatchKeyEvent", {"type": "keyUp", "key": body["key"], "windowsVirtualKeyCode": kc})
    return web.json_response({"ok": True})


async def main():
    asyncio.create_task(cdp_supervisor())
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws/stream", ws_stream)
    app.router.add_get("/frame.jpg", frame_jpg)
    app.router.add_get("/stream.mjpg", stream_mjpg)
    app.router.add_get("/api/tabs", api_tabs)
    app.router.add_post("/api/tabs/new", api_tabs_new)
    app.router.add_post("/api/tabs/activate", api_tabs_activate)
    app.router.add_post("/api/tabs/close", api_tabs_close)
    app.router.add_get("/api/telemetry", api_telemetry)
    app.router.add_post("/api/gpu_perf", api_gpu_perf)
    app.router.add_post("/api/stream_cfg", api_stream_cfg)
    app.router.add_post("/input", handle_input)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

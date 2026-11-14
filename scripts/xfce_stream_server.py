#!/usr/bin/env python3
import asyncio
import ctypes
import glob
import json
import os
import re
import struct
import subprocess
import time
import aiohttp
from aiohttp import web

HTTP_PORT = 8090
XFCE_SOCK = "/tmp/xfce_hwjpeg.sock"
XFCE_SHM_JPG = "/dev/shm/xfce_hw.jpg"
XWD_PATH = "/dev/shm/xfb/Xvfb_screen0"

latest_frame = None
frame_event = asyncio.Event()
ws_clients = set()
_prev_cpu = None
_cached_cpu_pct = 0.0

# --- X11 + XTest ctypes controller for DISPLAY=:0 ---
_x11 = ctypes.CDLL("libX11.so.6")
_xtst = ctypes.CDLL("libXtst.so.6")
_x11.XOpenDisplay.restype = ctypes.c_void_p
_x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
_x11.XFlush.argtypes = [ctypes.c_void_p]
_x11.XKeysymToKeycode.restype = ctypes.c_uint
_x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
_x11.XStringToKeysym.restype = ctypes.c_ulong
_x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
_xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
_xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
_xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]

_dpy = None


def get_dpy():
    global _dpy
    if not _dpy:
        _dpy = _x11.XOpenDisplay(b":0")
    return _dpy


def get_screen_dims():
    try:
        with open(XWD_PATH, "rb") as f:
            hdr = f.read(24)
            w, h = struct.unpack(">II", hdr[16:24])
            if 200 <= w <= 4096 and 200 <= h <= 4096:
                return w, h
    except Exception:
        pass
    return 2400, 1080


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
    w, h = get_screen_dims()
    cpu_pct = sample_cpu_pct()
    mem_tot = mem_avail = 0
    for l in _rfile("/proc/meminfo").splitlines():
        if l.startswith("MemTotal:"):
            mem_tot = int(l.split()[1]) // 1024
        elif l.startswith("MemAvailable:"):
            mem_avail = int(l.split()[1]) // 1024
    mem_used = max(0, mem_tot - mem_avail)

    tcpu = tbat = 0.0
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        tn = _rfile(os.path.join(z, "type"))
        tv = _rfile(os.path.join(z, "temp"))
        if tn == "mtktscpu" and tv:
            tcpu = round(int(tv) / 1000.0, 1)
        elif tn == "battery" and tv:
            tbat = round(int(tv) / 1000.0, 1)

    cap = _rfile("/sys/class/power_supply/battery/capacity", "0")
    stat = _rfile("/sys/class/power_supply/battery/status", "?")
    bri = _rfile("/sys/class/leds/lcd-backlight/brightness", "0")
    return {
        "width": w,
        "height": h,
        "cpu_pct": cpu_pct,
        "mem_used_mb": mem_used,
        "mem_tot_mb": mem_tot,
        "tcpu": tcpu,
        "tbat": tbat,
        "bat_pct": int(cap) if cap.isdigit() else 0,
        "bat_status": stat,
        "screen_on": int(bri) > 0 if bri.isdigit() else False,
    }


async def _send_ws(ws, data):
    try:
        await asyncio.wait_for(ws.send_bytes(data), timeout=0.35)
    except Exception:
        ws_clients.discard(ws)


def publish_frame(jpg):
    global latest_frame
    latest_frame = jpg
    frame_event.set()
    frame_event.clear()
    for ws in list(ws_clients):
        if ws.closed:
            ws_clients.discard(ws)
        else:
            asyncio.create_task(_send_ws(ws, jpg))


async def xfce_socket_reader():
    if os.path.exists(XFCE_SHM_JPG):
        try:
            publish_frame(open(XFCE_SHM_JPG, "rb").read())
        except Exception:
            pass
    while True:
        try:
            if not os.path.exists(XFCE_SOCK):
                await asyncio.sleep(0.4)
                continue
            reader, writer = await asyncio.open_unix_connection(XFCE_SOCK, limit=16 * 1024 * 1024)
            try:
                while True:
                    hdr = await reader.readexactly(4)
                    sz = struct.unpack("<I", hdr)[0]
                    if sz <= 0 or sz > 16 * 1024 * 1024:
                        break
                    jpg = await reader.readexactly(sz)
                    publish_frame(jpg)
            finally:
                writer.close()
        except Exception:
            await asyncio.sleep(0.5)


def send_x_key(key_name, shift=False):
    d = get_dpy()
    if not d:
        return
    ks = _x11.XStringToKeysym(key_name.encode())
    if not ks:
        return
    kc = _x11.XKeysymToKeycode(d, ks)
    if not kc:
        return
    skc = _x11.XKeysymToKeycode(d, 0xFFE1) if shift else 0  # XK_Shift_L
    if skc:
        _xtst.XTestFakeKeyEvent(d, skc, 1, 0)
    _xtst.XTestFakeKeyEvent(d, kc, 1, 0)
    _xtst.XTestFakeKeyEvent(d, kc, 0, 0)
    if skc:
        _xtst.XTestFakeKeyEvent(d, skc, 0, 0)
    _x11.XFlush(d)


CHAR_KEYSYMS = {
    " ": ("space", False), "\n": ("Return", False), ".": ("period", False), ",": ("comma", False),
    "/": ("slash", False), "?": ("question", True), ":": ("colon", True), ";": ("semicolon", False),
    "-": ("minus", False), "_": ("underscore", True), "=": ("equal", False), "+": ("plus", True),
    "!": ("exclam", True), "@": ("at", True), "#": ("numbersign", True), "$": ("dollar", True),
    "%": ("percent", True), "&": ("ampersand", True), "*": ("asterisk", True), "(": ("parenleft", True),
    ")": ("parenright", True), "[": ("bracketleft", False), "]": ("bracketright", False),
    "{": ("braceleft", True), "}": ("braceright", True), "'": ("apostrophe", False), '"': ("quotedbl", True),
    "\\": ("backslash", False), "|": ("bar", True), "<": ("less", True), ">": ("greater", True),
    "~": ("asciitilde", True), "`": ("grave", False),
}

SPECIAL_KEYS = {
    "Enter": "Return", "Backspace": "BackSpace", "Tab": "Tab", "Escape": "Escape",
    "ArrowLeft": "Left", "ArrowUp": "Up", "ArrowRight": "Right", "ArrowDown": "Down",
    "Delete": "Delete", "Home": "Home", "End": "End", "PageUp": "Page_Up", "PageDown": "Page_Down",
}


HTML = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Xiaomi 11T · Canlı XFCE Masaüstü (/dev/video4 HW-JPEG)</title>
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; height: 100%; background: #070a0f; color: #e6eef8;
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    overflow: hidden;
  }
  .app { display: flex; flex-direction: column; height: 100vh; width: 100vw; }
  .bar {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    padding: 7px 12px; background: #0f1722; border-bottom: 1px solid #243245; flex-shrink: 0;
  }
  .title { font-size: 12.5px; font-weight: 700; color: #00e599; letter-spacing: .4px; margin-right: 4px; }
  .pill {
    font-family: ui-monospace, monospace; font-size: 11px;
    padding: 3px 8px; border-radius: 999px; background: #162130; border: 1px solid #28384e;
  }
  .pill.hw { color: #86efac; border-color: rgba(34,197,94,.45); }
  .pill.fps { color: #38bdf8; border-color: rgba(56,189,248,.4); }
  .btn {
    height: 28px; padding: 0 10px; border-radius: 6px; border: 1px solid #2c3f57;
    background: #182334; color: #e6eef8; font-size: 11.5px; cursor: pointer;
  }
  .btn:hover { background: #223149; border-color: #38bdf8; }
  .btn.accent { background: #00e599; color: #042115; border-color: #00e599; font-weight: 700; }
  .spacer { flex: 1; }
  .stage {
    flex: 1 1 0; min-height: 0; display: flex; align-items: center; justify-content: center;
    background: #040608; padding: 6px; overflow: hidden;
  }
  #scr {
    max-width: 100%; max-height: calc(100vh - 54px);
    width: auto; height: auto; object-fit: contain;
    border: 1px solid #253447; border-radius: 8px; background: #000;
    cursor: crosshair; outline: none; user-select: none;
  }
</style>
</head>
<body>
<div class="app">
  <div class="bar">
    <span class="title">AGATE · CANLI TELEFON EKRANI (XFCE4)</span>
    <span class="pill hw">ENC: HW /dev/video4</span>
    <span class="pill fps" id="p-fps">FPS: --</span>
    <span class="pill" id="p-bw">-- KB/s</span>
    <span class="pill" id="p-tel">CPU --% · RAM --MB · --°C · Bat --%</span>
    <div class="spacer"></div>
    <button class="btn" onclick="openChr()">🌐 Chromium Aç</button>
    <button class="btn" onclick="toggleScr()">💡 Ekran Işığı</button>
    <button class="btn" onclick="rotateMode('yatay')">📱↔ Yatay</button>
    <button class="btn" onclick="rotateMode('dikey')">📱↕ Dikey</button>
    <button class="btn" onclick="pasteText()">📋 Yapıştır</button>
    <button class="btn" onclick="toggleFs()">⛶ Tam Ekran</button>
    <button class="btn accent" onclick="location.href=location.protocol+'//'+location.hostname+':8080/'">GPU Konsol (:8080)</button>
  </div>
  <div class="stage" id="stage">
    <img id="scr" src="/frame.jpg" tabindex="0" alt="XFCE Live">
  </div>
</div>
<script>
const scr = document.getElementById('scr');
let curW = 2400, curH = 1080, fps = 0, bytes = 0, lastBlob = null, lastMove = 0;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${proto}//${location.host}/ws/stream`);
  ws.binaryType = 'blob';
  ws.onmessage = (ev) => {
    fps++; bytes += ev.data.size;
    const u = URL.createObjectURL(ev.data);
    scr.src = u;
    if (lastBlob) URL.revokeObjectURL(lastBlob);
    lastBlob = u;
  };
  ws.onclose = () => setTimeout(connectWS, 700);
}
connectWS();

setInterval(() => {
  document.getElementById('p-fps').textContent = `FPS: ${fps}`;
  document.getElementById('p-bw').textContent = `${Math.round(bytes/1024)} KB/s`;
  fps = 0; bytes = 0;
}, 1000);

async function refreshTel() {
  try {
    const t = await (await fetch('/api/telemetry')).json();
    curW = t.width; curH = t.height;
    document.getElementById('p-tel').textContent =
      `${curW}×${curH} · CPU ${t.cpu_pct}% · RAM ${t.mem_used_mb}MB · ${t.tcpu}°C · Bat ${t.bat_pct}% · Ekran:${t.screen_on?'AÇIK':'KAPALI'}`;
  } catch (e) {}
}
setInterval(refreshTel, 1500);
refreshTel();

async function sendIn(p) {
  await fetch('/input', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(p)});
}
async function openChr() { await fetch('/api/open_chromium', {method:'POST'}); }
async function toggleScr() { await fetch('/api/screen_toggle', {method:'POST'}); refreshTel(); }
async function rotateMode(m) { await fetch('/api/rotate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode:m})}); }
async function pasteText() {
  const txt = prompt('Telefona yazılacak metin:');
  if (txt) sendIn({type:'text', text:txt});
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
  const b = e.button === 2 ? 3 : (e.button === 1 ? 2 : 1);
  sendIn({type:'mouse', action:'down', button:b, ...coords(e)});
});
scr.addEventListener('mouseup', e => {
  const b = e.button === 2 ? 3 : (e.button === 1 ? 2 : 1);
  sendIn({type:'mouse', action:'up', button:b, ...coords(e)});
});
scr.addEventListener('mousemove', e => {
  const now = performance.now();
  if (now - lastMove < 40) return;
  lastMove = now;
  sendIn({type:'mouse', action:'move', ...coords(e)});
});
scr.addEventListener('wheel', e => {
  e.preventDefault();
  const btn = e.deltaY < 0 ? 4 : 5;
  sendIn({type:'wheel', button:btn, ...coords(e)});
}, {passive:false});
scr.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey) return;
  e.preventDefault();
  if (e.key.length === 1) sendIn({type:'char', ch:e.key});
  else sendIn({type:'key', key:e.key});
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
    if not latest_frame and os.path.exists(XFCE_SHM_JPG):
        return web.Response(body=open(XFCE_SHM_JPG, "rb").read(), content_type="image/jpeg")
    if not latest_frame:
        return web.Response(status=503, text="Waiting for XFCE frame")
    return web.Response(body=latest_frame, content_type="image/jpeg")


async def api_telemetry(request):
    return web.json_response(collect_telemetry())


async def api_screen_toggle(request):
    try:
        with open("/run/fbui.ctl", "w") as f:
            f.write("toggle\n")
    except Exception:
        pass
    await asyncio.sleep(0.1)
    return web.json_response({"ok": True})


async def api_open_chromium(request):
    subprocess.Popen([
        "su", "-", "ubuntu", "-c",
        "DISPLAY=:0 nohup /usr/bin/chromium --no-sandbox --test-type --disable-dev-shm-usage "
        "--user-data-dir=/home/ubuntu/.config/chr_xfce https://www.google.com/ >/tmp/chr_xfce.log 2>&1 &"
    ])
    return web.json_response({"ok": True})


async def api_rotate(request):
    body = await request.json()
    mode = "dikey" if body.get("mode") == "dikey" else "yatay"
    subprocess.Popen(["/usr/local/bin/ekran", "xfce", mode])
    return web.json_response({"ok": True, "mode": mode})


async def handle_input(request):
    body = await request.json()
    d = get_dpy()
    if not d:
        return web.json_response({"ok": False})
    t = body.get("type")
    if t == "mouse":
        act = body.get("action")
        _xtst.XTestFakeMotionEvent(d, -1, int(body["x"]), int(body["y"]), 0)
        if act == "down":
            _xtst.XTestFakeButtonEvent(d, int(body["button"]), 1, 0)
        elif act == "up":
            _xtst.XTestFakeButtonEvent(d, int(body["button"]), 0, 0)
        _x11.XFlush(d)
    elif t == "wheel":
        _xtst.XTestFakeMotionEvent(d, -1, int(body["x"]), int(body["y"]), 0)
        b = int(body["button"])
        _xtst.XTestFakeButtonEvent(d, b, 1, 0)
        _xtst.XTestFakeButtonEvent(d, b, 0, 0)
        _x11.XFlush(d)
    elif t == "char":
        ch = body["ch"]
        if ch in CHAR_KEYSYMS:
            ks_name, sh = CHAR_KEYSYMS[ch]
            send_x_key(ks_name, sh)
        elif ch.isalnum():
            send_x_key(ch, ch.isupper())
    elif t == "key":
        k = SPECIAL_KEYS.get(body["key"])
        if k:
            send_x_key(k, False)
    elif t == "text":
        for ch in body.get("text", ""):
            if ch in CHAR_KEYSYMS:
                ks_name, sh = CHAR_KEYSYMS[ch]
                send_x_key(ks_name, sh)
            elif ch.isalnum():
                send_x_key(ch, ch.isupper())
    return web.json_response({"ok": True})


async def main():
    asyncio.create_task(xfce_socket_reader())
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws/stream", ws_stream)
    app.router.add_get("/frame.jpg", frame_jpg)
    app.router.add_get("/api/telemetry", api_telemetry)
    app.router.add_post("/api/screen_toggle", api_screen_toggle)
    app.router.add_post("/api/open_chromium", api_open_chromium)
    app.router.add_post("/api/rotate", api_rotate)
    app.router.add_post("/input", handle_input)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

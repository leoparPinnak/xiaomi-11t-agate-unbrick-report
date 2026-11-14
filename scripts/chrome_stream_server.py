#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import subprocess
import time
import aiohttp
from aiohttp import web

CDP_PORT = 9222
HTTP_PORT = 8080
USER_DIR = "/tmp/chrome_profile"

latest_frame = None
frame_event = asyncio.Event()
cdp_ws = None
cmd_id = 0


async def cdp_call(method, params=None):
    global cmd_id
    if cdp_ws is None or cdp_ws.closed:
        return
    cmd_id += 1
    await cdp_ws.send_json({"id": cmd_id, "method": method, "params": params or {}})


async def cdp_loop():
    global latest_frame, cdp_ws
    os.makedirs(USER_DIR, exist_ok=True)
    proc = subprocess.Popen(
        [
            "/usr/bin/chromium",
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            "--window-size=1280,720",
            f"--user-data-dir={USER_DIR}",
            "https://www.wikipedia.org/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": "disabled:"},
    )
    async with aiohttp.ClientSession() as sess:
        ws_url = None
        for _ in range(40):
            try:
                async with sess.get(f"http://127.0.0.1:{CDP_PORT}/json/list") as r:
                    pages = await r.json()
                    for p in pages:
                        if p.get("type") == "page" and "webSocketDebuggerUrl" in p:
                            ws_url = p["webSocketDebuggerUrl"]
                            break
                if ws_url:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.3)

        if not ws_url:
            raise RuntimeError("Chromium CDP target not found")

        async with sess.ws_connect(ws_url, max_msg_size=16 * 1024 * 1024) as ws:
            cdp_ws = ws
            await cdp_call("Page.enable")
            await cdp_call("Emulation.setDeviceMetricsOverride", {
                "width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False
            })
            await cdp_call("Page.startScreencast", {
                "format": "jpeg", "quality": 75, "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 1
            })
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                if data.get("method") == "Page.screencastFrame":
                    params = data["params"]
                    latest_frame = base64.b64decode(params["data"])
                    frame_event.set()
                    frame_event.clear()
                    await cdp_call("Page.screencastFrameAck", {"sessionId": params["sessionId"]})


HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Xiaomi 11T Chromium Live Stream</title>
<style>
  body { margin:0; background:#111; color:#eee; font-family:system-ui,sans-serif; display:flex; flex-direction:column; align-items:center; }
  .bar { width:100%; max-width:1280px; display:flex; gap:8px; padding:10px; box-sizing:border-box; background:#1b1f22; }
  input { flex:1; padding:8px 12px; border-radius:6px; border:1px solid #3a4248; background:#0d1012; color:#fff; font-size:14px; }
  button { padding:8px 14px; border-radius:6px; border:0; background:#00b86b; color:#000; font-weight:600; cursor:pointer; }
  .view { max-width:1280px; width:100%; border:1px solid #2b3136; background:#000; }
  img { width:100%; display:block; cursor:crosshair; user-select:none; }
</style>
</head>
<body>
  <div class="bar">
    <button onclick="goBack()">Geri</button>
    <input id="url" value="https://www.wikipedia.org/" onkeydown="if(event.key==='Enter')nav()">
    <button onclick="nav()">Git</button>
    <button onclick="reload()">Yenile</button>
  </div>
  <div class="view">
    <img id="scr" src="/stream.mjpg" tabindex="0">
  </div>
<script>
const img = document.getElementById('scr');
function send(payload){ fetch('/input', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); }
function nav(){ send({type:'navigate', url: document.getElementById('url').value}); }
function reload(){ send({type:'reload'}); }
function goBack(){ send({type:'back'}); }
function coords(e){
  const r = img.getBoundingClientRect();
  return { x: Math.round((e.clientX - r.left) * 1280 / r.width), y: Math.round((e.clientY - r.top) * 720 / r.height) };
}
img.addEventListener('mousedown', e => { img.focus(); const c=coords(e); send({type:'mouse', action:'mousePressed', ...c}); });
img.addEventListener('mouseup', e => { const c=coords(e); send({type:'mouse', action:'mouseReleased', ...c}); });
img.addEventListener('wheel', e => { e.preventDefault(); const c=coords(e); send({type:'wheel', deltaX:e.deltaX, deltaY:e.deltaY, ...c}); }, {passive:false});
img.addEventListener('keydown', e => {
  e.preventDefault();
  if(e.key.length === 1) send({type:'char', text:e.key});
  else send({type:'key', key:e.key});
});
</script>
</body>
</html>
"""


async def index(request):
    return web.Response(text=HTML, content_type="text/html")


async def frame_jpg(request):
    if not latest_frame:
        return web.Response(status=503, text="Waiting for first frame")
    return web.Response(body=latest_frame, content_type="image/jpeg")


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


async def handle_input(request):
    body = await request.json()
    t = body.get("type")
    if t == "navigate":
        u = body["url"].strip()
        if not u.startswith("http"):
            u = "https://" + u
        await cdp_call("Page.navigate", {"url": u})
    elif t == "reload":
        await cdp_call("Page.reload")
    elif t == "back":
        await cdp_call("Runtime.evaluate", {"expression": "history.back()"})
    elif t == "mouse":
        await cdp_call("Input.dispatchMouseEvent", {
            "type": body["action"], "x": body["x"], "y": body["y"], "button": "left", "clickCount": 1
        })
    elif t == "wheel":
        await cdp_call("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": body["x"], "y": body["y"], "deltaX": body["deltaX"], "deltaY": body["deltaY"]
        })
    elif t == "char":
        await cdp_call("Input.insertText", {"text": body["text"]})
    elif t == "key":
        km = {"Enter": 13, "Backspace": 8, "Tab": 9, "Escape": 27}
        kc = km.get(body["key"], 0)
        await cdp_call("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": body["key"], "windowsVirtualKeyCode": kc})
        await cdp_call("Input.dispatchKeyEvent", {"type": "keyUp", "key": body["key"], "windowsVirtualKeyCode": kc})
    return web.json_response({"ok": True})


async def main():
    asyncio.create_task(cdp_loop())
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/frame.jpg", frame_jpg)
    app.router.add_get("/stream.mjpg", stream_mjpg)
    app.router.add_post("/input", handle_input)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HTTP_PORT)
    await site.start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())

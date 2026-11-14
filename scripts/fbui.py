#!/usr/bin/env python3
import fcntl
import glob
import os
import pty
import pyte
import re
import select
import struct
import subprocess
import termios
import threading
import time
from PIL import Image, ImageDraw, ImageFont

W, H, STRIDE = 1080, 2400, 4352
BW = STRIDE // 4
COLS, ROWS = 66, 50
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BRIGHT_PATH = "/sys/class/leds/lcd-backlight/brightness"
BLANK_PATH = "/sys/class/graphics/fb0/blank"
CTL_FIFO = "/run/fbui.ctl"
TERM_PIPE = "/run/fbtty.in"
TMUX_SOCK = "/tmp/fbconsole.sock"

screen_on = True
last_toggle = time.time()
dirty = True
lock = threading.Lock()
vt_screen = pyte.Screen(COLS, ROWS)
vt_stream = pyte.Stream(vt_screen)

prev_cpu = None
cpu_pct = 0.0
last_sample = 0.0
cached_info = {}


def set_panel(on: bool):
    global screen_on, dirty
    screen_on = on
    try:
        if on:
            open(BLANK_PATH, "w").write("0")
            open(BRIGHT_PATH, "w").write("900")
            dirty = True
        else:
            open(BRIGHT_PATH, "w").write("0")
            open(BLANK_PATH, "w").write("1")
    except Exception:
        pass


def rfile(p, d=""):
    try:
        return open(p).read().strip()
    except Exception:
        return d


def sample_cpu_pct():
    global prev_cpu, cpu_pct
    line = rfile("/proc/stat").splitlines()[0].split()
    vals = [int(x) for x in line[1:]]
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
    total = sum(vals)
    if prev_cpu is not None:
        dt = total - prev_cpu[0]
        di = idle - prev_cpu[1]
        if dt > 0:
            cpu_pct = max(0.0, min(100.0, 100.0 * (dt - di) / dt))
    prev_cpu = (total, idle)
    return cpu_pct


def read_sys_info():
    global last_sample, cached_info
    now = time.time()
    if cached_info and (now - last_sample) < 1.2:
        return cached_info
    last_sample = now

    cpu = sample_cpu_pct()
    f0 = rfile("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "0")
    f4 = rfile("/sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq", "0")
    f7 = rfile("/sys/devices/system/cpu/cpu7/cpufreq/scaling_cur_freq", "0")
    try:
        freqs = f"{int(f0)//1000}/{int(f4)//1000}/{int(f7)//1000} MHz"
    except Exception:
        freqs = "-"

    # GPU utilization, frequency & VRAM from GED / Mali / gpufreq
    gpu_pct = 0
    gpu_mhz = 0
    gpu_pwr = "IDLE"
    gpu_mb = 0.0
    gpu_ctx = 0
    ged = rfile("/sys/kernel/ged/hal/gpu_utilization", "")
    if ged:
        try:
            gpu_pct = max(gpu_pct, int(ged.split()[0]))
        except Exception:
            pass
    mali = rfile("/proc/mali/utilization", "")
    m_util = re.search(r"gpu/cljs0/cljs1=(\d+)/(\d+)/(\d+)", mali)
    if m_util:
        gpu_pct = max(gpu_pct, int(m_util.group(1)), int(m_util.group(2)), int(m_util.group(3)))
    m_pwr = re.search(r"\):(\d+)", mali)
    if m_pwr and int(m_pwr.group(1)) > 0:
        gpu_pwr = "ON"

    gfreq = rfile("/proc/gpufreq/gpufreq_var_dump", "")
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

    mmem = rfile("/proc/mali/memory_usage", "")
    mm = re.search(r"\((\d+)\s+bytes\)", mmem)
    if mm:
        gpu_mb = int(mm.group(1)) / (1024.0 * 1024.0)
    gpu_ctx = mmem.count("kctx-")
    if gpu_pct > 0:
        gpu_pwr = "ON"
    gpu_desc = f"{gpu_mhz}MHz|{gpu_pwr}|{gpu_mb:.1f}MB|{gpu_ctx}ctx" if gpu_mhz > 0 else f"{gpu_pwr}|{gpu_mb:.1f}MB|{gpu_ctx}ctx"

    # Memory
    mem_tot = mem_avail = 0
    for l in rfile("/proc/meminfo").splitlines():
        if l.startswith("MemTotal:"):
            mem_tot = int(l.split()[1]) // 1024
        elif l.startswith("MemAvailable:"):
            mem_avail = int(l.split()[1]) // 1024
    mem_used = max(0, mem_tot - mem_avail)
    mem_pct = (100.0 * mem_used / mem_tot) if mem_tot else 0.0

    # Temperatures by thermal_zone type
    temps = {}
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        tname = rfile(os.path.join(z, "type"))
        tval = rfile(os.path.join(z, "temp"))
        if tname and tval:
            try:
                c = int(tval) / 1000.0
                if -20.0 < c < 130.0:
                    temps[tname] = c
            except Exception:
                pass
    t_cpu = temps.get("mtktscpu", 0.0)
    t_ap = temps.get("mtktsAP", 0.0)
    t_pmic = temps.get("mtktspmic", 0.0)
    t_wmt = temps.get("mtktswmt", 0.0)
    t_bat = temps.get("battery", 0.0)

    # Power draw & battery
    cap = rfile("/sys/class/power_supply/battery/capacity", "?")
    stat = rfile("/sys/class/power_supply/battery/status", "?")
    susp = rfile("/sys/class/power_supply/battery/input_suspend", "?")
    cur_ua = int(rfile("/sys/class/power_supply/battery/current_now", "0") or 0)
    volt_uv = int(rfile("/sys/class/power_supply/battery/voltage_now", "0") or 0)
    watts = abs(cur_ua * volt_uv) / 1e12
    ma = abs(cur_ua) / 1000.0
    v_str = volt_uv / 1e6

    up = rfile("/proc/uptime", "0").split()[0]
    try:
        secs = int(float(up))
        up_s = f"{secs//3600}h {(secs%3600)//60}m {secs%60}s"
    except Exception:
        up_s = up

    def get_ip(iface):
        try:
            out = subprocess.check_output(["ip", "-4", "-o", "addr", "show", iface], stderr=subprocess.DEVNULL).decode()
            for tok in out.split():
                if "/" in tok and "." in tok:
                    return tok.split("/")[0]
        except Exception:
            pass
        return "yok"

    wifi_ip = get_ip("wlan0")
    usb_ip = get_ip("rndis0")
    if usb_ip == "yok":
        usb_ip = get_ip("usb0")

    cached_info = {
        "up": up_s,
        "cpu_pct": cpu,
        "freqs": freqs,
        "gpu_pct": gpu_pct,
        "gpu_pwr": gpu_pwr,
        "gpu_desc": gpu_desc,
        "mem_used": mem_used,
        "mem_tot": mem_tot,
        "mem_pct": mem_pct,
        "t_cpu": t_cpu,
        "t_ap": t_ap,
        "t_pmic": t_pmic,
        "t_wmt": t_wmt,
        "t_bat": t_bat,
        "cap": cap,
        "stat": stat,
        "susp": susp,
        "watts": watts,
        "ma": ma,
        "volts": v_str,
        "wifi": f"{wifi_ip}:2222",
        "usb": f"{usb_ip}:2222",
    }
    return cached_info


def draw_bar(d, x, y, w, h, pct, col_fg):
    d.rectangle([x, y, x + w, y + h], fill=(22, 30, 34, 255), outline=(55, 75, 80, 255), width=2)
    fw = int(max(0, min(100, pct)) * (w - 4) / 100.0)
    if fw > 0:
        d.rectangle([x + 2, y + 2, x + 2 + fw, y + h - 2], fill=col_fg)


def render_frame():
    info = read_sys_info()
    img = Image.new("RGBA", (BW, H), (8, 12, 14, 255))
    d = ImageDraw.Draw(img)
    f_hdr = ImageFont.truetype(FONT_PATH, 28)
    f_sub = ImageFont.truetype(FONT_PATH, 23)
    f_term = ImageFont.truetype(FONT_PATH, 24)

    # Top dashboard panel
    d.rectangle([20, 35, W - 20, 520], fill=(12, 22, 20, 255), outline=(0, 210, 120, 255), width=3)
    d.text((38, 50), f"XIAOMI 11T | UBUNTU 22.04 | UP {info['up']}", font=f_hdr, fill=(0, 245, 130, 255))

    # CPU bar
    c_col = (0, 230, 130, 255) if info["cpu_pct"] < 70 else (255, 180, 50, 255)
    d.text((38, 95), f"CPU: {info['cpu_pct']:5.1f}%  ({info['freqs']})", font=f_sub, fill=(225, 240, 235, 255))
    draw_bar(d, 680, 97, 340, 24, info["cpu_pct"], c_col)

    # GPU bar
    d.text((38, 135), f"GPU: {info['gpu_pct']:3d}%  ({info['gpu_desc']})", font=f_sub, fill=(170, 230, 255, 255))
    draw_bar(d, 680, 137, 340, 24, info["gpu_pct"], (80, 190, 255, 255))

    # RAM bar
    d.text((38, 175), f"RAM: {info['mem_used']}/{info['mem_tot']} MB ({info['mem_pct']:.0f}%)", font=f_sub, fill=(235, 235, 190, 255))
    draw_bar(d, 680, 177, 340, 24, info["mem_pct"], (240, 205, 80, 255))

    # Power & Battery
    d.text((38, 222), f"GUC: {info['watts']:.2f} W  ({info['ma']:.0f} mA @ {info['volts']:.2f} V)", font=f_sub, fill=(255, 145, 120, 255))
    d.text((38, 260), f"PIL: {info['cap']}% | {info['stat']} | Sarj Kesme: {info['susp']}", font=f_sub, fill=(255, 215, 110, 255))

    # Temperatures
    d.text((38, 305), f"ISI: CPU {info['t_cpu']:.1f}C | AP {info['t_ap']:.1f}C | PMIC {info['t_pmic']:.1f}C", font=f_sub, fill=(255, 170, 170, 255))
    d.text((38, 342), f"     WiFi {info['t_wmt']:.1f}C | Batarya {info['t_bat']:.1f}C", font=f_sub, fill=(255, 170, 170, 255))

    # Network & controls
    d.text((38, 390), f"Wi-Fi SSH: {info['wifi']}  |  USB: {info['usb']}", font=f_sub, fill=(130, 230, 255, 255))
    d.text((38, 428), "Chrome UI: http://192.168.2.212:8080", font=f_sub, fill=(160, 245, 195, 255))
    d.text((38, 470), "Guc Tusu: Ekran Ac/Kapa  |  SSH: ekran baglan", font=f_sub, fill=(150, 175, 165, 255))

    # Terminal box
    d.rectangle([20, 540, W - 20, H - 30], fill=(5, 8, 10, 255), outline=(60, 90, 80, 255), width=2)
    with lock:
        disp = list(vt_screen.display)
        cy, cx = vt_screen.cursor.y, vt_screen.cursor.x

    y = 560
    for idx, ln in enumerate(disp):
        color = (0, 235, 130, 255) if ("@ubuntu-agate:" in ln or ln.startswith("root@") or ln.startswith("ubuntu@")) else (225, 232, 228, 255)
        d.text((38, y), ln, font=f_term, fill=color)
        if idx == cy:
            cx_px = 38 + int(cx * 14.45)
            d.rectangle([cx_px, y + 4, cx_px + 13, y + 29], outline=(0, 255, 140, 255), width=2)
        y += 35

    raw = img.tobytes()
    fd = os.open("/dev/fb0", os.O_RDWR)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, raw)
        vinfo = bytearray(160)
        fcntl.ioctl(fd, 0x4600, vinfo)
        struct.pack_into("<II", vinfo, 20, 0, 0)
        fcntl.ioctl(fd, 0x4606, vinfo)
    finally:
        os.close(fd)


def pty_worker():
    global dirty
    try:
        os.remove(TMUX_SOCK)
    except Exception:
        pass
    pid, master_fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.environ["HOME"] = "/root"
        os.environ["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        os.chdir("/root")
        os.execv("/usr/bin/tmux", [
            "/usr/bin/tmux", "-S", TMUX_SOCK, "new-session", "-A", "-s", "console"
        ])
    else:
        winsize = struct.pack("HHHH", ROWS, COLS, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
        for _ in range(25):
            if os.path.exists(TMUX_SOCK):
                break
            time.sleep(0.1)
        try:
            os.chmod(TMUX_SOCK, 0o666)
            subprocess.run(["tmux", "-S", TMUX_SOCK, "set-option", "-g", "status", "off"], stderr=subprocess.DEVNULL)
            subprocess.run(["tmux", "-S", TMUX_SOCK, "set-option", "-g", "window-size", "smallest"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        os.write(master_fd, b"clear && uname -a && batstat && df -h /\n")
        if not os.path.exists(TERM_PIPE):
            os.mkfifo(TERM_PIPE, 0o622)
        os.chmod(TERM_PIPE, 0o622)
        fifo_fd = os.open(TERM_PIPE, os.O_RDONLY | os.O_NONBLOCK)
        while True:
            rlist, _, _ = select.select([master_fd, fifo_fd], [], [], 1.0)
            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        with lock:
                            vt_stream.feed(data.decode("utf-8", "ignore"))
                        dirty = True
                except OSError:
                    break
            if fifo_fd in rlist:
                try:
                    cmd = os.read(fifo_fd, 4096)
                    if cmd:
                        os.write(master_fd, cmd)
                except OSError:
                    pass


def key_watcher():
    global last_toggle
    ev_fmt = "llHHI"
    ev_sz = struct.calcsize(ev_fmt)
    fd = None
    for path in ["/dev/input/event1", "/dev/input/event0"]:
        try:
            fd = os.open(path, os.O_RDONLY)
            break
        except Exception:
            pass
    if fd is None:
        return
    while True:
        try:
            data = os.read(fd, ev_sz)
            if len(data) < ev_sz:
                continue
            _, _, ev_type, ev_code, ev_val = struct.unpack(ev_fmt, data)
            if ev_type == 1 and ev_code == 116 and ev_val == 1:
                now = time.time()
                if now - last_toggle > 0.35:
                    last_toggle = now
                    set_panel(not screen_on)
            elif ev_type == 1 and ev_code in (114, 115) and ev_val == 1:
                if not screen_on:
                    set_panel(True)
        except Exception:
            time.sleep(0.5)


def ctl_watcher():
    if os.path.exists(CTL_FIFO):
        try:
            os.remove(CTL_FIFO)
        except Exception:
            pass
    os.mkfifo(CTL_FIFO, 0o666)
    os.chmod(CTL_FIFO, 0o666)
    while True:
        try:
            with open(CTL_FIFO, "r") as f:
                for line in f:
                    cmd = line.strip().lower()
                    if cmd in ("on", "ac", "1"):
                        set_panel(True)
                    elif cmd in ("off", "kapat", "0"):
                        set_panel(False)
                    elif cmd in ("toggle", "degistir"):
                        set_panel(not screen_on)
        except Exception:
            time.sleep(0.5)


def main():
    global dirty
    set_panel(True)
    threading.Thread(target=pty_worker, daemon=True).start()
    threading.Thread(target=key_watcher, daemon=True).start()
    threading.Thread(target=ctl_watcher, daemon=True).start()
    last_draw = 0.0
    while True:
        now = time.time()
        if screen_on and (dirty or now - last_draw >= 2.0):
            dirty = False
            last_draw = now
            try:
                render_frame()
            except Exception:
                pass
        time.sleep(0.08)


if __name__ == "__main__":
    main()

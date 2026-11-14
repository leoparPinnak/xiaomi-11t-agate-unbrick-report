#!/usr/bin/env python3
"""
Xiaomi 11T (agate) - Zero-Broker Hardware-JPEG UDP Desktop Client (PySide6 / Qt6)
Protocol (UDP :9900):
  Client -> Server:
    "AGTH"                         Hello / keepalive
    "AGTI" + 1 + act(u8)+btn(u8)+x(i16)+y(i16)   Mouse (0=move,1=down,2=up,3=wheel)
    "AGTI" + 2 + mods(u8)+keysym(u32)            Special / shortcut key (ctrl=1,alt=2,shift=4,meta=8)
    "AGTI" + 3 + len(u16)+utf8                   UTF-8 text (full Turkish support)
    "AGTI" + 4 + cmd(u8)                         1=Chromium,2=Terminal,3=Files,4=ScreenToggle,5=Land,6=Port
  Server -> Client:
    "AGTS" + w(u16) + h(u16) + scr(u8)           Hello Ack
    "AGTU" + fid(u32)+sz(u32)+idx(u16)+cnt(u16)  Chunked Hardware-JPEG frame (<=1360B/pkt)
"""
import socket
import struct
import sys
import threading
import time
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFrame
)

DEFAULT_HOST = "192.168.2.212"
DEFAULT_PORT = 9900

QT_KEY_TO_KEYSYM = {
    Qt.Key_Return: 0xFF0D, Qt.Key_Enter: 0xFF0D,
    Qt.Key_Backspace: 0xFF08, Qt.Key_Tab: 0xFF09, Qt.Key_Backtab: 0xFF09,
    Qt.Key_Escape: 0xFF1B, Qt.Key_Delete: 0xFFFF, Qt.Key_Insert: 0xFF63,
    Qt.Key_Home: 0xFF50, Qt.Key_End: 0xFF57,
    Qt.Key_PageUp: 0xFF55, Qt.Key_PageDown: 0xFF56,
    Qt.Key_Left: 0xFF51, Qt.Key_Up: 0xFF52, Qt.Key_Right: 0xFF53, Qt.Key_Down: 0xFF54,
    Qt.Key_Space: 0x0020,
    Qt.Key_F1: 0xFFBE, Qt.Key_F2: 0xFFBF, Qt.Key_F3: 0xFFC0, Qt.Key_F4: 0xFFC1,
    Qt.Key_F5: 0xFFC2, Qt.Key_F6: 0xFFC3, Qt.Key_F7: 0xFFC4, Qt.Key_F8: 0xFFC5,
    Qt.Key_F9: 0xFFC6, Qt.Key_F10: 0xFFC7, Qt.Key_F11: 0xFFC8, Qt.Key_F12: 0xFFC9,
    Qt.Key_Super_L: 0xFFEB, Qt.Key_Super_R: 0xFFEC,
}


class UdpSignals(QObject):
    tile_ready = Signal(int, int, int, int, QImage)  # tx, ty, full_w, full_h, tile_img
    stats_ready = Signal(int, int, float, int, int)  # fps, kbps, loss_pct, w, h
    telemetry_ready = Signal(float, int, int, float, int, int, int, float, int, int)  # cpu, ram_u, ram_t, temp, bat_pct, bat_state, bat_ma, bat_temp, scr_on, fb_mir


class UdpTransport:
    def __init__(self, signals: UdpSignals):
        self.signals = signals
        self.sock = None
        self.host = DEFAULT_HOST
        self.port = DEFAULT_PORT
        self.running = False
        self.rx_thread = None
        self.ka_thread = None
        self.remote_w = 3840
        self.remote_h = 2160
        self.fps_cnt = 0
        self.bytes_cnt = 0
        self.frames_seen = 0
        self.frames_ok = 0

    def start(self, host: str, port: int):
        self.stop()
        self.host = host.strip()
        self.port = int(port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
        self.sock.settimeout(0.25)
        self.running = True
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.ka_thread = threading.Thread(target=self._ka_loop, daemon=True)
        self.rx_thread.start()
        self.ka_thread.start()
        self.send_hello()

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _sendto(self, data: bytes):
        if self.sock and self.running:
            try:
                self.sock.sendto(data, (self.host, self.port))
            except Exception:
                pass

    def send_hello(self):
        self._sendto(b"AGTH")

    def send_mouse(self, act: int, btn: int, x: int, y: int):
        pkt = b"AGTI" + struct.pack("<BBBhh", 1, act, btn, x, y)
        self._sendto(pkt)

    def send_key(self, mods: int, keysym: int):
        pkt = b"AGTI" + struct.pack("<BBI", 2, mods, keysym)
        self._sendto(pkt)

    def send_text(self, txt: str):
        raw = txt.encode("utf-8", errors="ignore")
        if not raw:
            return
        for i in range(0, len(raw), 1200):
            chunk = raw[i:i + 1200]
            pkt = b"AGTI" + struct.pack("<BH", 3, len(chunk)) + chunk
            self._sendto(pkt)

    def send_cmd(self, cmd_id: int):
        pkt = b"AGTI" + struct.pack("<BB", 4, cmd_id)
        self._sendto(pkt)

    def _ka_loop(self):
        last_stat = time.monotonic()
        while self.running:
            self.send_hello()
            now = time.monotonic()
            if now - last_stat >= 1.0:
                dt = now - last_stat
                fps = round(self.fps_cnt / dt)
                kbps = round((self.bytes_cnt / 1024.0) / dt)
                loss = 0.0
                if self.frames_seen > 0:
                    loss = max(0.0, 100.0 * (self.frames_seen - self.frames_ok) / self.frames_seen)
                self.fps_cnt = 0
                self.bytes_cnt = 0
                self.frames_seen = 0
                self.frames_ok = 0
                last_stat = now
                self.signals.stats_ready.emit(fps, kbps, loss, self.remote_w, self.remote_h)
            time.sleep(0.5)

    def _rx_loop(self):
        inflight = {}  # fid -> [cnt, total_sz, parts_dict, ts, tx, ty, fw, fh]
        latest_tile_fid = {}  # (tx, ty) -> last completed fid
        seen_fids = set()

        while self.running and self.sock:
            try:
                pkt, _ = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except Exception:
                break

            if len(pkt) >= 9 and pkt[:4] == b"AGTS":
                w, h, _ = struct.unpack("<HHB", pkt[4:9])
                if 200 <= w <= 4096 and 200 <= h <= 4096:
                    self.remote_w = w
                    self.remote_h = h
                continue

            if len(pkt) >= 24 and pkt[:4] == b"AGTM":
                cpu_x10, ram_u, ram_t, temp_x10, bpct, bstat, bma, bt_x10, son, fbm, w, h = struct.unpack(
                    "<HHHhBBhhBBHH", pkt[4:24]
                )
                if 200 <= w <= 4096 and 200 <= h <= 4096:
                    self.remote_w, self.remote_h = w, h
                self.signals.telemetry_ready.emit(
                    cpu_x10 / 10.0, ram_u, ram_t, temp_x10 / 10.0,
                    bpct, bstat, bma, bt_x10 / 10.0, son, fbm
                )
                continue

            if len(pkt) >= 24 and pkt[:4] == b"AGTT":
                fid, total_sz, idx, cnt, tx, ty, fw, fh = struct.unpack("<IIHHHHHH", pkt[4:24])
                hdr_len = 24
            elif len(pkt) >= 16 and pkt[:4] == b"AGTU":
                fid, total_sz, idx, cnt = struct.unpack("<IIHH", pkt[4:16])
                tx, ty, fw, fh = 0, 0, self.remote_w, self.remote_h
                hdr_len = 16
            else:
                continue

            if fid <= latest_tile_fid.get((tx, ty), 0) or cnt == 0 or idx >= cnt:
                continue

            if fid not in seen_fids:
                seen_fids.add(fid)
                self.frames_seen += 1
                if len(seen_fids) > 256:
                    seen_fids = {x for x in seen_fids if x >= fid - 128}

            entry = inflight.get(fid)
            if entry is None:
                entry = [cnt, total_sz, {}, time.monotonic(), tx, ty, fw, fh]
                inflight[fid] = entry

            entry[2][idx] = pkt[hdr_len:]
            self.bytes_cnt += len(pkt)

            if len(entry[2]) == cnt:
                latest_tile_fid[(entry[4], entry[5])] = fid
                self.frames_ok += 1
                self.fps_cnt += 1
                jpg = b"".join(entry[2][i] for i in range(cnt))
                del inflight[fid]
                img = QImage.fromData(jpg, "JPEG")
                if not img.isNull():
                    if fw > 0 and fh > 0:
                        self.remote_w, self.remote_h = fw, fh
                    self.signals.tile_ready.emit(entry[4], entry[5], self.remote_w, self.remote_h, img)
            elif len(inflight) > 12:
                now = time.monotonic()
                for old_id in [k for k, v in inflight.items() if now - v[3] > 0.35]:
                    del inflight[old_id]


class ScreenCanvas(QWidget):
    def __init__(self, transport: UdpTransport):
        super().__init__()
        self.transport = transport
        self.img: QImage | None = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.dragging = False
        self.last_move_ts = 0.0
        self.draw_rect = (0, 0, 1, 1)

    def set_tile(self, tx: int, ty: int, fw: int, fh: int, tile: QImage):
        if self.img is None or self.img.width() != fw or self.img.height() != fh:
            self.img = QImage(fw, fh, QImage.Format_RGB32)
            self.img.fill(QColor("#040608"))
        p = QPainter(self.img)
        p.drawImage(tx, ty, tile)
        p.end()
        self.update()

    def _map_pos(self, pos: QPoint):
        dx, dy, dw, dh = self.draw_rect
        if dw <= 1 or dh <= 1:
            return 0, 0
        rx = round((pos.x() - dx) * self.transport.remote_w / dw)
        ry = round((pos.y() - dy) * self.transport.remote_h / dh)
        rx = max(0, min(self.transport.remote_w - 1, rx))
        ry = max(0, min(self.transport.remote_h - 1, ry))
        return rx, ry

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#040608"))
        if self.img and not self.img.isNull():
            rw, rh = self.width(), self.height()
            iw, ih = self.img.width(), self.img.height()
            scale = min(rw / iw, rh / ih)
            dw, dh = max(1, int(iw * scale)), max(1, int(ih * scale))
            dx, dy = (rw - dw) // 2, (rh - dh) // 2
            self.draw_rect = (dx, dy, dw, dh)
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            p.drawImage(self.rect().adjusted(dx, dy, -(rw - dx - dw), -(rh - dy - dh)), self.img)
        else:
            p.setPen(QColor("#8496ad"))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(self.rect(), Qt.AlignCenter, "UDP akışı bekleniyor (192.168.2.212:9900)...")
        p.end()

    def mousePressEvent(self, ev):
        self.setFocus()
        self.dragging = True
        btn = 3 if ev.button() == Qt.RightButton else (2 if ev.button() == Qt.MiddleButton else 1)
        x, y = self._map_pos(ev.position().toPoint())
        self.transport.send_mouse(1, btn, x, y)

    def mouseReleaseEvent(self, ev):
        self.dragging = False
        btn = 3 if ev.button() == Qt.RightButton else (2 if ev.button() == Qt.MiddleButton else 1)
        x, y = self._map_pos(ev.position().toPoint())
        self.transport.send_mouse(2, btn, x, y)

    def mouseMoveEvent(self, ev):
        now = time.monotonic()
        if now - self.last_move_ts < (0.014 if self.dragging else 0.032):
            return
        self.last_move_ts = now
        x, y = self._map_pos(ev.position().toPoint())
        self.transport.send_mouse(0, 0, x, y)

    def wheelEvent(self, ev):
        btn = 4 if ev.angleDelta().y() > 0 else 5
        x, y = self._map_pos(ev.position().toPoint())
        self.transport.send_mouse(3, btn, x, y)

    def keyPressEvent(self, ev: QKeyEvent):
        if ev.key() == Qt.Key_F11:
            w = self.window()
            if w.isFullScreen():
                w.showNormal()
            else:
                w.showFullScreen()
            return
        if ev.key() in (Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_AltGr):
            return
        m = ev.modifiers()
        mods = (1 if (m & Qt.ControlModifier) else 0) | (2 if (m & Qt.AltModifier) else 0) | \
               (4 if (m & Qt.ShiftModifier) else 0) | (8 if (m & Qt.MetaModifier) else 0)

        if ev.key() in QT_KEY_TO_KEYSYM:
            self.transport.send_key(mods, QT_KEY_TO_KEYSYM[ev.key()])
            return

        txt = ev.text()
        if (mods & (1 | 2 | 8)) and Qt.Key_A <= ev.key() <= Qt.Key_Z:
            ks = ord('a') + (ev.key() - Qt.Key_A)
            self.transport.send_key(mods, ks)
            return
        if txt:
            self.transport.send_text(txt)


class MainWindow(QMainWindow):
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        super().__init__()
        self.setWindowTitle("Xiaomi 11T · Saf UDP Donanım JPEG Masaüstü İstemcisi (:9900)")
        self.resize(1440, 820)
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #070a0f; color: #e6eef8; font-family: "Segoe UI", sans-serif; }
            QPushButton { background: #182334; border: 1px solid #2c3f57; border-radius: 5px; padding: 4px 9px; font-size: 11px; }
            QPushButton:hover { background: #23334b; border-color: #38bdf8; }
            QPushButton#accent { background: #00e599; color: #052114; border-color: #00e599; font-weight: bold; }
            QLineEdit { background: #05080c; border: 1px solid #2c3f57; border-radius: 5px; padding: 3px 7px; font-size: 11.5px; color: #e6eef8; }
            QLabel#pill { background: #131c29; border: 1px solid #27374d; border-radius: 9px; padding: 2px 8px; font-family: Consolas, monospace; font-size: 11px; }
        """)

        self.signals = UdpSignals()
        self.transport = UdpTransport(self.signals)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # Top control bar
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.ip_edit = QLineEdit(f"{host}:{port}")
        self.ip_edit.setFixedWidth(155)
        btn_conn = QPushButton("Bağlan")
        btn_conn.setObjectName("accent")
        btn_conn.clicked.connect(self.reconnect)

        self.lbl_stat = QLabel("UDP FPS: -- | -- KB/s | Kayıp: 0.0% | 3840×2160")
        self.lbl_stat.setObjectName("pill")
        self.lbl_tel = QLabel("CPU --% · RAM --MB · --°C · Bat --% · Ekran: --")
        self.lbl_tel.setObjectName("pill")
        self.lbl_tel.setStyleSheet("background:#10221c; border:1px solid #1f5c43; color:#7ef0be; border-radius:9px; padding:2px 8px; font-family:Consolas,monospace; font-size:11px;")

        btn_chr = QPushButton("🌐 Chromium")
        btn_chr.clicked.connect(lambda: self.transport.send_cmd(1))
        btn_term = QPushButton("💻 Terminal")
        btn_term.clicked.connect(lambda: self.transport.send_cmd(2))
        btn_files = QPushButton("📁 Dosyalar")
        btn_files.clicked.connect(lambda: self.transport.send_cmd(3))
        btn_4k = QPushButton("4K")
        btn_4k.clicked.connect(lambda: self.transport.send_cmd(7))
        btn_1080 = QPushButton("1080p")
        btn_1080.clicked.connect(lambda: self.transport.send_cmd(8))
        btn_scr = QPushButton("💡 Ekran")
        btn_scr.clicked.connect(lambda: self.transport.send_cmd(4))
        btn_land = QPushButton("↔ Yatay")
        btn_land.clicked.connect(lambda: self.transport.send_cmd(5))
        btn_port = QPushButton("↕ Dikey")
        btn_port.clicked.connect(lambda: self.transport.send_cmd(6))
        btn_fs = QPushButton("⛶ F11")
        btn_fs.clicked.connect(self.toggle_fs)

        bar.addWidget(QLabel("UDP:"))
        bar.addWidget(self.ip_edit)
        bar.addWidget(btn_conn)
        bar.addWidget(self.lbl_stat)
        bar.addWidget(self.lbl_tel)
        bar.addStretch(1)
        for b in (btn_chr, btn_term, btn_files, btn_4k, btn_1080, btn_scr, btn_land, btn_port, btn_fs):
            bar.addWidget(b)
        root.addLayout(bar)

        # Keyboard & shortcut bar
        kbar = QHBoxLayout()
        kbar.setSpacing(5)
        self.kb_edit = QLineEdit()
        self.kb_edit.setPlaceholderText("Telefona Türkçe metin gönder (Enter = yaz + Enter)...")
        self.kb_edit.returnPressed.connect(lambda: self.send_kb(True))
        btn_send = QPushButton("Gönder")
        btn_send.clicked.connect(lambda: self.send_kb(False))
        kbar.addWidget(QLabel("⌨️:"))
        kbar.addWidget(self.kb_edit, 1)
        kbar.addWidget(btn_send)
        for label, mods, ks in [
            ("Ctrl+A", 1, ord("a")), ("Ctrl+C", 1, ord("c")), ("Ctrl+V", 1, ord("v")),
            ("Ctrl+T", 1, ord("t")), ("Ctrl+W", 1, ord("w")), ("Alt+Tab", 2, 0xFF09),
            ("Esc", 0, 0xFF1B), ("Enter", 0, 0xFF0D),
        ]:
            b = QPushButton(label)
            b.clicked.connect(lambda _, m=mods, k=ks: (self.transport.send_key(m, k), self.canvas.setFocus()))
            kbar.addWidget(b)
        root.addLayout(kbar)

        self.canvas = ScreenCanvas(self.transport)
        root.addWidget(self.canvas, 1)

        self.signals.tile_ready.connect(self.canvas.set_tile)
        self.signals.stats_ready.connect(self.on_stats)
        self.signals.telemetry_ready.connect(self.on_telemetry)

        self.reconnect()
        self.canvas.setFocus()

    def reconnect(self):
        txt = self.ip_edit.text().strip()
        if ":" in txt:
            h, p = txt.rsplit(":", 1)
            self.transport.start(h, int(p))
        else:
            self.transport.start(txt, DEFAULT_PORT)

    def send_kb(self, with_enter: bool):
        t = self.kb_edit.text()
        if t:
            self.transport.send_text(t)
            self.kb_edit.clear()
        if with_enter:
            self.transport.send_key(0, 0xFF0D)
        self.canvas.setFocus()

    def on_stats(self, fps: int, kbps: int, loss: float, w: int, h: int):
        self.lbl_stat.setText(f"UDP FPS: {fps} | {kbps} KB/s | Kayıp: {loss:.1f}% | {w}×{h}")

    def on_telemetry(self, cpu: float, ram_u: int, ram_t: int, temp: float, bat_pct: int, bat_state: int, bat_ma: int, bat_temp: float, scr_on: int, fb_mir: int):
        if bat_state == 2:
            btxt = f"⛔%{bat_pct} (%70 Durduruldu)"
        elif bat_state == 1:
            btxt = f"⚡%{bat_pct} (+{abs(bat_ma)}mA)"
        elif bat_state == 3:
            btxt = f"✅%{bat_pct} (Dolu)"
        else:
            btxt = f"🔋%{bat_pct} ({bat_ma}mA)"
        stxt = "AÇIK" if scr_on else ("DONDURULDU" if not fb_mir else "KAPALI")
        self.lbl_tel.setText(
            f"CPU {cpu:.1f}% · RAM {ram_u}/{ram_t}MB · {temp:.1f}°C · {btxt} ({bat_temp:.1f}°C) · Ekran:{stxt}"
        )

    def toggle_fs(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def closeEvent(self, ev):
        self.transport.stop()
        super().closeEvent(ev)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    win = MainWindow(host, port)
    win.show()
    sys.exit(app.exec())

#!/bin/bash
pkill -f fbui.py 2>/dev/null || true
tmux -S /tmp/fbconsole.sock kill-server 2>/dev/null || true
pkill -f fb_xfce_bridge 2>/dev/null || true
pkill -f "Xvfb :0" 2>/dev/null || true
pkill -f "xfce4-session" 2>/dev/null || true
pkill -f "chr_xfce" 2>/dev/null || true
sleep 0.5

chmod 666 /dev/null /dev/zero /dev/urandom /dev/tty /dev/ptmx /dev/input/event4 2>/dev/null || true
mkdir -p /dev/shm/xfb
chmod 777 /dev/shm/xfb
Xvfb :0 -screen 0 1080x2400x24 -fbdir /dev/shm/xfb >/var/log/xvfb0.log 2>&1 &
for i in $(seq 1 30); do [ -f /dev/shm/xfb/Xvfb_screen0 ] && break; sleep 0.1; done

/usr/local/sbin/fb_xfce_bridge :0 >/var/log/fb_bridge.log 2>&1 &
sleep 0.6

su - ubuntu -c "DISPLAY=:0 DBUS_SESSION_BUS_ADDRESS= nohup dbus-launch --exit-with-session startxfce4 >/tmp/xfce.log 2>&1 &"
sleep 3
su - ubuntu -c "DISPLAY=:0 nohup /usr/bin/chromium --no-sandbox --test-type --disable-dev-shm-usage --window-size=1080,1900 --window-position=0,80 --user-data-dir=/home/ubuntu/.config/chr_xfce https://www.google.com/ >/tmp/chr_xfce.log 2>&1 &"

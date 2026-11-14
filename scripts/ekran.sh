#!/bin/bash
CTL=/run/fbui.ctl
case "$1" in
  ac|on|1)     echo on > "$CTL" ;;
  kapat|off|0) echo off > "$CTL" ;;
  toggle|t)    echo toggle > "$CTL" ;;
  xfce)
    /usr/local/sbin/start_xfce_fb.sh
    echo "XFCE masaustu telefon ekranina basildi (Guc tusu: ac/kapa, Dokunmatik aktif)"
    ;;
  terminal|dash)
    pkill -f fb_xfce_bridge 2>/dev/null || true
    pkill -f "xfce4-session" 2>/dev/null || true
    pkill -f "Xvfb :0" 2>/dev/null || true
    sleep 0.4
    nohup /usr/bin/python3 /usr/local/sbin/fbui.py >/var/log/fbui.log 2>&1 </dev/null &
    echo "Terminal dashboard moduna donuldu"
    ;;
  baglan|attach)
    exec tmux -S /tmp/fbconsole.sock attach -t console
    ;;
  cmd)
    shift
    tmux -S /tmp/fbconsole.sock send-keys -t console "$*" C-m
    ;;
  durum|status)
    echo "brightness=$(cat /sys/class/leds/lcd-backlight/brightness) blank=$(cat /sys/class/graphics/fb0/blank)"
    pgrep -af "fbui.py|fb_xfce_bridge|Xvfb :0|xfce4-session" || true
    ;;
  *)
    echo "Kullanim: ekran [ac|kapat|toggle|xfce|terminal|baglan|cmd <komut>|durum]"
    ;;
esac

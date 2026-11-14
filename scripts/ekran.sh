#!/bin/bash
case "$1" in
  ac|on|1) echo on > /run/fbui.ctl ;;
  kapat|off|0) echo off > /run/fbui.ctl ;;
  toggle|t|"") echo toggle > /run/fbui.ctl ;;
  baglan|attach) exec tmux -S /tmp/fbconsole.sock attach -t console ;;
  cmd) shift; printf "%s\n" "$*" > /run/fbtty.in ;;
  durum|status)
    echo "Parlaklik: $(cat /sys/class/leds/lcd-backlight/brightness)"
    echo "Blank    : $(cat /sys/class/graphics/fb0/blank)"
    ;;
  *) echo "Kullanim: ekran [ac|kapat|toggle|baglan|durum|cmd <komut>]" ;;
esac

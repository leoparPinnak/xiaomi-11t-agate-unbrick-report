#!/bin/bash
BAT=/sys/class/power_supply/battery
while true; do
    CAP=$(cat "$BAT/capacity" 2>/dev/null || echo 50)
    TEMP=$(cat "$BAT/temp" 2>/dev/null || echo 300)
    CUR=$(cat "$BAT/input_suspend" 2>/dev/null || echo 0)
    if [ "$TEMP" -ge 420 ] 2>/dev/null; then
        [ "$CUR" != "1" ] && echo 1 > "$BAT/input_suspend" 2>/dev/null
    elif [ "$CAP" -ge 70 ] 2>/dev/null; then
        [ "$CUR" != "1" ] && echo 1 > "$BAT/input_suspend" 2>/dev/null
    elif [ "$CAP" -le 60 ] 2>/dev/null; then
        [ "$CUR" != "0" ] && echo 0 > "$BAT/input_suspend" 2>/dev/null
    fi
    sleep 30
done

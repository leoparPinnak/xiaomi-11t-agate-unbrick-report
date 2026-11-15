#!/system/bin/sh
# Agate AOSP Charge Guard: 70% stop / 67% resume hysteresis
BAT=/sys/class/power_supply/battery
while true; do
    LIMIT=$(getprop persist.agate.charge_limit)
    CAP=$(cat "$BAT/capacity" 2>/dev/null || echo 50)
    SUSP=$(cat "$BAT/input_suspend" 2>/dev/null || echo 0)
    if [ "$LIMIT" = "false" ] || [ "$LIMIT" = "0" ]; then
        if [ "$SUSP" = "1" ]; then
            echo 0 > "$BAT/input_suspend" 2>/dev/null || true
        fi
    else
        if [ "$CAP" -ge 70 ] && [ "$SUSP" != "1" ]; then
            echo 1 > "$BAT/input_suspend" 2>/dev/null || true
        elif [ "$CAP" -le 67 ] && [ "$SUSP" = "1" ]; then
            echo 0 > "$BAT/input_suspend" 2>/dev/null || true
        fi
    fi
    sleep 15
done

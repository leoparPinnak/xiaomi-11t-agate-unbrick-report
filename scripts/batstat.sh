#!/bin/bash
B=/sys/class/power_supply/battery
CAP=$(cat $B/capacity)
STAT=$(cat $B/status)
SUSP=$(cat $B/input_suspend)
TEMP=$(awk '{printf "%.1f C", $1/10}' $B/temp)
VOLT=$(awk '{printf "%.3f V", $1/1000000}' $B/voltage_now)
echo "Batarya: ${CAP}% | Durum: ${STAT} | Sarj Kesme (input_suspend): ${SUSP} | Sicaklik: ${TEMP} | Voltaj: ${VOLT}"

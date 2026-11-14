#!/bin/bash
case "$1" in
  max|on|1)
    echo 886000 > /proc/gpufreq/gpufreq_opp_freq
    echo 1 > /proc/mali/always_on 2>/dev/null || true
    for p in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do
        echo performance > "$p" 2>/dev/null || true
    done
    echo "MAX: GPU=886MHz always_on, CPU=performance"
    ;;
  auto|off|0)
    echo 0 > /proc/gpufreq/gpufreq_opp_freq
    echo 0 > /proc/mali/always_on 2>/dev/null || true
    for p in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do
        echo schedutil > "$p" 2>/dev/null || true
    done
    echo "AUTO: GPU=DVFS, CPU=schedutil"
    ;;
  *)
    cat /proc/gpufreq/gpufreq_opp_freq
    grep -E "idx:|real|g_power" /proc/gpufreq/gpufreq_var_dump
    echo "cpu: $(cat /sys/devices/system/cpu/cpufreq/policy*/scaling_governor | tr '\n' ' ')"
    ;;
esac

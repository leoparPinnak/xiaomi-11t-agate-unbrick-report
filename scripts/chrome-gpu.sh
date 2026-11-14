#!/bin/bash
set -e
XDG_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg_chrome_rt}"
mkdir -p "$XDG_DIR" && chmod 700 "$XDG_DIR"
export XDG_RUNTIME_DIR="$XDG_DIR"
if [ ! -S "$XDG_DIR/wayland-1" ]; then
    /usr/bin/weston --backend=headless-backend.so --socket=wayland-1 --width=1920 --height=1080 >/dev/null 2>&1 &
    for i in $(seq 1 30); do [ -S "$XDG_DIR/wayland-1" ] && break; sleep 0.1; done
fi
export WAYLAND_DISPLAY=wayland-1
export LD_LIBRARY_PATH=/usr/local/hybris/lib
export HYBRIS_LD_LIBRARY_PATH=/mnt/avendor/lib64:/mnt/avendor/lib64/egl:/mnt/avendor/lib64/hw:/mnt/asystem/system/lib64:/mnt/asystem/system/lib64/bootstrap:/apex/com.android.runtime/lib64/bionic
export HYBRIS_EGLPLATFORM=wayland
export LIBEGL=/mnt/avendor/lib64/egl/libGLES_mali.so
export LIBGLESV2=/mnt/avendor/lib64/egl/libGLES_mali.so
export DBUS_SESSION_BUS_ADDRESS=disabled:
exec /usr/bin/chromium --no-sandbox --disable-dev-shm-usage --ozone-platform=wayland --use-gl=angle --use-angle=gles --disable-vulkan --disable-features=Vulkan,Translate,OptimizationHints,MediaRouter,InterestCohort --ignore-gpu-blocklist --enable-webgl --disable-blink-features=AutomationControlled --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --no-first-run --no-default-browser-check --disable-infobars --password-store=basic --use-mock-keychain --window-size=1920,1080 "$@"

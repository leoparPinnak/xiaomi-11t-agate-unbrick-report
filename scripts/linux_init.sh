#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export HOME=/root

exec >/var/log/linux_init.log 2>&1
echo "=== Ubuntu Native Boot Start ==="

mkdir -p /dev/pts /dev/shm /run /run/sshd /run/wpa_supplicant /tmp
chmod 1777 /tmp
mountpoint -q /dev/pts || mount -t devpts devpts /dev/pts -o gid=5,mode=620
mountpoint -q /dev/shm || mount -t tmpfs tmpfs /dev/shm -o rw,nosuid,nodev,size=512M
mountpoint -q /run || mount -t tmpfs tmpfs /run -o rw,nosuid,nodev,mode=755
mkdir -p /run/sshd /run/wpa_supplicant

hostname -F /etc/hostname 2>/dev/null || hostname ubuntu-agate
ip link set lo up
chmod 666 /dev/null /dev/zero /dev/urandom /dev/tty /dev/ptmx 2>/dev/null || true
echo 0 > /sys/class/leds/lcd-backlight/brightness 2>/dev/null || true
echo 1 > /sys/class/graphics/fb0/blank 2>/dev/null || true
dd if=/dev/zero of=/dev/fb0 bs=4096 count=2600 2>/dev/null || true

# Ensure device nodes exist
/bin/busybox mdev -s 2>/dev/null || /usr/bin/busybox mdev -s 2>/dev/null || true

# Bring up USB RNDIS interface if present
for iface in usb0 rndis0; do
    if [ -d "/sys/class/net/$iface" ]; then
        echo "Bringing up USB RNDIS on $iface (192.168.77.1/24)"
        ip link set "$iface" up
        ip addr flush dev "$iface"
        ip addr add 192.168.77.1/24 dev "$iface"
        cat > /run/udhcpd.conf << EOF
start 192.168.77.10
end 192.168.77.20
interface $iface
opt dns 1.1.1.1 8.8.8.8
opt subnet 255.255.255.0
opt lease 864000
EOF
        /usr/bin/busybox udhcpd /run/udhcpd.conf &
        break
    fi
done

# Start SSH immediately
/usr/sbin/sshd -p 2222
echo "sshd started rc=$?"

# Start 60-70% battery charge protection daemon
/usr/local/sbin/charge-limit.sh &

# Bring up MTK Wi-Fi (conninfra + bt_drv + wmt_chrdev_wifi + wlan_drv_gen4m)
echo "=== Bringing up MTK Wi-Fi ==="
echo -n /vendor/firmware > /sys/module/firmware_class/parameters/path 2>/dev/null || true
insmod /vendor/lib/modules/conninfra.ko 2>&1 || true
sleep 1
/usr/bin/busybox mdev -s
if [ -e /dev/conninfra_dev ]; then
    LD_LIBRARY_PATH=/system/lib64:/apex/com.android.runtime/lib64/bionic:/vendor/lib64 /vendor/bin/conninfra_loader 2>&1 || true
fi
insmod /vendor/lib/modules/bt_drv.ko 2>&1 || true
insmod /vendor/lib/modules/wmt_chrdev_wifi.ko 2>&1 || true
insmod /vendor/lib/modules/wlan_drv_gen4m.ko 2>&1 || true
sleep 1
/usr/bin/busybox mdev -s
LD_LIBRARY_PATH=/system/lib64:/apex/com.android.runtime/lib64/bionic:/vendor/lib64 /vendor/bin/wlan_assistant >/var/log/wlan_assistant.log 2>&1 &
sleep 2
if [ -e /dev/wmtWifi ]; then
    echo 1 > /dev/wmtWifi 2>&1 || true
    sleep 2
fi

chmod 666 /dev/null /dev/zero /dev/urandom /dev/tty /dev/ptmx 2>/dev/null || true
if [ -d /sys/class/net/wlan0 ]; then
    echo "wlan0 is UP! Connecting Wi-Fi..."
    ip link set wlan0 up
    /usr/sbin/wpa_supplicant -B -i wlan0 -c /etc/wpa_supplicant/wpa_supplicant.conf 2>&1 || true
    /usr/sbin/dhclient -nw wlan0 2>&1 || true
else
    echo "wlan0 failed to appear"
fi

echo "=== Linux init ready ==="
/usr/bin/python3 /usr/local/sbin/fbui.py >/var/log/fbui.log 2>&1 &
mkdir -p /mnt/avendor /mnt/asystem /system
[ ! -e /dev/loop1 ] && mknod -m 0660 /dev/loop1 b 7 1
[ ! -e /dev/loop2 ] && mknod -m 0660 /dev/loop2 b 7 2
busybox losetup -o 1931476992 /dev/loop1 /dev/sdc62 2>/dev/null || true
busybox losetup -o 3399483392 /dev/loop2 /dev/sdc62 2>/dev/null || true
mount -t ext4 -o ro /dev/loop1 /mnt/avendor 2>/dev/null || true
mount -t ext4 -o ro /dev/loop2 /mnt/asystem 2>/dev/null || true
ln -sfn /mnt/avendor /system/vendor
chmod 666 /dev/mali0 /dev/ion /dev/video* /dev/dri/card0 2>/dev/null || true
while true; do
    sleep 60
done

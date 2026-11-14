#!/system/bin/sh
set -e
IMG=/data/ubuntu.img
MNT=/data/ubuntu
BB=/data/adb/magisk/busybox
[ -x "$BB" ] || BB=/data/local/tmp/mp/busybox

/debug_ramdisk/magiskpolicy --live "allow kernel system_data_root_file file { read write getattr open }"

mkdir -p "$MNT"
if [ ! -f "$IMG" ]; then
    truncate -s 32G "$IMG"
    mkfs.ext4 -F -L ubuntu "$IMG"
fi

if ! grep -q " $MNT " /proc/mounts; then
    $BB mount -t ext4 -o loop,rw,noatime "$IMG" "$MNT"
fi

if [ ! -f "$MNT/bin/bash" ]; then
    $BB tar -xpf /data/local/tmp/ubuntu-base.tar.gz -C "$MNT"
fi

mkdir -p "$MNT/dev" "$MNT/dev/pts" "$MNT/dev/shm" "$MNT/proc" "$MNT/sys" "$MNT/tmp" "$MNT/run/sshd"
chmod 1777 "$MNT/tmp"

grep -q " $MNT/proc " /proc/mounts || mount -t proc proc "$MNT/proc"
grep -q " $MNT/sys " /proc/mounts || mount -t sysfs sysfs "$MNT/sys"
grep -q " $MNT/dev " /proc/mounts || mount -o bind /dev "$MNT/dev"
mkdir -p "$MNT/dev/pts" "$MNT/dev/shm"
grep -q " $MNT/dev/pts " /proc/mounts || mount -t devpts devpts "$MNT/dev/pts" -o gid=5,mode=620
grep -q " $MNT/dev/shm " /proc/mounts || mount -t tmpfs tmpfs "$MNT/dev/shm" -o rw,nosuid,nodev,size=512M

cat > "$MNT/etc/resolv.conf" << 'EOF'
nameserver 1.1.1.1
nameserver 8.8.8.8
EOF

cat > "$MNT/etc/hosts" << 'EOF'
127.0.0.1 localhost ubuntu-agate
::1 localhost ip6-localhost ip6-loopback
EOF

mkdir -p "$MNT/etc/apt/apt.conf.d"
cat > "$MNT/etc/apt/apt.conf.d/99android" << 'EOF'
APT::Sandbox::User "root";
EOF

$BB chroot "$MNT" /usr/bin/env -i HOME=/root TERM=xterm-256color PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin /bin/bash -c '
groupadd -f -g 3003 aid_inet
groupadd -f -g 3004 aid_net_raw
groupadd -f -g 3005 aid_net_admin
usermod -aG aid_inet,aid_net_raw,aid_net_admin root
id _apt >/dev/null 2>&1 && usermod -aG aid_inet _apt || true
echo "ubuntu-agate" > /etc/hostname
cat /etc/os-release
uname -a
df -h /
'
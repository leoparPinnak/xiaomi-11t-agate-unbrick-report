import gzip
import hashlib
import io
import os
import stat
import struct

SRC_BOOT = r"C:\mtk\v125\agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global\images\boot.img"
BUSYBOX = r"C:\mtk\ubuntu\busybox-arm64"
OUT_BOOT = r"C:\mtk\ubuntu\ubuntu_native_boot.img"

INIT_SCRIPT = r"""#!/bin/sh
export PATH=/bin:/sbin

/bin/busybox mount -t proc proc /proc
/bin/busybox mount -t sysfs sysfs /sys
/bin/busybox mount -t tmpfs -o mode=0755 tmpfs /dev
/bin/busybox mkdir -p /dev/pts /dev/shm /sys/kernel/config /newroot

/bin/busybox mknod -m 0666 /dev/null c 1 3
/bin/busybox mknod -m 0666 /dev/zero c 1 5
/bin/busybox mknod -m 0666 /dev/urandom c 1 9
/bin/busybox mknod -m 0600 /dev/console c 5 1
/bin/busybox mknod -m 0666 /dev/tty c 5 0
/bin/busybox mknod -m 0600 /dev/kmsg c 1 11
/bin/busybox mknod -m 0660 /dev/loop0 b 7 0

echo /bin/busybox > /proc/sys/kernel/hotplug 2>/dev/null
/bin/busybox mdev -s

log() {
    echo "<6>[linux-init] $1" > /dev/kmsg 2>/dev/null
    echo "[linux-init] $1"
}

setup_rndis() {
    /bin/busybox mount -t configfs none /sys/kernel/config 2>/dev/null || true
    G=/sys/kernel/config/usb_gadget/g1
    if [ -d /sys/kernel/config/usb_gadget ]; then
        mkdir -p "$G/strings/0x409" "$G/configs/b.1/strings/0x409" "$G/functions/rndis.gs4" 2>/dev/null
        echo "" > "$G/UDC" 2>/dev/null || true
        echo 0x2717 > "$G/idVendor"
        echo 0xFF80 > "$G/idProduct"
        echo 0x0223 > "$G/bcdDevice"
        echo 0x0200 > "$G/bcdUSB"
        echo 1 > "$G/os_desc/use" 2>/dev/null || true
        echo 0x1 > "$G/os_desc/b_vendor_code" 2>/dev/null || true
        echo "MSFT100" > "$G/os_desc/qw_sign" 2>/dev/null || true
        echo "agate-linux" > "$G/strings/0x409/serialnumber"
        echo "Xiaomi" > "$G/strings/0x409/manufacturer"
        echo "Xiaomi 11T Linux" > "$G/strings/0x409/product"
        echo "rndis" > "$G/configs/b.1/strings/0x409/configuration"
        echo 500 > "$G/configs/b.1/MaxPower"
        ln -sf "$G/functions/rndis.gs4" "$G/configs/b.1/f1" 2>/dev/null || true
        ln -sf "$G/configs/b.1" "$G/os_desc/b.1" 2>/dev/null || true
        UDC_NAME=$(ls /sys/class/udc 2>/dev/null | head -n 1)
        if [ -n "$UDC_NAME" ]; then
            echo "$UDC_NAME" > "$G/UDC"
            log "USB RNDIS bound to $UDC_NAME"
        fi
    fi
}

setup_rndis

# Find super block device dynamically by PARTNAME=super
SUPER_DEV=""
for i in 1 2 3 4 5 6 7 8 9 10; do
    /bin/busybox mdev -s
    for ue in /sys/class/block/*/uevent; do
        [ -f "$ue" ] || continue
        if /bin/busybox grep -q "^PARTNAME=super$" "$ue"; then
            DEVLINE=$(/bin/busybox cat "$(dirname "$ue")/dev")
            MAJ=${DEVLINE%%:*}
            MIN=${DEVLINE##*:}
            rm -f /dev/super
            /bin/busybox mknod -m 0660 /dev/super b "$MAJ" "$MIN"
            SUPER_DEV=/dev/super
            log "Found super at $ue ($MAJ:$MIN)"
            break
        fi
    done
    [ -n "$SUPER_DEV" ] && break
    /bin/busybox sleep 1
done

if [ -n "$SUPER_DEV" ]; then
    /bin/busybox losetup -d /dev/loop0 2>/dev/null || true
    /bin/busybox losetup -o 6622253056 /dev/loop0 "$SUPER_DEV"
    if /bin/busybox mount -t ext4 -o rw,noatime /dev/loop0 /newroot; then
        if [ -x /newroot/sbin/linux_init ]; then
            log "Switching root to /newroot/sbin/linux_init"
            /bin/busybox mount --move /proc /newroot/proc
            /bin/busybox mount --move /sys /newroot/sys
            /bin/busybox mount --move /dev /newroot/dev
            exec /bin/busybox switch_root /newroot /sbin/linux_init
        else
            log "ERR: /newroot/sbin/linux_init missing!"
        fi
    else
        log "ERR: mount /dev/loop0 failed!"
    fi
else
    log "ERR: PARTNAME=super not found!"
fi

# Fallback rescue shell over USB RNDIS
for iface in usb0 rndis0; do
    if [ -d "/sys/class/net/$iface" ]; then
        /bin/busybox ip link set "$iface" up
        /bin/busybox ip addr add 192.168.77.1/24 dev "$iface"
        /bin/busybox telnetd -l /bin/sh -p 2323 &
        break
    fi
done
while true; do
    /bin/busybox sleep 30
done
"""


def align(x, p):
    return ((x + p - 1) // p) * p


class CpioBuilder:
    def __init__(self):
        self.buf = bytearray()
        self.ino = 1

    def _entry(self, name, mode, data=b"", nlink=1, rdev_maj=0, rdev_min=0):
        nm = name.encode("utf-8") + b"\x00"
        hdr = (
            "070701"
            + f"{self.ino:08x}"
            + f"{mode:08x}"
            + f"{0:08x}"
            + f"{0:08x}"
            + f"{nlink:08x}"
            + f"{0:08x}"
            + f"{len(data):08x}"
            + f"{0:08x}"
            + f"{0:08x}"
            + f"{rdev_maj:08x}"
            + f"{rdev_min:08x}"
            + f"{len(nm):08x}"
            + f"{0:08x}"
        ).encode("ascii")
        self.ino += 1
        self.buf += hdr + nm
        while len(self.buf) % 4:
            self.buf.append(0)
        self.buf += data
        while len(self.buf) % 4:
            self.buf.append(0)

    def mkdir(self, name, mode=0o755):
        self._entry(name, stat.S_IFDIR | mode, nlink=2)

    def file(self, name, data, mode=0o755):
        self._entry(name, stat.S_IFREG | mode, data=data, nlink=1)

    def symlink(self, name, target):
        self._entry(name, stat.S_IFLNK | 0o777, data=target.encode("utf-8"), nlink=1)

    def dev(self, name, is_block, maj, min_, mode=0o600):
        kind = stat.S_IFBLK if is_block else stat.S_IFCHR
        self._entry(name, kind | mode, nlink=1, rdev_maj=maj, rdev_min=min_)

    def finish(self):
        self._entry("TRAILER!!!", 0, nlink=1)
        while len(self.buf) % 512:
            self.buf.append(0)
        return bytes(self.buf)


def main():
    orig = open(SRC_BOOT, "rb").read()
    ksz, kaddr, rsz, raddr, ssz, saddr, tags, pgsz, hsz, osv = struct.unpack("<10I", orig[8:48])
    hdr_ver = orig[40:44]
    dtb_sz = struct.unpack("<I", orig[1648:1652])[0]
    assert struct.unpack("<I", hdr_ver)[0] == 2

    k_off = pgsz
    kernel = orig[k_off : k_off + ksz]
    r_off = k_off + align(ksz, pgsz)
    dtb_off = r_off + align(rsz, pgsz)
    dtb = orig[dtb_off : dtb_off + dtb_sz]

    bb_data = open(BUSYBOX, "rb").read()

    c = CpioBuilder()
    for d in ["bin", "sbin", "dev", "proc", "sys", "etc", "mnt", "newroot", "run", "tmp"]:
        c.mkdir(d, 0o755)
    c.file("bin/busybox", bb_data, 0o755)
    applets = [
        "sh", "ash", "mount", "umount", "mkdir", "mknod", "mdev", "losetup",
        "switch_root", "sleep", "echo", "cat", "ls", "ln", "chmod", "ip",
        "ifconfig", "telnetd", "udhcpd", "grep", "sed", "awk", "dmesg", "sync",
        "rm", "cp", "uname", "ps", "dirname", "head",
    ]
    for a in applets:
        c.symlink(f"bin/{a}", "busybox")
    c.symlink("sbin/mdev", "/bin/busybox")
    c.symlink("sbin/switch_root", "/bin/busybox")

    c.dev("dev/console", False, 5, 1, 0o600)
    c.dev("dev/null", False, 1, 3, 0o666)
    c.dev("dev/zero", False, 1, 5, 0o666)
    c.dev("dev/tty", False, 5, 0, 0o666)
    c.dev("dev/kmsg", False, 1, 11, 0o600)
    c.dev("dev/urandom", False, 1, 9, 0o666)
    c.dev("dev/loop0", True, 7, 0, 0o660)

    c.file("init", INIT_SCRIPT.replace("\r\n", "\n").encode("utf-8"), 0o755)

    cpio_raw = c.finish()
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", compresslevel=9, mtime=0) as f:
        f.write(cpio_raw)
    ramdisk = gz_buf.getvalue()

    # Build boot image v2 header
    hdr = bytearray(orig[:pgsz])
    struct.pack_into("<I", hdr, 16, len(ramdisk))

    h = hashlib.sha1()
    h.update(kernel)
    h.update(struct.pack("<I", len(kernel)))
    h.update(ramdisk)
    h.update(struct.pack("<I", len(ramdisk)))
    h.update(b"")
    h.update(struct.pack("<I", 0))  # second_size
    h.update(b"")
    h.update(struct.pack("<I", 0))  # recovery_dtbo_size
    h.update(dtb)
    h.update(struct.pack("<I", len(dtb)))
    digest = h.digest() + b"\x00" * 12
    hdr[576:608] = digest

    out = bytearray()
    out += hdr
    out += kernel
    out += b"\x00" * (align(len(kernel), pgsz) - len(kernel))
    out += ramdisk
    out += b"\x00" * (align(len(ramdisk), pgsz) - len(ramdisk))
    out += dtb
    out += b"\x00" * (align(len(dtb), pgsz) - len(dtb))

    open(OUT_BOOT, "wb").write(out)
    print(f"Built {OUT_BOOT}: total={len(out)} B, kernel={len(kernel)}, ramdisk={len(ramdisk)}, dtb={len(dtb)}")


if __name__ == "__main__":
    main()

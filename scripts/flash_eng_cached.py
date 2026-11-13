import sys, usb.core
from mtkclient.Library.partition import Partition
from mtkclient.Library.DA.xflash.xflash_lib import DAXFlash
from mtkclient.Library.Connection.usblib import UsbClass
from mtkclient import mtk as mtk_entry

# 1) Cache GPT per parttype so detect_partition doesn't re-read PGPT 25 times
_orig_get_gpt = Partition.get_gpt
_gpt_cache = {}
def _cached_get_gpt(self, gpt_settings, parttype="user"):
    key = parttype or "user"
    if key in _gpt_cache:
        return _gpt_cache[key]
    res = _orig_get_gpt(self, gpt_settings, parttype)
    if res and res[1] is not None:
        _gpt_cache[key] = res
    return res
Partition.get_gpt = _cached_get_gpt

# 2) Cache get_packet_length once fetched
_orig_get_plen = DAXFlash.get_packet_length
_plen_cache = None
def _cached_get_plen(self):
    global _plen_cache
    if _plen_cache is not None:
        return _plen_cache
    res = _orig_get_plen(self)
    if res is not None:
        _plen_cache = res
    return res
DAXFlash.get_packet_length = _cached_get_plen

# 3) Cap oversized WinUSB read packet size & clear_halt on Pipe error (errno 32)
_orig_usbread = UsbClass.usbread
def _safe_usbread(self, resplen=None, maxtimeout=100, w_max_packet_size=None):
    if w_max_packet_size is not None and self.EP_IN is not None:
        w_max_packet_size = min(w_max_packet_size, max(self.EP_IN.wMaxPacketSize, 4096))
    for attempt in range(3):
        out = _orig_usbread(self, resplen=resplen, maxtimeout=maxtimeout, w_max_packet_size=w_max_packet_size)
        if out or resplen == 0:
            return out
        try:
            if self.device is not None and self.EP_IN is not None:
                self.device.clear_halt(self.EP_IN.bEndpointAddress)
        except Exception:
            pass
    return b""
UsbClass.usbread = _safe_usbread

if __name__ == "__main__":
    sys.exit(mtk_entry.main() or 0)



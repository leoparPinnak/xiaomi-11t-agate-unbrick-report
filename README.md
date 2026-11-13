# Xiaomi 11T (`agate` / MT6893) — Başlangıçtan Kurtuluşa Tam Teknik Rapor

**Cihaz:** Xiaomi 11T (`agate` / `missi`), Model `21081111RG`, Seri `DM6DINSKV8KJSWQS`  
**Çipset:** MediaTek `MT6891Z/MT6893` (Dimensity 1200, `HW code: 0x950`, `HW subcode: 0x8a00`, `HW Ver: 0xca00`)  
**Depolama & RAM:** 128 GB UFS (`SAMSUNG KLUDG4UHDC-B0E1` — `LU0: 4 MB`, `LU1: 4 MB`, `LU2: 128 GB`) + 4 GB / LPDDR4X DRAM (`0x40000000`)  
**Güvenlik Kilidi (BROM):** `SecCFG: SBC + SLA + DAA` (`Target config: 0xe7`, `Mem read/write auth: True`, `Cmd 0xC8 blocked: True`)  
**Tarih Aralığı:** 12 – 13 Kasım 2026  
**Sonuç:** Tamamen ölü / siyah ekran (`Hard-Brick`, sadece BROM) durumundan ücretli yetkili hesap/box olmadan **ekranı ve sistemi geri açıldı**.

---

## 1. Başlangıç Durumu ve Yedekleme (12 Kasım 2026)

İşlemlere başlanmadan önce cihaz çalışır durumdaydı ancak IMEI / ROM tarafında önceki bir müdahalenin izleri vardı:

- **Sistem:** Android 12, MIUI 13 (`V13.0.2.0.SKWMIXM`), ancak `vendor/product/odm` katmanı `amber_global` olarak spoof edilmiş durumdaydı.
- **Bootloader & Root:** Bootloader açıktı (`seccfg` durumu `0x03` = Unlocked, `flash.locked=0`, `verifiedbootstate=orange`). Cihaz `boot_a` üzerinden Magisk 31.1 ile rootluydu.
- **Alınan Tam Yedek (`C:\Users\met\Desktop\telefon-yedek\partisyonlar\` — 709 MB, 11 dosya, SHA-256 doğrulamalı):**
  - Kimlik/kalibrasyon partisyonları: `nvram.img` (64 MB), `nvdata.img` (64 MB), `nvcfg.img` (32 MB), `protect1.img` (8 MB), `protect2.img` (8 MB), `persist.img` (66.5 MB), `proinfo.img` (3 MB), `seccfg.img` (8 MB)
  - Sistem/modem yedekleri: `boot_a.img` (128 MB), `boot_b.img` (128 MB), `md1img_a.img` (200 MB), ayrıca `rev\lk_a.img` (8 MB)
  - Kişisel veriler (`01-rehber-isimler.txt`, `02-rehber-numaralar.txt`, `03-sms.txt`, `04-aramalar.txt`) ve stok `miui_AGATEGlobal_V13.0.2.0.SKWMIXM_8544f90cd4_12.0.zip` (`payload.bin`).

---

## 2. Cihazın BROM'a Düşme (Hard-Brick) Süreci

Ücretsiz IMEI yazımı (`userdebug` + AT komutları) için **Engineering ROM (ENG Firmware)** yüklenmesi hedeflendi:

1. İlk denemelerde ENG ROM parçaları (`agate-r-factory`, Android 11 tabanlı, `ARB=0`) **Fastboot** üzerinden yazılmaya çalışıldı.
2. Daha sonra cihazdan okunan `cur_misc.bin` ve `cur_lk_a.bin` imajları şunu kanıtladı:
   - `lk_a` üzerine ENG ROM'un `lk.img` (`FACTORY_BUILD_LK`, 2021-09-18) dosyası yazılmış,
   - `misc` partisyonunun başına `boot-fastboot` bayrağı yazılmış (`0x800` ofsetinde aktif slot `_a` `BCAB` kaydı kalmış),
   - Ancak `LU0` içindeki Preloader **Android 12 (`agate-s-stable-build-normal`, `20220218-202332`)** iken, `_a` slotundaki kalan firmware/güvenlik parçaları (`tee_a`, `gz_a`, `dpm_a`, `boot_a`, `dtbo_a`) Android 12 stok sürümde kalmış veya uyumsuzlaşmıştı.
3. **Sonuç:** Telefon güç tuşuna, Fastboot'a (`Ses Kısma + Güç`) ve Recovery'ye hiç tepki vermez hale geldi. Ekran tamamen siyah kaldı; USB takıldığında yalnızca MediaTek **BootROM (`USB\VID_0E8D&PID_0003`)** olarak görünüyordu ve MediaTek Watchdog (`WDT 0x10007000`) devrede olduğu için cihaz **5–20 saniye içinde COM portundan düşüyordu**.

---

## 3. Başarısız Olan Denemeler ve Alınan Tüm Hatalar

### 3.1. Windows Üzerinde İlk `mtkclient` ve `UsbDk` / `libusb` Denemeleri (05:14 – 06:17)
- **Ne denendi:** `SURUCU-UsbDk.msi` (`UsbDk_1.0.22_x64`), `SURUCU-libusb-filtre.exe` ve `mtkclient` ile BROM yakalama denendi (`01-usbdk-kur.bat` .. `04-tum-partisyonlar.bat`).
- **Alınan hata (`brom-OK.txt`):**
  `USB enumeration error: Operation not supported or unimplemented on this platform - retrying...`
- **Kök neden:** Windows 11 Build `26100/26200` üzerinde `UsbDk` USB cihaz numaralandırması (enumeration) bozuk çalışıyordu (`mtkclient` kaynak kodu `usblib.py:143` içinde de bu Windows build'i için `USE_USBDK` uyarısı yer alıyordu).

### 3.2. macOS (`192.168.2.190`) Üzerinde `mtkclient` Denemeleri (05:37 – 06:02 & 22:20 – 22:22)
- **Ne denendi:** Sürücü engelini aşmak için SSH üzerinden Mac'teki `mtkclient` (`Python 3.12` + `libusb`) ve `~/authcatch.sh` yakalayıcı betiği çalıştırıldı (`mac1.py` .. `mac32.py`, ardından `authcatch.sh`).
- **Alınan hatalar (`authcatch.log`):**
  - `Preloader - [LIB]: Status: Handshake failed, retrying...`
  - `/dev/cu.usbmodem*` oluşmadı; BROM cihazı kısa süre (`MTK=1`) görünse de handshake başarısız oldu.
  - Ayrıca `authcatch.sh` içindeki `grep -qiE "LUN|GPT|Partition|preloader"` kontrolü `mtk.py`'nin kendi yardım metnindeki `"For preloader mode..."` kelimesiyle eşleştiği için `BAGLANDI 22:22:58` yazıp döngüyü erken sonlandırdı.

### 3.3. SP Flash Tool v5 (`C:\Sp_Flash_Tool_NEW_1107`) Denemeleri (15:56 – 20:10)
- **Alınan hatalar (`SP_FT_Dump_11-13-2026-15-56-56` / `16-08-42` / `17-33-07` / `20-03-16`):**
  - `Load default DA(DA_mt_6765_6768_6785_6873.bin) failed` — Varsayılan DA MT6893 desteklemiyordu.
  - `S_FTHND_FILE_LOAD_FAIL (5008)` — Auth dosyası yüklenemedi.
  - `S_DL_BL_SIG_TYPE_UNSUPPORTED (5078)` ve `S_FTHND_FILE_IS_NOT_LOADED_YET (5007)`.
  - **`STATUS_SEC_AUTH_FILE_NEEDED (0xC0030012)`** (`16:21:36`, `20:09:59`) — BROM üzerinde SBC+SLA+DAA aktif olduğu için auth bypass olmadan SPFT engellendi.
  - **`STATUS_BROM_CMD_STARTCMD_FAIL (0xC0060001)`** (`16:15:51`, `17:12:05`, `17:35:31`, `17:36:23`, `17:38:45`, `20:05:32`, `20:10:34`) — Cihaz 5–20 saniyelik WDT zaman aşımına uğrayıp COM7'den düştüğü veya önceki askıda kalan oturum temizlenmediği için `0xA0` el sıkışması başarısız oldu.

### 3.4. SP Flash Tool V6.2404 ve ENG ROM DA Dosyası Denemeleri (22:15 – 22:36)
- **Alınan hatalar:**
  - `Error: lib DA NOT match!` (`22:15:16`, `22:15:29`, `22:27:08`, `22:29:24`) — ENG ROM içinden çıkan 2021 tarihli 0.8 MB DA (`CL545866`), SPFT V6.2404 kütüphanesi (`CL633342`) ile uyumsuzdu. SPFT'nin kendi 17.7 MB `MTK_AllInOne_DA.bin` dosyası kullanılarak aşıldı.
  - `S_TIMEOUT (1042)` (`22:32:02`, `23:10:57`) — SPFT 120 sn içinde port bulamadan zaman aşımına uğradı.
  - `S_FILEPATH_NOT_SPECIFIED_YET (1017)` (`22:36:20`) — Filtrelenmiş `scatter-flash.txt` imaj klasörünün dışına konduğunda göreceli `.img` yolları çözülemedi (`C:\mtk\images\` içine taşınıp NTFS junction ile çözüldü).
  - `STATUS_ERR (0xC0010001)` (`22:49:17`) ve `STATUS_BROM_CMD_STARTCMD_FAIL` (`22:35:16`, `23:12:56`).

### 3.5. İlk Büyük Aşama (`2nd DA Connected`) ve `32 KB PGPT` Duvarı (22:33 – 23:13)
Batarya konnektörü sökülüp takıldıktan sonra **MTK Auth Bypass Tool V30** ile `Disable Auth` çalıştırıldı:
- **`MTK Auth Disable(SLA/DAA) success!`** alındı (`get_security_config = 00 00 00 00`), canlı preloader (`2026_11_13_17_32_36_preloader_agate.bin`) dump edildi.
- BROM düşmeden 20 saniye içinde SPFT bağlandı → 1st DA (348,392 B) yüklendi → **4 GB DRAM (`0x40000000`) ve 128 GB UFS (`lu0/lu1/lu2`) başlatıldı** → 2nd DA yüklendi → `DA SLA: Disabled` → **`DA Connected`** elde edildi (`22:33:43`).
- **Ancak hemen ardından tüm SPFT sürümlerinde aynı duvara çarpıldı:**
  - `22:49:52` (SPFT V6.2404): `PGPT` ve `SGPT` sonrası 2. `PGPT` (`0x8000` = 32 KB) okumasında dondu → 125 sn sonra **`STATUS_UPLOAD_EXCEPTION (0xC0050004)` / `data_mux receive timeout`**.
  - `23:05:03` (SPFT v5.2228, `StorageLifeCycleCheck=false`): Tam `<-Rx: [ef ee ee fe 01 00 00 00 00 80 00 00]` (32 KB `PGPT` verisi başlangıcı) satırında dondu → **`STATUS_DEVICE_CTRL_EXCEPTION (0xC0050001)`**.
  - `23:13:49` (SPFT v5.2228, Windows **USB Seçmeli Askıya Alma = Kapalı** + **`USBHighSpeed=false`**): Yine santimine kadar aynı `0x8000` `PGPT` okumasında kilitlendi.
- **Kök neden:** Windows 11 26100'deki Microsoft yerleşik **`usbser.sys`** seri sürücüsü, USB 3.0 xHCI portunda 2nd DA'dan gelen 32 KB'lık toplu okuma (bulk-IN) paketlerinde kilitleniyordu.

### 3.6. MediaTek `usb2ser.sys` Sürücü Denemesi ve Bellek Bütünlüğü (HVCI) Engeli
- **Ne denendi:** `MTK-Driver-v5.1632.zip` içinden Microsoft WHQL imzalı `cdc-acm.inf` / `usb2ser.sys` (`3.0.1504.0`, `VID_0E8D&PID_0003/2000/2001`, `IdleEnable=0`) çıkarılıp `SURUCU-KUR.bat` (`pnputil /add-driver ... /install`) ile yüklendi.
- **Alınan hata:** Aygıt Yöneticisi'nde `MediaTek USB Port (COM7)` üzerinde **sarı ünlem (`ProblemCode: 14`)** çıktı.
- **Kök neden (`check_hvci.py` ile doğrulandı):**
  - Bilgisayarda Windows 11 **Bellek Bütünlüğü (`HypervisorEnforcedCodeIntegrity / HVCI = 1`)** açıktı.
  - 2015 tarihli `usb2ser.sys` dosyasının PE başlığında `SectionAlignment = 0x80` ve `INIT` bölümünde `Write + Execute (W=True, X=True)` bayrakları bulunduğu için (`HVCI_SAFE: False`) Windows 11 Bellek Bütünlüğü bu sürücünün yüklenmesine izin vermiyordu.
- `SURUCU-TEMIZLE.bat` ile `oem61.inf` kaldırılıp sarı ünlem temizlendi.

---

## 4. Kesin Çözüm: Adım Adım Nasıl Kurtarıldı?

Sorunu kökten çözen zincir 4 kritik adımdan oluştu:

### Adım 1: `usbser.sys` Yerine HVCI Uyumlu `WinUSB` + `mtkclient V2.1.4`
1. Windows 11 Bellek Bütünlüğü'nü kapatıp PC'yi yeniden başlatmaya gerek kalmadan, Microsoft'un kendi HVCI uyumlu **`winusb.sys`** sürücüsünü kullanmak için imzalı **`zadig-2.9.exe`** (`Akeo Consulting`) indirildi.
2. Zadig üzerinden `USB\VID_0E8D&PID_0003` cihazına **`WinUSB`** sürücüsü kuruldu (`oem61.inf`, `libwdi`). İlk denemede telefon WDT yüzünden düşse bile sürücü Windows Sürücü Deposu'na yerleştiği için sonraki takışta otomatik olarak `WinUSB` bağlandı.
3. **`mtkclient V2.1.4`** (`mtk.exe`) artık ne `MTK Auth Bypass Tool`'a ne de `SP Flash Tool`'a ihtiyaç duydu:
   - `mt6893_payload.bin` (`Kamakiri Run`) ile BROM güvenlik kilidini kendi açtı,
   - `MTK_DA_V5.bin` (Stage 1 + Stage 2) yamalarıyla **`SBC patched to be disabled`** ve **`DA SLA is disabled`** sağladı,
   - `printgpt` komutu ile UFS üzerindeki **77 partisyonun tamamını** başarıyla okudu ve `cur_misc.bin`, `cur_seccfg.bin`, `cur_para.bin`, `cur_lk_a.bin`, `cur_lk_b.bin` incelemelerini yapmamızı sağladı.

### Adım 2: `mtkclient` İçindeki `USBError(32, 'Pipe error')` Bug'ının Yakalanması ve Yamalanması
İlk `mtkclient` yazma denemelerinde iki ayrı hata daha tespit edilip çözüldü:
1. `--parttype boot1` (`LU0`) okuma komutu `storage.py` içindeki UFS LUN boyut/tip eşleştirme hatası nedeniyle `USBError(32, 'Pipe error')` verip sonraki komutları düşürdü → `boot1` okuması kaldırıldı (`MABT` zaten canlı preloader'ı dump ettiği için `LU0`'ın sağlam olduğu biliniyordu).
2. Ardından yalnızca `LU2` (`user`) yazımı başlatıldığında ilk 5 partisyon (`vbmeta_a`, `vbmeta_system_a`, `vbmeta_vendor_a`, `md1img_a`, `spmfw_a`) sorunsuz yazıldı, ancak 6. partisyon `audio_dsp_a`'da yine **`USBError(32, 'Pipe error')` / `USB read failed mid-packet`** hatası geldi.
3. **Kaynak kod incelemesi (`mtk_daloader.py`, `partition.py`, `usblib.py`) ile gerçek sebep bulundu:**
   - `detect_partition()` fonksiyonu **her partisyondan önce** `get_gpt()` çağırıp UFS'ten `32 KB PGPT` tablosunu USB üzerinden yeniden okuyordu.
   - `xflash_lib.py:744` (`w_max_packet_size=remaining`) ve `usblib.py` (`self.fast=False`) Windows `WinUSB` üzerine `32768` baytlık dev okuma isteği gönderince `EP_IN` borusu tıkanıp (`EPIPE`) kesiliyordu.
4. **Çözüm — [`C:\mtk\flash_eng_cached.py`](file:///C:/mtk/flash_eng_cached.py) yaması yazıldı:**
   - `Partition.get_gpt` bellek içi önbelleğe alındı (GPT 25 kez değil, **sadece 1 kez** okundu).
   - `DAXFlash.get_packet_length` önbelleğe alındı.
   - `UsbClass.usbread` için `w_max_packet_size` üst sınırı `4096` bayta indirildi ve `Pipe error` durumunda otomatik `clear_halt(EP_IN)` + yeniden deneme eklendi.
   - Sparse formatlı `super.img` ve `userdata.img` dosyaları [`C:\mtk\simg2img.py`](file:///C:/mtk/simg2img.py) ile RAW formata açılıp trailing sıfırları kırpıldı (`super_2500m.img`, `userdata_100m.img`).
   - Bu yama ile **25 ENG ROM partisyonunun tamamı sıfır hatayla yazıldı** (`md1img_a`, `lk_a`, `boot_a`, `super`, `userdata`, `misc_clean.bin`, vb. + `metadata/frp` format).

### Adım 3: ENG ROM Sonrası Ekranın Açılmama Sebebinin Tespiti (Android 11 vs Android 12)
ENG ROM %100 yazıldığı halde ekran yine açılmadı. Yapılan ikili karşılaştırma kesin sebebi ortaya çıkardı:
- Cihazın `LU0` içindeki Preloader'ı (`2026_11_13_17_32_36_preloader_agate.bin`) **`agate-s-stable-build-normal` (`20220218-202332`, Android 12 / V13.0.2.0.SKWMIXM)** idi.
- ENG ROM ise **`agate-r-factory-build-normal` (`20210918-213456`, Android 11)** sürümüydü.
- Android 12 Preloader, eski tarihli Android 11 ENG `lk_a` / `tee_a` / `gz_a` imajlarını sürüm/anti-rollback uyumsuzluğu nedeniyle başlatmayı reddediyordu.

### Adım 4: Orijinal Stok `V13.0.2.0.SKWMIXM` Yüklemesi ile Cihazın Açılması
1. Kullanıcının isteği üzerine orijinal çalışır stok ROM'a dönüldü.
2. [`C:\mtk\extract_stock.py`](file:///C:/mtk/extract_stock.py) ile `C:\Users\met\Desktop\telefon-yedek\firmware\payload.bin` içinden **MIUI `V13.0.2.0.SKWMIXM` (Android 12)** imajları çıkarıldı (`audio_dsp`, `boot`, `cam_vpu1..3`, `dpm`, `dtbo`, `gz`, `lk`, `mcupm`, `md1img`, `mitee`, `pi_img`, `preloader_raw`, `scp`, `spmfw`, `sspm`, `system_ext`, `tee`, `vbmeta*`).
3. Çıkarılan `preloader_raw.img` ve `lk.img` dosyalarının cihazın orijinal dump'larıyla (`MABT_1732` ve `rev\lk_a.img`) **baytı baytına eşleştiği** doğrulandı.
4. `nvram`, `nvdata`, `nvcfg`, `protect1`, `protect2`, `persist`, `proinfo`, `seccfg`, `otp` ve `LU0` preloader'a **hiç dokunulmadan**, 21 adet orijinal Stok `V13.0.2.0` boot/firmware partisyonu + temizlenmiş `misc_clean.bin` (`boot-fastboot` kilidi kaldırılmış, `_a` slotu korunmuş) [`C:\mtk\run_stock_boot.ps1`](file:///C:/mtk/run_stock_boot.ps1) üzerinden `WinUSB` + `flash_eng_cached.py` ile ~45 saniyede yazıldı (`mtk_stock_live.log`, tümü %100 başarılı + `metadata`/`frp` format).
5. Batarya sök-tak ve güç tuşuna basılmasının ardından **cihazın ekranı ve sistemi geri geldi (`"aha geldi"`).**

---

## 5. Kritik Dosyalar ve Araçlar Özeti

| Dosya / Araç | Görevi |
|---|---|
| `C:\Users\met\Desktop\telefon-yedek\partisyonlar\` | 11 kritik orijinal partisyonun SHA-256 doğrulamalı yedeği (dokunulmadı) |
| `C:\Users\met\Desktop\zadig-2.9.exe` | `USB\VID_0E8D&PID_0003` üzerine HVCI uyumlu `WinUSB` sürücüsü kurdu |
| `C:\mtk\flash_eng_cached.py` | `mtkclient` GPT/paket önbelleği + `Pipe error` `clear_halt` runtime yaması |
| `C:\mtk\simg2img.py` | Android sparse imajları (`super.img`, `userdata.img`) RAW formata çevirdi |
| `C:\mtk\extract_stock.py` | `payload.bin` (`CrAU`) içinden stok `V13.0.2.0.SKWMIXM` partisyonlarını çıkardı |
| `C:\mtk\stock\` & `C:\mtk\run_stock_boot.ps1` | Stok `V13.0.2.0` boot/firmware partisyonlarını ~45 saniyede cihaza yazdı |
| `C:\mtk\platform-tools\fastboot.exe` & `adb.exe` | Açılan cihazda Fastboot/ADB devam adımları için hazırlandı |

---

## 6. Kalan Son Adım (Sistemi Tam Açma)

Boot/firmware (`lk`, `boot`, `dtbo`, `tee`, `md1img`, vb.) stok `V13.0.2.0` ile tamamen kurtarılmış durumda. `super` bölümünde hâlâ bir önceki denemeden kalan ENG `super` bulunduğu için, açılan cihaz USB'ye bağlanıp Fastboot üzerinden stok `system.img`, `vendor.img`, `product.img` ve `system_ext.img` (veya `lpmake` ile paketlenmiş `super_stock.img`) yazıldığında telefon tamamen stok MIUI 13 masaüstüne açılacaktır.

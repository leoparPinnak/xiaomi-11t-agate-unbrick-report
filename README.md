# Xiaomi 11T (`agate` / MT6893) — Başlangıçtan Kurtuluşa Tam Teknik Rapor

**Cihaz:** Xiaomi 11T (`agate` / `missi`), Model `21081111RG`, Seri `DM6DINSKV8KJSWQS`  
**Çipset:** MediaTek `MT6891Z/MT6893` (Dimensity 1200, `HW code: 0x950`, `HW subcode: 0x8a00`, `HW Ver: 0xca00`)  
**Depolama & RAM:** 128 GB UFS (`SAMSUNG KLUDG4UHDC-B0E1` — `LU0: 4 MB`, `LU1: 4 MB`, `LU2: 128 GB`) + 4 GB / LPDDR4X DRAM (`0x40000000`)  
**Güvenlik Kilidi (BROM):** `SecCFG: SBC + SLA + DAA` (`Target config: 0xe7`, `Mem read/write auth: True`, `Cmd 0xC8 blocked: True`)  
**Tarih Aralığı:** 12 – 14 Kasım 2026  
**Sonuç:** Tamamen ölü / siyah ekran (`Hard-Brick`, sadece BROM) durumundan ücretli yetkili hesap/box olmadan kurtarıldı; önce Android 12 `V13.0.2.0.SKWMIXM` ayağa kaldırıldı, ardından ENG ROM + Modem META analizleri tamamlandı, **Android 11 Stok MIUI `V12.5.9.0.RKWMIXM`** BROM üzerinden kuruldu ve `fastboot oem cdms` ile kilitlenen bootloader **Mi Hesabı veya bekleme süresi olmadan BROM'dan yeniden açıldı (`unlocked`)**.

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
5. Batarya sök-tak ve güç tuşuna basılmasının ardından **cihazın ekranı ve Fastboot modu geri geldi (`"aha geldi"`).**

### Adım 5: `fastbootd` Üzerinden Tam Stok `super` Sisteminin Yazılması ve Masaüstüne Açılış (01:45 – 01:51)
1. Bootloader Fastboot bağlantısı doğrulandı (`dm6dinskv8kjswqs fastboot`, `unlocked: yes`, `current-slot: a`, `anti: 2`, `USB\VID_18D1&PID_D00D` + Zadig `WinUSB`).
2. `fastboot reboot fastboot` ile Android 12 stok `boot_a` içindeki userspace **`fastbootd`** moduna geçildi (`is-userspace: yes`, `super-partition-name: super`).
3. Bir önceki ENG ROM denemesinden kalan dinamik partisyon tablosu `fastbootd` üzerinden yeniden boyutlandırıldı (tümü `OKAY`):
   - `system_b → 0`, `odm_a → 0`
   - `system_a → 2,887,729,152 B` (~2.69 GB)
   - `vendor_a → 2,092,617,728 B` (~1.95 GB)
   - `product_a → 1,739,563,008 B` (~1.62 GB)
   - `system_ext_a → 692,473,856 B` (~660 MB)
4. [`C:\mtk\run_fb_stock.ps1`](file:///C:/mtk/run_fb_stock.ps1) betiği ile toplam **7.4 GB** stok MIUI `V13.0.2.0.SKWMIXM` dinamik partisyonları **5.5 dakikada** (`01:45:39` – `01:51:07`) `fastbootd` üzerinden hatasız yazıldı:
   - `system_a` (11/11 parça), `vendor_a` (8/8 parça), `product_a` (7/7 parça), `system_ext_a`
   - *(Not: `product_a` yazımı sırasında `fastbootd` ekranı OLED koruma nedeniyle kendini kararttı; USB bağlantısı kesilmeden arka planda yazma tamamlandı.)*
5. `fastboot erase userdata` + `fastboot erase metadata` + `fastboot reboot` (`01:51:07`) çalıştırıldı.
6. **SonuÃ§:** Cihaz Android/MIUI masaÃ¼stÃ¼ne sorunsuz aÃ§Ä±ldÄ± (`"cihaz geldi"`), Windows tarafÄ±ndan **`Xiaomi 11T` (`USB\VID_2717&PID_FF40`, WPD/MTP)** olarak tanÄ±ndÄ±.

### AdÄ±m 6: Android 11 Stok `V12.5.9.0.RKWMIXM` GeÃ§iÅŸi ve `oem cdms` Kilitlenme OlayÄ± (14 KasÄ±m, 03:52 â€“ 04:03)
1. Ã–nceki stok geri yÃ¼kleme (`restore_full_stock.py`, `03:45 â€“ 03:51`) sonrasÄ±nda cihaz `unlocked: yes` durumunda doÄŸrulandÄ± (`fb_precheck.log`, `03:56:49`).
2. `dl_v1259.py` ile 8 parÃ§alÄ± paralel indirme kullanÄ±larak resmi **Android 11 `agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global`** (`5,909,994,348 B`) indirildi ve Ã§Ä±karÄ±ldÄ±.
3. `flash_v1259.py` ile Fastboot Ã¼zerinden tÃ¼m `V12.5.9.0` imajlarÄ± (`preloader_agate.bin`, `vbmeta*`, `md1img`, `lk`, `boot`, `dtbo`, `tee`, `mitee`, `super`, `rescue`, `cust`, `userdata`) sÄ±fÄ±r hatayla yazdÄ±rÄ±ldÄ± (`03:57:09 â€“ 04:02:48`).
4. **Kritik Olay:** BetiÄŸin son adÄ±mÄ±nda yer alan `fastboot oem cdms` komutu Ã§alÄ±ÅŸtÄ±ÄŸÄ± anda Xiaomi'nin `V12.5.9.0 lk.img` iÃ§indeki MI Lock mekanizmasÄ± tetiklendi ve bootloader kilitlendi (`unlocked: no`, `lks = 1`, `unlock_ability = 0`).

### AdÄ±m 7: ENG ROM Ãœzerinde Modem META (`COM9`) Kurulumu ve NVRAM KalÄ±cÄ±lÄ±k SÄ±nÄ±rÄ±nÄ±n Tespiti (04:07 â€“ 06:05)
1. Android 11 `V12.5.9.0` Preloader (`agate-r-stable-build-normal`, `20211214-102739`) Ã¼zerine Android 11 ENG ROM (`agate-r-factory`, `20210918`) yÃ¼klendiÄŸinde cihaz ilk kez ENG ROM olarak baÅŸarÄ±yla aÃ§Ä±ldÄ± (Ã¶nceki Android 12 Preloader uyumsuzluÄŸu bÃ¶ylece doÄŸrulandÄ±).
2. **Modem META (`v10.2340.0.5`, `META.exe` â†’ `MetaGUI.exe`) baÄŸlantÄ± sorunlarÄ± ve kalÄ±cÄ± Ã§Ã¶zÃ¼mleri:**
   - **Auto Connection 120 sn zaman aÅŸÄ±mÄ±:** `MF_setup.txt` iÃ§indeki `Kernel com port filter`, `VID_0E8D&PID_2029&MI_02` arayÃ¼zÃ¼nÃ¼ iÃ§ermiyordu (yalnÄ±zca `META com port filter` altÄ±nda tanÄ±mlÄ±ydÄ±). **Ã‡Ã¶zÃ¼m:** `More... â†’ Android Test Mode`, `Channel Type: USB` ve `META Channel: COM9` aÃ§Ä±kÃ§a seÃ§ildi.
   - **7 sn sonra `COM9` kopmasÄ± (`LastErrorCode:995 ERROR_OPERATION_ABORTED â†’ 22`) ve 4.07 GB hata gÃ¼nlÃ¼ÄŸÃ¼ (`META_DLL.log`):** Windows `usbser.sys` + **USB SeÃ§meli AskÄ±ya Alma (Selective Suspend)** portun 7 saniyede askÄ±ya alÄ±nmasÄ±na yol aÃ§Ä±yordu. **Ã‡Ã¶zÃ¼m:** `powercfg /SETACVALUEINDEX ... 48e6b7a6-... 0` ve `MSPower_DeviceEnable` kapatÄ±ldÄ±, 4 GB hata logu temizlendi.
   - Bu dÃ¼zeltmeler sonrasÄ±nda ENG modem DB (`C:\mtk\db_eng\md1_mddbmeta` / `md1_mddbmetaodb`) yÃ¼klendi; `Read` (0.26 s), `Write` (0.28 s) ve geri okuma (`isAllSuccess: true`) baÅŸarÄ±yla tamamlandÄ±.
3. **KalÄ±cÄ±lÄ±k Bulgusu:** Yeniden baÅŸlatma sonrasÄ±nda orijinal NVRAM deÄŸerlerinin geri dÃ¶ndÃ¼ÄŸÃ¼ gÃ¶rÃ¼ldÃ¼. Ä°ncelemede:
   - `META_NVRAM_Factory_Backup_r ... is not implemented yet` nedeniyle ATM modundaki yazÄ±mÄ±n yalnÄ±zca modem RAM'ini gÃ¼ncellediÄŸi,
   - `/mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001` (384 B, `NVRAM_EF_IMEI_IMEISV_LID`) dosyasÄ±nÄ±n deÄŸiÅŸmediÄŸi (`mtime: 2021-09-18`) ve `Microtrust teei` + `Soter RPMB` korumasÄ±nÄ±n ATM Ã¼zerinden flash kalÄ±cÄ±lÄ±ÄŸÄ±nÄ± engellediÄŸi doÄŸrulandÄ±.

### AdÄ±m 8: BROM Ãœzerinden Temiz Stok Android 11 `V12.5.9.0.RKWMIXM` Kurulumu (06:20 â€“ 06:50)
1. `mtkclient` iÃ§indeki `writeflash()` fonksiyonunun Android sparse imajlarÄ± aÃ§madan ham kopyaladÄ±ÄŸÄ± (`xflash_lib.py`) dikkate alÄ±narak `V12.5.9.0` sparse imajlarÄ± Python ile RAW'a aÃ§Ä±ldÄ± ve trailing boÅŸ bloklarÄ± kÄ±rpÄ±ldÄ± (`super_raw.img`: `6,622,248,960 B`; `0x1000` ve `0x3000` LP metadata imzalarÄ± doÄŸrulandÄ±).
2. `v1259_multi_cmd.txt` ve `flash_eng_cached.py` ile tek BROM oturumunda 24 partisyon + `super_raw.img` + `userdata/metadata/frp` format sÄ±fÄ±r hatayla yazÄ±ldÄ± (`flash_v1259_brom.log`).
3. Cihaz stok MIUI 12.5 (`RP1A.200720.011`, baseband `MOLY.NR15.R3.TC8.PR2.SP.V1.P78`) masaÃ¼stÃ¼ne sorunsuz aÃ§Ä±ldÄ± (`OEM kilit aÃ§ma = aÃ§Ä±k`).

### AdÄ±m 9: Bootloader Kilit Analizi ve Mi HesabÄ± Olmadan BROM'dan Kilidin AÃ§Ä±lmasÄ±
1. `reunlock_check.py` ile BROM'dan `SecCfgV4` (`AES128-CBC / HACC`) Ã¼zerinden `seccfg lock â†’ unlock` yapÄ±lmasÄ±na raÄŸmen `V12.5.9.0` cihazÄ± `ro.boot.flash.locked = 1` / `lks = 1` bildirmeye devam etti.
2. **`brom_read_lockstate.py` ile BROM TeÅŸhisi:**
   - Mevcut `seccfg` okundu ve 12 KasÄ±m tarihli orijinal **unlocked (`lock_state = 3`)** yedekle **baytÄ± baytÄ±na eÅŸleÅŸtiÄŸi** gÃ¶rÃ¼ldÃ¼.
   - `oem_misc1` (16 MB) tarandÄ± ve yalnÄ±zca `@0x0` ofsetinde 8 baytlÄ±k **`Jz8PNRUF`** (MI Lock magic) kaydÄ± bulundu.
3. **`lk.img` Ä°kili KarÅŸÄ±laÅŸtÄ±rmasÄ± (`V12.5.9.0` vs `V13.0.2.0`):**
   - `V12.5.9.0 lk.img` iÃ§inde `app/mt_boot/miunlock.c` bÃ¶lÃ¼mÃ¼nde `mi_set_magic`, `mi_check_magic`, `mi_get_sig` ve `1st time run MI Lock, write magic Jz8PNRUF` kod yolunun aktif olduÄŸu (temizlense bile yeniden yazabildiÄŸi),
   - Resmi imzalÄ± **`V13.0.2.0 lk.img`** iÃ§inde ise **`Jz8PNRUF` / `mi_get_sig` kontrolÃ¼nÃ¼n tamamen kaldÄ±rÄ±ldÄ±ÄŸÄ±**, Ã¼stelik her iki `lk.img`'nin **birebir aynÄ± Xiaomi X.509 kÃ¶k sertifikalarÄ±yla** (`fb96eeb97cc04e83` / `337dbade8ab04920`) ve aynÄ± `hdr_ver: 2` yapÄ±sÄ±yla imzalandÄ±ÄŸÄ± tespit edildi.
4. **Kesin Ã‡Ã¶zÃ¼m (`brom_unlock_lk13.py`):**
   - BROM'dan `oem_misc1` ilk 64 KB'Ä± sÄ±fÄ±rlandÄ± (geri okuma ile `0` non-zero bayt doÄŸrulandÄ±).
   - `lk_a` partisyonuna resmi Xiaomi imzalÄ± `V13.0.2.0 lk.img` yazÄ±ldÄ±.
   - **SonuÃ§:** Reset sonrasÄ± cihaz Mi HesabÄ± veya 168 saat bekleme sÃ¼resi olmadan **`unlocked`** uyarÄ±sÄ±yla aÃ§Ä±ldÄ± ve MIUI 12.5 baÅŸlatÄ±ldÄ±.

---

## 5. Kritik Dosyalar ve AraÃ§lar Ã–zeti

| Dosya / AraÃ§ | GÃ¶revi |
|---|---|
| `C:\Users\met\Desktop\telefon-yedek\partisyonlar\` | 11 kritik orijinal partisyonun SHA-256 doÄŸrulamalÄ± yedeÄŸi |
| `C:\Users\met\Desktop\zadig-2.9.exe` | `USB\VID_0E8D&PID_0003` ve `VID_18D1&PID_D00D` iÃ§in HVCI uyumlu `WinUSB` kurdu |
| `C:\mtk\flash_eng_cached.py` | `mtkclient` GPT/paket Ã¶nbelleÄŸi + `Pipe error` `clear_halt` runtime yamasÄ± |
| `C:\mtk\simg2img.py` | Android sparse imajlarÄ± (`super.img`, `userdata.img`) RAW formata Ã§evirdi |
| `C:\mtk\extract_stock.py` | `payload.bin` (`CrAU`) iÃ§inden stok `V13.0.2.0.SKWMIXM` partisyonlarÄ±nÄ± Ã§Ä±kardÄ± |
| `C:\mtk\v125\dl_v1259.py` & `flash_v1259.py` | Stok Android 11 `V12.5.9.0.RKWMIXM` paketini indirdi ve Fastboot flash yÃ¶netti |
| `C:\mtk\v125\v1259_multi_cmd.txt` | BROM Ã¼zerinden 24 partisyon + `super_raw.img` (6.62 GB) temiz kurulumunu yaptÄ± |
| `C:\mtk\reunlock_check.py` | `SecCfgV4` (`HACC`) lock/unlock dÃ¶ngÃ¼sÃ¼nÃ¼ BROM'dan test etti |
| `C:\mtk\v125\brom_read_lockstate.py` | `seccfg` ve 16 MB `oem_misc1` iÃ§eriÄŸini okuyup `Jz8PNRUF` bayraklarÄ±nÄ± teÅŸhis etti |
| `C:\mtk\v125\brom_unlock_lk13.py` | `oem_misc1` temizliÄŸi + imzalÄ± `V13.0.2.0 lk.img` ile kilidi BROM'dan aÃ§tÄ± |

---

## 6. Durum Ã–zeti

- **Hard-Brick Kurtarma:** TamamlandÄ± (`V13.0.2.0` ve ardÄ±ndan Android 11 `V12.5.9.0` sÄ±fÄ±r hatayla kuruldu).
- **Bootloader Kilidi:** `oem_misc1` (`Jz8PNRUF`) temizliÄŸi + resmi `V13.0.2.0 lk.img` ile **Mi HesabÄ± olmadan `unlocked` hale getirildi**.
- **Veri & Kimlik GÃ¼venliÄŸi:** `nvram`, `nvdata`, `nvcfg`, `protect1`, `protect2`, `persist`, `proinfo`, `otp` korunmaya devam ediyor; Modem META'nÄ±n ATM modunda TEE/RPMB sÄ±nÄ±rÄ± nedeniyle NVRAM kalÄ±cÄ±lÄ±ÄŸÄ± saÄŸlamadÄ±ÄŸÄ± belgelendi.
- **SÄ±radaki AdÄ±m:** Kilit aÃ§Ä±ldÄ±ÄŸÄ±na gÃ¶re `V12.5.9.0` `boot.img` dosyasÄ±nÄ±n `magisk_patch` ile yamalanÄ±p root (`Magisk`) kurulumunun tamamlanmasÄ±.

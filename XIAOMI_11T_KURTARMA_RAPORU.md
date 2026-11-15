# Xiaomi 11T (`agate` / MT6893) — Başlangıçtan Kurtuluşa Tam Teknik Rapor

**Cihaz:** Xiaomi 11T (`agate` / `missi`), Model `21081111RG`, Seri `DM6DINSKV8KJSWQS`  
**Çipset:** MediaTek `MT6891Z/MT6893` (Dimensity 1200, `HW code: 0x950`, `HW subcode: 0x8a00`, `HW Ver: 0xca00`)  
**Depolama & RAM:** 128 GB UFS (`SAMSUNG KLUDG4UHDC-B0E1` — `LU0: 4 MB`, `LU1: 4 MB`, `LU2: 128 GB`) + 4 GB / LPDDR4X DRAM (`0x40000000`)  
**Güvenlik Kilidi (BROM):** `SecCFG: SBC + SLA + DAA` (`Target config: 0xe7`, `Mem read/write auth: True`, `Cmd 0xC8 blocked: True`)  
**Tarih Aralığı:** 12 – 14 Kasım 2026  
**Sonuç:** Tamamen ölü / siyah ekran (`Hard-Brick`, sadece BROM) durumundan ücretli yetkili hesap/box olmadan kurtarıldı; Android 12 `V13.0.2.0.SKWMIXM` ve Android 11 `V12.5.9.0.RKWMIXM` kuruldu, `oem cdms` ile kilitlenen bootloader BROM'dan yeniden açıldı, **Magisk 31.1 root** kuruldu, ardından Android'siz **Saf Ubuntu 22.04.5 LTS (`aarch64`) Linux sunucusu** (`Wi-Fi` + `USB RNDIS` + `%60–%70 pil şarj koruması` + AMOLED ekran karartma) çalıştırıldı ve **bootloader açık şekilde `V12.5.9.0` / `V13.0.2.0` geri dönüş yedekleri/betikleri** doğrulandı.

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
6. **Sonuç:** Cihaz Android/MIUI masaüstüne sorunsuz açıldı (`"cihaz geldi"`), Windows tarafından **`Xiaomi 11T` (`USB\VID_2717&PID_FF40`, WPD/MTP)** olarak tanındı.

### Adım 6: Android 11 Stok `V12.5.9.0.RKWMIXM` GeçiÅŸi ve `oem cdms` Kilitlenme Olayı (14 Kasım, 03:52 â€“ 04:03)
1. Ã–nceki stok geri yükleme (`restore_full_stock.py`, `03:45 â€“ 03:51`) sonrasında cihaz `unlocked: yes` durumunda doÄŸrulandı (`fb_precheck.log`, `03:56:49`).
2. `dl_v1259.py` ile 8 parçalı paralel indirme kullanılarak resmi **Android 11 `agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global`** (`5,909,994,348 B`) indirildi ve çıkarıldı.
3. `flash_v1259.py` ile Fastboot üzerinden tüm `V12.5.9.0` imajları (`preloader_agate.bin`, `vbmeta*`, `md1img`, `lk`, `boot`, `dtbo`, `tee`, `mitee`, `super`, `rescue`, `cust`, `userdata`) sıfır hatayla yazdırıldı (`03:57:09 â€“ 04:02:48`).
4. **Kritik Olay:** BetiÄŸin son adımında yer alan `fastboot oem cdms` komutu çalÄ±ÅŸtÄ±ÄŸı anda Xiaomi'nin `V12.5.9.0 lk.img` içindeki MI Lock mekanizması tetiklendi ve bootloader kilitlendi (`unlocked: no`, `lks = 1`, `unlock_ability = 0`).

### Adım 7: ENG ROM Ãœzerinde Modem META (`COM9`) Kurulumu ve NVRAM Kalıcılık Sınırının Tespiti (04:07 â€“ 06:05)
1. Android 11 `V12.5.9.0` Preloader (`agate-r-stable-build-normal`, `20211214-102739`) üzerine Android 11 ENG ROM (`agate-r-factory`, `20210918`) yüklendiÄŸinde cihaz ilk kez ENG ROM olarak baÅŸarıyla açıldı (önceki Android 12 Preloader uyumsuzluÄŸu böylece doÄŸrulandı).
2. **Modem META (`v10.2340.0.5`, `META.exe` â†’ `MetaGUI.exe`) baÄŸlantı sorunları ve kalıcı çözümleri:**
   - **Auto Connection 120 sn zaman aÅŸımı:** `MF_setup.txt` içindeki `Kernel com port filter`, `VID_0E8D&PID_2029&MI_02` arayüzünü içermiyordu (yalnızca `META com port filter` altında tanımlıydı). **Ã‡özüm:** `More... â†’ Android Test Mode`, `Channel Type: USB` ve `META Channel: COM9` açıkça seçildi.
   - **7 sn sonra `COM9` kopması (`LastErrorCode:995 ERROR_OPERATION_ABORTED â†’ 22`) ve 4.07 GB hata günlÃ¼ÄŸü (`META_DLL.log`):** Windows `usbser.sys` + **USB Seçmeli Askıya Alma (Selective Suspend)** portun 7 saniyede askıya alınmasına yol açıyordu. **Ã‡özüm:** `powercfg /SETACVALUEINDEX ... 48e6b7a6-... 0` ve `MSPower_DeviceEnable` kapatıldı, 4 GB hata logu temizlendi.
   - Bu düzeltmeler sonrasında ENG modem DB (`C:\mtk\db_eng\md1_mddbmeta` / `md1_mddbmetaodb`) yüklendi; `Read` (0.26 s), `Write` (0.28 s) ve geri okuma (`isAllSuccess: true`) baÅŸarıyla tamamlandı.
3. **Kalıcılık Bulgusu:** Yeniden baÅŸlatma sonrasında orijinal NVRAM deÄŸerlerinin geri döndÃ¼ÄŸü görüldü. İncelemede:
   - `META_NVRAM_Factory_Backup_r ... is not implemented yet` nedeniyle ATM modundaki yazımın yalnızca modem RAM'ini güncellediÄŸi,
   - `/mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001` (384 B, `NVRAM_EF_IMEI_IMEISV_LID`) dosyasının deÄŸiÅŸmediÄŸi (`mtime: 2021-09-18`) ve `Microtrust teei` + `Soter RPMB` korumasının ATM üzerinden flash kalıcılÄ±ÄŸını engellediÄŸi doÄŸrulandı.

### Adım 8: BROM Ãœzerinden Temiz Stok Android 11 `V12.5.9.0.RKWMIXM` Kurulumu (06:20 â€“ 06:50)
1. `mtkclient` içindeki `writeflash()` fonksiyonunun Android sparse imajları açmadan ham kopyaladÄ±ÄŸı (`xflash_lib.py`) dikkate alınarak `V12.5.9.0` sparse imajları Python ile RAW'a açıldı ve trailing boÅŸ blokları kırpıldı (`super_raw.img`: `6,622,248,960 B`; `0x1000` ve `0x3000` LP metadata imzaları doÄŸrulandı).
2. `v1259_multi_cmd.txt` ve `flash_eng_cached.py` ile tek BROM oturumunda 24 partisyon + `super_raw.img` + `userdata/metadata/frp` format sıfır hatayla yazıldı (`flash_v1259_brom.log`).
3. Cihaz stok MIUI 12.5 (`RP1A.200720.011`, baseband `MOLY.NR15.R3.TC8.PR2.SP.V1.P78`) masaüstüne sorunsuz açıldı (`OEM kilit açma = açık`).

### Adım 9: Bootloader Kilit Analizi ve Mi Hesabı Olmadan BROM'dan Kilidin Açılması
1. `reunlock_check.py` ile BROM'dan `SecCfgV4` (`AES128-CBC / HACC`) üzerinden `seccfg lock â†’ unlock` yapılmasına raÄŸmen `V12.5.9.0` cihazı `ro.boot.flash.locked = 1` / `lks = 1` bildirmeye devam etti.
2. **`brom_read_lockstate.py` ile BROM TeÅŸhisi:**
   - Mevcut `seccfg` okundu ve 12 Kasım tarihli orijinal **unlocked (`lock_state = 3`)** yedekle **baytı baytına eÅŸleÅŸtiÄŸi** görüldü.
   - `oem_misc1` (16 MB) tarandı ve yalnızca `@0x0` ofsetinde 8 baytlık **`Jz8PNRUF`** (MI Lock magic) kaydı bulundu.
3. **`lk.img` İkili KarÅŸılaÅŸtırması (`V12.5.9.0` vs `V13.0.2.0`):**
   - `V12.5.9.0 lk.img` içinde `app/mt_boot/miunlock.c` bölümünde `mi_set_magic`, `mi_check_magic`, `mi_get_sig` ve `1st time run MI Lock, write magic Jz8PNRUF` kod yolunun aktif olduÄŸu (temizlense bile yeniden yazabildiÄŸi),
   - Resmi imzalı **`V13.0.2.0 lk.img`** içinde ise **`Jz8PNRUF` / `mi_get_sig` kontrolünün tamamen kaldırıldÄ±ÄŸı**, üstelik her iki `lk.img`'nin **birebir aynı Xiaomi X.509 kök sertifikalarıyla** (`fb96eeb97cc04e83` / `337dbade8ab04920`) ve aynı `hdr_ver: 2` yapısıyla imzalandÄ±ÄŸı tespit edildi.
4. **Kesin Ã‡özüm (`brom_unlock_lk13.py`):**
   - BROM'dan `oem_misc1` ilk 64 KB'ı sıfırlandı (geri okuma ile `0` non-zero bayt doÄŸrulandı).
   - `lk_a` partisyonuna resmi Xiaomi imzalı `V13.0.2.0 lk.img` yazıldı.
   - **Sonuç:** Reset sonrası cihaz Mi Hesabı veya 168 saat bekleme süresi olmadan **`unlocked`** uyarısıyla açıldı ve MIUI 12.5 baÅŸlatıldı.

### Adım 10: Magisk 31.1 Root, Ubuntu 22.04 Chroot ve %60–%70 Pil Koruması (14 Kasım)
1. **Magisk 31.1 Kurulumu ve `boot_patch.sh` Düzeltmesi:**
   - `V12.5.9.0` stok `boot.img` (`KEEPVERITY=true`, `KEEPFORCEENCRYPT=true`, `PREINITDEVICE=metadata`) cihaz üzerinde `magiskboot` + `boot_patch.sh` ile yamalanırken, kaynak dosya adının `stock_boot.img` verilmesinin `boot_patch.sh` içindeki `cat $BOOTIMAGE > stock_boot.img` satırı yüzünden dosyayı 0 bayta düşürüp `mmap EINVAL` hatası verdiği tespit edildi → kaynak dosya `orig_boot.img` olarak adlandırılıp `magisk_patched_v1259_boot.img` üretildi.
   - `fastboot flash boot_a` sonrası `/debug_ramdisk/magisk -v` (`31.1:MAGISK:D`) doğrulandı ve `Magisk.apk` kurularak `uid=0` aktif edildi.
2. **Ubuntu 22.04.5 LTS ARM64 Kurulumu (`setup_ubuntu.sh`):**
   - `/proc/config.gz` incelendi (`Linux 4.14.186`, `CONFIG_NAMESPACES=y`, `CONFIG_CGROUPS=y`, `CONFIG_OVERLAY_FS=y`, `CONFIG_USB_RTL8152=y`, `CONFIG_USB_CONFIGFS_RNDIS=y`; yalnızca `USER_NS`, `SYSVIPC`, `DEVTMPFS` kapalı).
   - Android `/data` (`f2fs`) `nosuid,nodev` bayraklarıyla bağlı olduğu için 32 GB sparse `ext4` loop imajı (`/data/ubuntu.img`) oluşturuldu.
   - Loop mount sırasında SELinux `avc: denied { read } scontext=u:r:kernel:s0 tcontext=u:object_r:system_data_root_file:s0` hatası `magiskpolicy --live "allow kernel system_data_root_file file { read write getattr open }"` ile aşıldı.
   - `ubuntu-base-22.04.5-base-arm64.tar.gz` çıkarıldı; Android `CONFIG_ANDROID_PARANOID_NETWORK` nedeniyle `aid_inet (3003)`, `aid_net_raw (3004)`, `aid_net_admin (3005)` grupları ve `APT::Sandbox::User "root"` ayarlandı, `openssh-server` (`Port 2222`), `sudo`, `python3`, `git`, `wpasupplicant`, `isc-dhcp-client`, `busybox-static` kuruldu.
3. **7/24 Pil Koruma Sistemi (`charge-limit.sh`):**
   - Kernel sysfs üzerinden `/sys/class/power_supply/battery/input_suspend` doğrulandı (`1` yazıldığında `Discharging`, `0` yazıldığında `Charging`).
   - Pil `>= %70` veya sıcaklık `>= 42.0 °C` olduğunda şarjı donanım seviyesinde kesen, `<= %60` olduğunda yeniden açan arka plan servisi (`charge-limit.sh`) + Ubuntu içi izleme komutu (`batstat`) eklendi.

### Adım 11: Android'siz Saf Ubuntu 22.04 Boot, USB RNDIS ve MediaTek Wi-Fi (`conninfra`/`bt_drv`) (14 Kasım)
1. **Şifresiz Ubuntu Root Bölümü (`super` Boş Alanı — Sıfır Veri Kaybı):**
   - `lpdump /dev/block/by-name/super` analizinde `super` (9.13 GB) içinde aktif partisyonların `12,934,080` sektörde bittiği ve **`6,622,253,056` ofsetinden itibaren `2.33 GiB` (~2.50 GB) boş alan** bulunduğu tespit edildi.
   - Android `userdata` (`106 GB`) ve `system_a/vendor_a` bölümlerine hiç dokunulmadan bu boş alan `ext4` (`ubuntu_native`) olarak formatlandı (`magiskpolicy` `super_block_device` izniyle) ve Ubuntu rootfs buraya taşındı.
2. **Saf Linux `initramfs` (`build_native_boot.py` → `ubuntu_native_boot.img`):**
   - Stok `V12.5.9.0` `kernel` + `dtb` korunarak özel statik `busybox` tabanlı `initramfs` (`/init`) paketlendi.
   - Stok kernelde `CONFIG_DEVTMPFS` kapalı olduğu için `/init` aşamasında `tmpfs` `/dev`, temel cihaz düğümleri, `busybox mdev -s` ve `/sys/class/block/*/uevent` üzerinden dinamik `PARTNAME=super` tespiti eklendi.
   - `configfs` üzerinden **`USB RNDIS` (`0x2717:0xFF80`, `rndis.gs4` → `musb-hdrc`, `192.168.77.1/24` + `udhcpd`)** açıldı, ardından `losetup -o 6622253056` + `switch_root /newroot /sbin/linux_init` ile doğrudan saf Ubuntu PID 1 olarak başlatıldı.
   - *(Not: MTK `lk.img` `fastboot boot` RAM boot'u desteklemediği için `lk_crash` ile geri dönmüş, imaj `fastboot flash boot_a` ile yazıldığında tek seferde açılmıştır.)*
3. **Android Olmadan MediaTek Wi-Fi (`wlan0`) Aşamalarının Çözülmesi:**
   - `/vendor/lib/modules/*.ko`, `/vendor/firmware/*`, `/mnt/vendor/nvdata/APCFG/APRDEB/*` ve minimal Bionic runtime (`linker64` + 8 temel `.so`, `conninfra_loader`, `wlan_assistant`) rootfs içine alındı.
   - İlk açılışta `CONFIG_DEVTMPFS` kapalı olduğundan `insmod` sonrası `/dev/conninfra_dev` ve `/dev/wmtWifi` düğümlerinin oluşmadığı ve `conninfra_core_pre_cal_blocking` kilidinin `bt_drv.ko` yüklenene kadar beklediği tespit edildi.
   - **Çözüm (`linux_init`):** `conninfra.ko` → `mdev -s` → `conninfra_loader` → `bt_drv.ko` → `wmt_chrdev_wifi.ko` → `wlan_drv_gen4m.ko` → `mdev -s` → `chmod 666 /dev/null ...` → `wlan_assistant &` → `echo 1 > /dev/wmtWifi` → `wpa_supplicant` + `dhclient wlan0` sırasıyla Wi-Fi saf Linux üzerinde sıfır hatayla **`wlan0` (`192.168.2.212`)** olarak ayağa kalktı.
4. **AMOLED Ekran Karartma & Sistem İzinleri:**
   - Açılışta bootloader Mi logosu framebuffer'da kaldığı için `/sbin/linux_init` başına `/sys/class/leds/lcd-backlight/brightness = 0`, `/sys/class/graphics/fb0/blank = 1` ve `/dev/fb0` sıfırlaması eklendi; sistem boşta **~6.96 GB boş RAM** ile sorunsuz çalışıyor.

### Adım 12: Bootloader Açık Kalacak Şekilde Tam Geri Dönüş Yedeklemesi ve Güvencesi
- `userdata` veya `super` formatlansa dahi bootloader kilit durumu (`seccfg` = `0x03`, `oem_misc1` = temiz, `lk_a` = imzalı `V13.0.2.0 lk.img`) etkilenmez; canlı sistemden `/dev/sda` (`LU0 preloader`, 4 MB, SHA-256 doğrulamalı) dahil eksik kalan kurtarma imajları yerel yedek klasörüne (`C:\Users\met\Desktop\telefon-yedek\geri-donus\`) tamamlandı.
- **`fastboot oem cdms` komutu içermeyen** iki geri dönüş betiği hazırlandı:
  - [`geri_donus_v1259_fastboot.ps1`](scripts/geri_donus_v1259_fastboot.ps1): Bootloader kilidini açan `lk_a_v13_unlocked.img` korunarak 3 saniyede Android 11 `V12.5.9.0` (+ Magisk) veya `-FullRestore` ile sıfırdan tam `V12.5.9.0` kurar.
  - [`geri_donus_v1302_fastboot.ps1`](scripts/geri_donus_v1302_fastboot.ps1): Bootloader açık şekilde Android 12 `V13.0.2.0.SKWMIXM` (+ isteğe bağlı `-WithMagisk`) kurar.
- *(Not: Cihaza özel `nvram`, `nvdata`, `proinfo`, `seccfg`, `persist`, `protect1/2`, `otp` imajları hem dosya boyutu hem de gizlilik/IMEI güvenliği nedeniyle herkese açık GitHub reposuna konmamış, yerel `telefon-yedek\partisyonlar\` ve `geri-donus\` klasörlerinde `SHA256SUMS.txt` ile korunmuştur.)*

### Adım 13: Telefon Ekranı Telemetri Arayüzü, Canlı SSH Aynalama, ARM64 Chromium 156 ve Video Akış Prototipi (14 Kasım)
1. **Framebuffer Canlı Dashboard & Terminal (`scripts/fbui.py` & `scripts/ekran.sh`):**
   - Stok `4.14.186` çekirdek `CONFIG_VT` içermediği için doğrudan `/dev/fb0` (`1080×2400`, `stride=4352`, 32-bit RGBA) üzerine `python3-pil` + `DejaVuSansMono.ttf` ile özel bir konsol arayüzü yazıldı.
   - **Canlı Telemetri Kartı:** CPU yükü (%) + 3 küme frekansları (`cpu0/cpu4/cpu7`), GPU kullanımı (`/sys/kernel/ged/hal/gpu_utilization`, Mali güç durumu), RAM kullanımı, anlık güç tüketimi (**Watt**, **mA**, **Voltaj**), batarya yüzdesi + şarj kesme durumu ve 5 gerçek termal sensör (`mtktscpu`, `mtktsAP`, `mtktspmic`, `mtktswmt`, `battery`) anlık çizilir.
   - **Fiziksel Tuş Kontrolü (`/dev/input/event1` `mtk-kpd`):** Güç tuşuna (`KEY_POWER = 116`) her basışta ekran açılıp kapatılır; Ses+/Ses- kapalı ekranı uyandırır. SSH üzerinden `ekran ac|kapat|toggle|durum|baglan|cmd` komutları eklendi.
   - **Canlı SSH ↔ Telefon Ekranı Aynalama:** `python3-pyte` VT100/ANSI emülatörü + `tmux -S /tmp/fbconsole.sock` (`66×50`) bağlandı ve `/home/ubuntu/.bashrc` içine etkileşimli SSH otomatik bağlantısı eklendi (`ssh -p 2222 ubuntu@192.168.2.212` doğrudan telefon ekranındaki `tmux` oturumuna düşer; `Ctrl+B D` ile ayrılınır).
   - **İzin Düzeltmesi:** `busybox mdev -s` sonrasında `/dev/null`, `/dev/zero`, `/dev/urandom`, `/dev/tty`, `/dev/ptmx` izinlerinin `0666` yapılması `/sbin/linux_init` sonuna sabitlendi.
2. **Snap'siz Native ARM64 Chromium 156 ve Video Akışı (`scripts/chrome_stream_server.py`):**
   - Ubuntu `snapd` `systemd`'siz ortamda çalışmadığı için `ppa:xtradeb/apps` (Jammy `arm64`) deposundan native `.deb` **`Chromium 156.0.8078.73`** kuruldu (`--headless --no-sandbox --disable-gpu --dump-dom` doğrulandı, diskte `1.3 GB` boş alan korundu).
   - `python3-aiohttp` ile `/opt/chrome_stream/server.py` geliştirildi: Chromium CDP `Page.startScreencast` üzerinden `1280×720` kareleri yakalayıp `:8080/` (etkileşimli uzaktan kontrol), `:8080/stream.mjpg` (ham MJPEG akışı) ve `:8080/frame.jpg` olarak sundu (kablosuz Wi-Fi'den canlı görüntülendi).
   - Gün sonu soğutma ve ertesi günkü özel yazılım geliştirme çalışması öncesinde `chrome_stream` süreci durduruldu (kod `/opt/chrome_stream/server.py` ve repoda hazır bekler).

### Adım 14: Mali-G77 MC9 Donanım GPU'sunun Saf Ubuntu `glibc` ve Chromium 156'da Çalıştırılması
1. **Android `vendor_a` ve `system_a` Salt-Okunur Bağlantısı (Sıfır Ek Disk):**
   - `super` (`/dev/sdc62`) içindeki `vendor_a` (`offset 1931476992` → `/mnt/avendor`) ve `system_a` (`offset 3399483392` → `/mnt/asystem`) salt-okunur bağlandı; `/system/vendor -> /mnt/avendor` bağlantısı ve `/sbin/linux_init` açılış kalıcılığı eklendi.
   - `/mnt/avendor/lib64/egl/libGLES_mali.so` (`r25p0-00cet2`, 37.95 MB) kütüphanesinin 62 geçişli `.so` bağımlılığının tamamının (`0` eksik) mevcut olduğu doğrulandı.
2. **`libhybris` Derlemesi ve 5 Kritik Android 11 / MediaTek Uyum Yaması (`scripts/libhybris_mali_agate.patch`):**
   - `Halium/android-headers` (`halium-11.0`) ile `libhybris` (`--enable-arch=arm64 --enable-mali-quirks --enable-wayland`) `/usr/local/hybris` altına derlendi; çıkan engeller tek tek teşhis edilip çözüldü:
     1. **`__ctype_get_mb_cur_max` TLS Çökmesi (`SEGV at 0x820`):** Android 11 Bionic `libc.so` `TLS_SLOT_BIONIC_TLS` (`[tpidr_el0 - 8]`) okuması `glibc` TCB'sinde NULL olduğu için `hooks.c` içine `HOOK_DIRECT(__ctype_get_mb_cur_max)` eklendi → `libGLES_mali.so` yüklendi ve `test_opencl` **`Mali-G77 MC9 r0p1` (`OpenCL Success!`)** verdi.
     2. **`soter_open` TEE Kilitlenmesi:** `eglGetDisplay` sırasında `libGLES_mali.so`'nun `/dev/ion` üzerinde güvenli heap denemesi (`heap_id_mask=0x2000`) `ion_sec_heap_allocate -> soter_open` üzerinden TEE daemon bekleyip takılıyordu. `libion.so` `__open_2@LIBC` kullandığı tespit edilerek `hooks.c` içine `__open_2` + `ioctl` hooku eklendi ve güvenli heap `ENODEV` ile atlandı → saf Pbuffer üzerinde **`GL_RENDERER: Mali-G77 MC9` (`OpenGL ES 3.2`)** çalıştı ve `glReadPixels` ile GPU çizimi doğrulandı.
     3. **`gralloc` Stack-Guard Çakışması:** Headless `null` ve `wayland` platform başlatıcılarındaki gereksiz `hybris_gralloc_initialize(0)` kaldırıldı.
     4. **Chromium ANGLE `DisplayEGL` Eksik Çekirdek EGL Girişleri:** ANGLE bütün core EGL fonksiyonlarını (`eglBindAPI`, `eglChooseConfig`, `eglCreatePbufferSurface`, `eglMakeCurrent`, `eglQueryString` vb.) `eglGetProcAddress` üzerinden istediği için `egl.c` `_eglHybrisOverrideFunctions[]` tablosuna tüm core EGL fonksiyonları, `EGL_PLATFORM_SURFACELESS_MESA`/`DEVICE_EXT` desteği ve `eglQueryDevicesEXT` eklendi.
     5. **GLESv1/v2 Varsayılanı:** `egl.c` içindeki `_egl_context_client_version` başlangıç değeri `2` yapılarak Chromium GPU prosesi `SIGSEGV` (`exit_code=11`) tamamen giderildi.
3. **Doğrulanan Sonuçlar:**
   - **Weston Headless (`--backend=headless-backend.so`) + `libhybris` + Chromium 156 (`scripts/chrome-gpu.sh` & `scripts/chrome_stream_server.py`):**
   - WebGL 2.0 `UNMASKED_RENDERER_WEBGL`: **`ANGLE (ARM, Mali-G77 MC9, OpenGL ES 3.2)`**
   - `/dev/mali0`, `/dev/ion`, `/dev/video*`, `/dev/dri/card0` izinleri `0666` olarak `/sbin/linux_init` içine sabitlendi.

### Adım 15: Çift Donanım JPEG Kodlayıcı (`/dev/video3` & `/dev/video4`), `/dev/video2` Tespiti ve Şarj Eşiği Güncellemesi
1. **Çift Donanım JPEG Motorunun Açılması (`scripts/hwjpeg_v4l2.c` → `/usr/local/lib/libhwjpeg.so`):**
   - `mtk-jpeg-enc` (`/dev/video3` ve `/dev/video4`) düğümlerinin `V4L2_MEMORY_MMAP` bellek ayırmasında `vb2_dc_alloc` hatası verdiği, `V4L2_MEMORY_DMABUF` (`mem=4`) beklediği tespit edildi.
   - `/dev/ion` üzerinde System heap (`0x1`) parçalama hatası (`contiguous chunk is too small`) verirken, MediaTek Multimedia IOMMU heap'i **`heap_id_mask = 0x400`** ile alınan DMA-BUF'ların her iki motorla da kusursuz çalıştığı doğrulandı.
   - **Ölçülen Hız (`1280×720`):**
     - `YUYV → HW JPEG`: `/dev/video3` **141.5 FPS (`7.07 ms/kare`)** + `/dev/video4` **140.0 FPS (`7.14 ms/kare`)** (toplam **~281 FPS** donanım JPEG).
     - Python `ctypes` üzerinden `RGBA → HW JPEG` (`libhwjpeg.so`): **117.5 FPS (`8.51 ms/kare`)** (`PIL.Image.verify()` doğrulamalı geçerli JFIF JPEG).
2. **H.264 VENC (`/dev/video2`) Bulgusu:**
   - `/dev/video2` (`17020000.venc`) `encoder capability 0` döndü (kullanıcı alanı `/vendor/bin/vpud` VCU servisine bağlı). Çift donanım JPEG motoru (`/dev/video3` + `/dev/video4`) doğrudan çalıştığı için ek VCU daemonu gerektirmeden 10 Chrome akışı için yeterlidir.
3. **Şarj Eşiği Histerezisi Güncellemesi (`scripts/charge-limit.sh`):**
   - Önceki `%60` alt eşiği yüzünden pil `%62–%64` aralığındayken `input_suspend = 1` kalarak şarj başlamıyordu; alt eşik **`<= %67`** (üst eşik **`>= %70`**) olarak güncellendi ve `input_suspend = 0` sıfırlandı.

### Adım 16: Weston Donanım JPEG Modülü (`weston_hwjpeg.so`), Sıfır CPU Screencast & Gelişmiş Web Konsolu (`:8080`)
1. **CPU `Page.startScreencast` Darboğazının Tamamen Kaldırılması (`scripts/weston_hwjpeg.c` → `/usr/local/lib/weston_hwjpeg.so`):**
   - Chromium'un `Page.startScreencast` komutu kareleri GPU'dan okuyup CPU'da JPEG/PNG sıkıştırdığı için 1080p ve çoklu sekmede yüksek CPU ve düşük FPS üretiyordu.
   - `libweston-9-dev` ile özel **Weston C eklentisi (`weston_hwjpeg.so`)** yazıldı:
     - `weston --backend=headless-backend.so --use-pixman --shell=kiosk-shell.so` içinde her yeni karede (`output->frame_signal`) piksel verisini doğrudan çift tampona alır.
     - Worker thread **ARM64 NEON SIMD (`vld4_u8`)** ile `BGRA → YUYV` renk dönüşümü yapıp MediaTek **ION `0x400` DMA-BUF** üzerinden **`/dev/video3` (`mtk-jpeg-enc`)** donanım JPEG motoruna verir.
     - Çıkan ham JPEG karelerini `/tmp/weston_hwjpeg.sock` Unix soketinden doğrudan Python sunucusuna aktarır (`Page.startScreencast` ve base64 tamamen devre dışı).
   - **Ölçülen Canlı Sonuçlar (`WebGL Aquarium`, Mali-G77 `886 MHz`):**
     - `1280×720` HW-JPEG: **36.4 FPS** (Weston CPU `%14.7`)
     - `1920×1080` HW-JPEG (1 sekme): **28.8 FPS** (`~14.7 MB/s`)
     - `1920×1080` HW-JPEG (**6 sekme eşzamanlı açıkken**, arka plan throttle aktif): **23.4 FPS** (`%33.3` toplam CPU, `66.3°C`)
2. **Profesyonel Web Tarayıcı Konsolu (`scripts/chrome_stream_server.py`, `:8080`):**
   - Modern koyu arayüz, gerçek Chromium çoklu sekme yönetimi (`+` yeni sekme, sekme geçişi, `×` kapatma), adres/arama çubuğu, yer imleri, canlı Stream FPS & KB/s göstergesi.
   - Encode modu / kalite seçici: **`HW-JPEG 1080p (/dev/video3)`** (varsayılan), **`Native 1080p (Kayıpsız PNG)`**, **`2K QHD 1440p`** ve **`4K UHD 2160p (Kayıpsız PNG)`**.
   - Tek tıkla **`GPU: MAX 886MHz` / `AUTO`** (`scripts/gpu-perf.sh`) anahtarı ve alt kısımda 6 kartlı canlı telefon telemetrisi (CPU, GPU/VRAM, RAM, 5 sıcaklık, Batarya/Güç/Şarj Limiti, Akış).

### Adım 17: Telefon Ekranına Dokunmatik XFCE4 Masaüstü ve Chromium Basılması (`ekran xfce`)
1. **Dokunmatik Ekran Sürücülerinin Yüklenmesi (`/dev/input/event4`):**
   - `/mnt/avendor/lib/modules/` içindeki **`xiaomi_touch.ko`** ve **`fts_touch_spi.ko`** çekirdek modülleri yüklenerek FocalTech dokunmatik ekran (`/dev/input/event4`, `fts`, `0..10799 × 0..23999` çözünürlük) aktifleştirildi ve `/sbin/linux_init` açılışına kalıcı eklendi.
2. **Minimal XFCE4 & Xvfb → `/dev/fb0` Köprüsü (`scripts/fb_xfce_bridge.c`):**
   - `--no-install-recommends` ile minimal **XFCE4** (`xfwm4`, `xfce4-panel`, `xfce4-session`, `xfdesktop4`, `xfce4-terminal`, `thunar`, `Xvfb`) kuruldu (`~44 MB`, `/` diskte `447 MB` boş).
   - MediaTek `/dev/fb0` `FBIOPAN_DISPLAY` ve `stride=4352` (`1088` genişlik) gerektirdiği için **`fb_xfce_bridge.c`** (`/usr/local/sbin/fb_xfce_bridge`) yazıldı:
     - `Xvfb :0` (`1080×2400`) bellek tamponunu (`BGRX → RGBA`) değişen satırlarda 30 FPS olarak `/dev/fb0`'a basar.
     - `/dev/input/event4` dokunmatik olaylarını `libXtst` (`XTestFakeMotionEvent` / `XTestFakeButtonEvent`) ile doğrudan X11 tıklama/sürüklemeye çevirir.
     - `/dev/input/event1` (`KEY_POWER`) ve `/run/fbui.ctl` FIFO ile ekran ışığı açma/kapatma özelliğini korur.
3. **Çift Modlu Ekran Kontrolü (`scripts/ekran.sh`, `scripts/start_xfce_fb.sh`):**
   - `sudo ekran xfce`: XFCE4 masaüstünü ve üzerinde dokunmatik **Chromium** penceresini telefon ekranına (`1080×2400`) basar (masaüstünde `Chromium Web` kısayolu hazır).
   - `sudo ekran terminal`: Eski hafif telemetri + `tmux` terminal dashboard'una (`fbui.py`) geri döner.
   - `sudo ekran ac | kapat | toggle`: Güç tuşuyla aynı şekilde ekranı açar/kapatır.

### Adım 18: XFCE4 Masaüstünün `/dev/video4` Donanım JPEG ile Canlı Tarayıcıya Basılması (`:8090`)
1. **DRM & Zero-Copy Donanım Keşfi (`/dev/dri/card0`):**
   - `libdrm` probu ile `CRTC[0]` (`fb=99`, `1088×7200`, `pitch=4352`) ve `drmPrimeHandleToFD` üzerinden DMA-BUF `fd` alındığı doğrulandı; ancak MediaTek `4.14` çekirdeğinde boot framebuffer GEM `mmap` (`ENODEV`), Mali `eglCreateImageKHR(EGL_LINUX_DMA_BUF_EXT)` import (`(nil)`) ve `DRM_CLIENT_CAP_WRITEBACK_CONNECTORS` (`-1`) desteklenmediği için doğrudan `Xvfb_screen0` (`2400×1080`) + ikinci donanım motoru `/dev/video4` seçildi.
2. **Çift Donanım Motorlu Eşzamanlı Yayın (`scripts/fb_xfce_bridge.c` + `scripts/xfce_stream_server.py`):**
   - `fb_xfce_bridge` içine **ARM64 NEON SIMD (`bgrx_to_yuyv_neon`)** + **ION `0x400` DMA-BUF** + **`/dev/video4` (`mtk-jpeg-enc`)** encoder thread eklendi; `/tmp/xfce_hwjpeg.sock` üzerinden ham JPEG karelerini yayınlar.
   - `http://192.168.2.212:8090/` arayüzü (`xfce_stream_server.py`) tarayıcıdan **tıklama, sağ tık, sürükleme, kaydırma, klavye, yatay/dikey döndürme ve ekran ışığı aç/kapat** kontrolü sağlar (`libX11` + `libXtst`).
   - `:8080` (`/dev/video3` Mali GPU WebGL/Chromium konsolu) ile `:8090` (`/dev/video4` XFCE masaüstü yayını) arasında üst çubuktaki butonlarla tek tıkla geçiş yapılabilir.
3. **Canlı İmleç, Tutup Sürükleme, Türkçe Klavye ve `asyncio` Görev Koruması:**
   - `fb_xfce_bridge.c` içine **`libXfixes` (`XFixesGetCursorImage`)** entegre edilerek X11 fare imleci hem telefon ekranına hem `:8090` yayınına canlı çizildi.
   - `:8090` ve `:8080` üzerine `draggable="false"` + `pointerdown/pointermove/pointerup` + `setPointerCapture` ile gerçek tutup sürükleme; `:8090` içine `/ws/input` WebSocket kanalı, `Ctrl+A/C/V/X/Z/T/W` / `Alt+Tab` kısayol barı ve çakışmasız boş keycode slotları (`154..197`) ile tam Türkçe karakter (`ç ğ ı İ ö ş ü`) desteği eklendi.
   - Python 3.10 Garbage Collector'ın referanssız `asyncio.create_task` soket okuyucularını iptal ederek `FPS: 0` üretmesi (`Task was destroyed but it is pending`) her iki sunucuda `_spawn()` referans setiyle kalıcı çözüldü.

### Adım 19: Sıfır-Aracı Saf UDP (`:9900`), 4K UHD (`3840×2160`) Karo Motoru ve PySide6 İstemcisi
1. **Doğrudan C Çekirdeğinden Saf UDP Yayın (`scripts/fb_xfce_bridge.c`):**
   - Tüm TCP yayın sunucuları (`:8080`, `:8090`, `:9222`) durduruldu; görüntü ve girdi tamamen **`UDP :9900`** üzerinden taşınır.
   - `AGTH` (Hello/keepalive) → `AGTS` (`width×height`), `AGTI` ikili girdi protokolüyle fare hareket/tıklama/sürükleme/tekerlek, kısayollar (`Ctrl/Alt/Shift`), Türkçe UTF-8 ve uygulama/çözünürlük komutları (`XInitThreads()` korumalı) doğrudan C'den X11'e basılır.
2. **4K (`3840×2160`) 2×2 Karo (`AGTT`) Motoru + Telefon Ekranı Dondurma:**
   - Donanım testinde `17030000.jpgenc` (`/dev/video3`) 4K'da hata verirken `17830000.jpgenc` (`/dev/video4`) tek parça 16.5 MB çıktı tamponunda 32-bit M4U/IOMMU (`0xFF02E000 + 16 MB > 4 GB`) sınırına takıldığı için `3840×2160` masaüstü **4 adet `1920×1080` donanım JPEG karosuna** bölündü (`AGTT` protokolü).
   - Yalnızca pikseli değişen karolar NEON + `/dev/video4` ile encode edilip round-robin tazelemeyle gönderilir; `4K`/`1080p` modlarında telefonun fiziksel AMOLED ekranı kapatılıp dondurulur (`brightness=0`, `/dev/fb0` döngüsü devre dışı).
3. **Sıfırdan Qt6 (PySide6) UDP İstemcisi (`scripts/agate_udp_client.py`):**
   - Gelen `AGTT` karolarını doğrudan `QImage(3840, 2160)` üzerine çizer (`8 MB` RX buffer, `4K`/`1080p`/`Yatay`/`Dikey`, `F11` tam ekran).
   - Canlı 4K doğrulama sonucu: **4/4 karo tam (`3840×2160`), `~693 KB/s`, `%0.0` paket kaybı** (`C:\mtk\agate_udp_client.py` ve `C:\mtk\baslat_udp_ekran.bat`).

### Adım 20: Sıfırdan AOSP 13 (`aosp_agate_hud`) ROM Derlemesi, `4.14.186` eBPF & Treble Düzeltmeleri ve Xiaomi 11T'de Canlı Açılış (15 Kasım)
1. **AOSP 13 Kaynak Ağacı, WSL2 Ortamı ve Emülatör Doğrulaması (`D:\AOSP_MIRROR`, `D:\WSL\Ubuntu`):**
   - 1150 git deposundan (`26.73 GB`) **AOSP 13 (`android-13.0.0_r83`, `TQ3A.230805.001.S1`)** çekildi ve WSL2 Ubuntu 22.04 (`32` çekirdek, `52 GB` RAM, `m -j32`) üzerinde sıfırdan derlendi (`130.093` Ninja adımı).
   - **GPU AGSL Cockpit HUD Launcher (`AgateHudLauncher`):** Jetpack Compose + Material3 + **`RuntimeShader` (AGSL)** (`COCKPIT_BACKGROUND_AGSL` plazma/3D zemin ızgarası + `RADIAL_GAUGE_AGSL` Mali-G77 kadranları) + canlı `/proc/stat`, `/proc/meminfo`, termal zonlar ve çevrimdışı/LLM destekli Türkçe `HudAgentEngine` yazıldı ve Windows `agate_hud_emu` (`1080×2400`) emülatöründe doğrulandı.
   - **Sistem Tema Overlay & Açılış Animasyonu:** `AgateHudFrameworkOverlay` (RRO), `640×640` `AGATE HUD OS` `bootanimation.zip`, `agate_hud.rc` ve `agate_charge_limit.sh` (`>= %70` kes / `<= %67` devam) ROM içine gömüldü.
2. **Fiziksel Cihaz (`agate`, Linux `4.14.186` + `V13.0.2.0` Vendor) Uyum Düzeltmeleri:**
   - **Treble VNDK v30/v31 & `skip_mount.cfg`:** `aosp_agate_hud.mk` içine `gsi_release.mk` eklendi (`com.android.vndk.v30/v31/v32` APEX'leri + `/system/system_ext/etc/init/config/skip_mount.cfg` ile stok `product`/`system_ext` çakışması engellendi).
   - **`agate_hud.rc` Init/SELinux Düzeltmesi:** `/system_ext/bin/sh` → `/system/bin/sh` ve `seclabel u:r:su:s0` eklendi.
   - **Linux `4.14.186` `bpfloader` Çekirdek Bug Teşhisi (`reboot,bpfloader-failed`):**
     - Ubuntu kurtarma çekirdeği üzerinden `/metadata/bootstat/persist.sys.boot.reason` okundu (`reboot,bpfloader-failed`).
     - AOSP `bpfloader` canlı `4.14.186` çekirdekte çalıştırıldığında 10/10 BPF `.o` dosyasının (`offload.o`, `netd.o`, `clatd.o`, `time_in_state.o`, `gpu_mem.o`, `gpu_work.o` vb.) sorunsuz yüklendiği, ancak en sondaki `BPF_MAP_TYPE_ARRAY (max_entries=2)` `key=1` yazma testinin çekirdekte `EINVAL` (`22`) döndürdüğü doğrulandı (`aosp_agate_hud/patches/bpfloader_4_14_agate.patch`). Yama sonrası `bpf.progs_loaded=1` elde edildi.
   - **`privapp-permissions` Allowlist (`privapp-permissions-com.agate.hud.xml`):** `adb logcat` ile `PermissionManagerServiceImpl` üzerinden yakalanan `BATTERY_STATS` ve `STATUS_BAR` yetkileri `/system_ext/etc/permissions/privapp-permissions-com.agate.hud.xml` ile tanımlandı.
3. **Fastboot / `fastbootd` Yazımı ve Canlı Donanım Doğrulaması (`scripts/flash_aosp_agate_hud.ps1`):**
   - `V13.0.2.0` açık `lk_a` (`ECF7D2F2...`) korunarak `vbmeta*` (`--disable-verity --disable-verification`), `boot_ab`, `dtbo_ab`, `vendor_a` (`2.09 GB`) ve **`system_agate_hud.img` (`1.93 GB`)** yazıldı.
   - **Sonuç:** Telefon **29 saniyede** kendi AOSP 13 ROM'uyla (`aosp_agate_hud-userdebug 13 TQ3A.230805.001.S1`) açıldı; `Mali-G77 MC9` (OpenGL ES 3.2) üzerinde **`com.agate.hud/.MainActivity`** canlı render aldı, `wlan0` Wi-Fi aktifleşti, `agate_charge_limit.sh` `%72` pilde `input_suspend=1` (`Discharging`) ile şarj kesiciyi otomatik devreye soktu ve `ro.boot.flash.locked=0` (`unlocked`) korundu.

---

## 5. Kritik Dosyalar ve Araçlar Özeti

| Dosya / Araç | Görevi |
|---|---|
| `C:\Users\met\Desktop\telefon-yedek\partisyonlar\` | 11 kritik orijinal partisyonun SHA-256 doğrulamalı yedeği |
| `C:\Users\met\Desktop\telefon-yedek\geri-donus\` | `preloader_lu0_v125.bin`, `lk_a_v13_unlocked.img`, `seccfg_unlocked.img`, `boot_a_*` imajları ve `SHA256SUMS.txt` |
| `C:\Users\met\Desktop\zadig-2.9.exe` | `USB\VID_0E8D&PID_0003` ve `VID_18D1&PID_D00D` için HVCI uyumlu `WinUSB` kurdu |
| `C:\mtk\flash_eng_cached.py` | `mtkclient` GPT/paket önbelleği + `Pipe error` `clear_halt` runtime yaması |
| `C:\mtk\simg2img.py` | Android sparse imajları (`super.img`, `userdata.img`) RAW formata çevirdi |
| `C:\mtk\extract_stock.py` | `payload.bin` (`CrAU`) içinden stok `V13.0.2.0.SKWMIXM` partisyonlarını çıkardı |
| `C:\mtk\v125\dl_v1259.py` & `flash_v1259.py` | Stok Android 11 `V12.5.9.0.RKWMIXM` paketini indirdi ve Fastboot flash yönetti |
| `C:\mtk\v125\v1259_multi_cmd.txt` | BROM üzerinden 24 partisyon + `super_raw.img` (6.62 GB) temiz kurulumunu yaptı |
| `C:\mtk\reunlock_check.py` | `SecCfgV4` (`HACC`) lock/unlock döngüsünü BROM'dan test etti |
| `C:\mtk\v125\brom_read_lockstate.py` | `seccfg` ve 16 MB `oem_misc1` içeriğini okuyup `Jz8PNRUF` bayraklarını teşhis etti |
| `C:\mtk\v125\brom_unlock_lk13.py` | `oem_misc1` temizliği + imzalı `V13.0.2.0 lk.img` ile kilidi BROM'dan açtı |
| `scripts/setup_ubuntu.sh` | Android üzerinde 32 GB sparse `ext4` loop imajına Ubuntu 22.04 kurulumu |
| `scripts/build_native_boot.py` | Stok `kernel` + `dtb` + statik `busybox` `initramfs` ile Android'siz `boot.img` üreticisi |
| `scripts/linux_init.sh`, `charge-limit.sh`, `batstat.sh` | Saf Linux PID 1 başlatıcısı + `%67–%70` şarj kesici |
| `scripts/fbui.py`, `scripts/ekran.sh` | `/dev/fb0` canlı telemetri dashboard + `ekran xfce | terminal` mod anahtarı |
| `scripts/fb_xfce_bridge.c` & `scripts/start_xfce_fb.sh` | `Xvfb :0` → `/dev/fb0` + `fts` dokunmatik + `/dev/video4` HW-JPEG akış köprüsü |
| `scripts/xfce_stream_server.py` | `:8090` canlı XFCE masaüstü web konsolu (`/dev/video4` + XTest uzaktan kontrol) |
| `scripts/agate_udp_client.py` | Sıfırdan yazılmış Qt6 (`PySide6`) saf UDP `:9900` donanım JPEG masaüstü istemcisi |
| `scripts/libhybris_mali_agate.patch` | `libhybris` Mali-G77 MC9 (`Android 11` / `MT6893` `/dev/ion` & ANGLE) tam yaması |
| `scripts/weston_hwjpeg.c` | Weston C modülü: ARM64 NEON + ION `0x400` + `/dev/video3` donanım JPEG akış eklentisi |
| `scripts/hwjpeg_v4l2.c` | `/dev/video3` & `/dev/video4` ION `0x400` V4L2 DMABUF donanım JPEG kütüphanesi (`/usr/local/lib/libhwjpeg.so`) |
| `scripts/gpu-perf.sh` | Mali-G77 `886 MHz` max performans / `auto` DVFS geçiş aracı (`/usr/local/bin/gpu-perf`) |
| `scripts/chrome-gpu.sh` & `scripts/chrome_stream_server.py` | Mali-G77 GPU + `/dev/video3` HW-JPEG destekli Chromium 156 konsolu (`:8080`) |
| `scripts/geri_donus_v1259_fastboot.ps1` & `geri_donus_v1302_fastboot.ps1` | Bootloader kilitlemeden Android 11 / Android 12 geri dönüş betikleri |
| `scripts/flash_aosp_agate_hud.ps1` | `V13.0.2.0` açık `lk` + `vendor_a` + özel AOSP 13 `system_agate_hud.img` yazım betiği |
| `aosp_agate_hud/` | `AgateHudLauncher` (Compose + AGSL + Agent), `AgateHudFrameworkOverlay`, `device/xiaomi/agate`, `bpfloader_4_14_agate.patch` |

---

## 6. Durum Özeti

- **Hard-Brick & Bootloader:** Cihaz kurtarıldı; `seccfg` (`0x03`), sıfırlanmış `oem_misc1` ve `V13.0.2.0 lk.img` ile bootloader kalıcı olarak **unlocked** durumda (`ro.boot.flash.locked=0`, `orange`).
- **Mevcut Çalışan Sistem:** Sıfırdan derlenmiş özel **AOSP 13 (`aosp_agate_hud-userdebug 13 TQ3A.230805.001.S1`)** — **Mali-G77 MC9** üzerinde **AGSL `RuntimeShader` Kokpit HUD (`com.agate.hud`)**, **`AgateHudFrameworkOverlay`**, **Wi-Fi (`wlan0`)**, **60/120 Hz ekran** ve **`%67–%70` donanım şarj kesici (`agate_charge_limit.sh`)** fiziksel cihazda canlı aktif.
- **Yedek & Geri Dönüş Güvenliği:** Tüm geri dönüş imajları (`preloader`, `seccfg`, `lk_a`, `boot_a_*`) ve Fastboot betikleri (`V12.5.9.0`, `V13.0.2.0`, Ubuntu) SHA-256 doğrulamalı olarak `C:\Users\met\Desktop\telefon-yedek\geri-donus\` içinde hazır; Windows `agate_hud_emu` emülatör ortamı (`D:\AndroidSdk`) da yedek geliştirme ortamı olarak aktif.

---

## 7. Devam Edilecek Sıradaki Adımlar (İsteğe Bağlı)

1. **10 Eşzamanlı Chrome Penceresi + `4 GB zram`:** Aynı yapıya `zram` swap eklenip 10 izole `BrowserContext` üzerinde `/dev/video3` + `/dev/video4` paralel akışı genişletilebilir.
2. **Ses Akışı:** `PulseAudio` `module-null-sink` üzerinden WebSocket/Opus ses aktarımı.
3. **Depolama Genişletme & Özel Kernel:** `userdata` (`106 GB`) bölümünü ext4 Ubuntu diski yapmak ve gerekirse `CONFIG_USER_NS`/`SYSVIPC`/`DEVTMPFS` açık özel kernel derlemek.

param(
    [switch]$FullRestore,
    [switch]$StockBootOnly
)

$ErrorActionPreference = "Stop"
$FB = "C:\mtk\platform-tools\fastboot.exe"
$BAK = "C:\Users\met\Desktop\telefon-yedek\geri-donus"
$V125 = "C:\mtk\v125\agate_global_images_V12.5.9.0.RKWMIXM_20211214.0000.00_11.0_global\images"

Write-Host "Fastboot cihazi bekleniyor (Ses Kisma + Guc ile Fastboot moduna alin)..."
& $FB getvar unlocked

if (-not $FullRestore) {
    $bootImg = if ($StockBootOnly) { "$BAK\boot_a_v1259_stock.img" } else { "$BAK\boot_a_v1259_magisk.img" }
    Write-Host "Yalnizca boot_a yaziliyor -> $bootImg (Bootloader ACIK kalir)"
    & $FB set_active a
    & $FB flash boot_a $bootImg
    & $FB flash lk_a "$BAK\lk_a_v13_unlocked.img"
    & $FB reboot
    Write-Host "Tamamlandi! Android 11 V12.5.9.0 aciliyor."
    exit 0
}

Write-Host "TAM V12.5.9.0 GERI YUKLEME (Bootloader ACIK kalacak - oem cdms CALISTIRILMAZ!)..."
& $FB set_active a
& $FB flash preloader_ab "$V125\preloader_agate.bin"
& $FB flash vbmeta_ab "$V125\vbmeta.img"
& $FB flash vbmeta_system_ab "$V125\vbmeta_system.img"
& $FB flash vbmeta_vendor_ab "$V125\vbmeta_vendor.img"
& $FB flash md1img_ab "$V125\md1img.img"
& $FB flash spmfw_ab "$V125\spmfw.img"
& $FB flash audio_dsp_ab "$V125\audio_dsp.img"
& $FB flash pi_img_ab "$V125\pi_img.img"
& $FB flash dpm_ab "$V125\dpm.img"
& $FB flash scp_ab "$V125\scp.img"
& $FB flash sspm_ab "$V125\sspm.img"
& $FB flash mcupm_ab "$V125\mcupm.img"
& $FB flash cam_vpu1_ab "$V125\cam_vpu1.img"
& $FB flash cam_vpu2_ab "$V125\cam_vpu2.img"
& $FB flash cam_vpu3_ab "$V125\cam_vpu3.img"
& $FB flash gz_ab "$V125\gz.img"
# Bootloader kilidi tekrar kilitlenmesin diye MI-Lock icermeyen imzali V13 lk.img kullanilir:
& $FB flash lk_ab "$BAK\lk_a_v13_unlocked.img"
$bootImg = if ($StockBootOnly) { "$V125\boot.img" } else { "$BAK\boot_a_v1259_magisk.img" }
& $FB flash boot_ab $bootImg
& $FB flash dtbo_ab "$V125\dtbo.img"
& $FB flash tee_ab "$V125\tee.img"
& $FB flash mitee_ab "$V125\mitee.img"
& $FB flash logo_ab "$V125\logo.bin"
& $FB flash super "$V125\super.img"
& $FB flash rescue "$V125\rescue.img"
& $FB flash cust "$V125\cust.img"
& $FB erase userdata
& $FB erase metadata
& $FB set_active a
& $FB reboot
Write-Host "Tam V12.5.9.0 geri yukleme tamamlandi (Bootloader ACIK)!"

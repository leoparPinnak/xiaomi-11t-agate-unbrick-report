param(
    [switch]$WithMagisk
)

$ErrorActionPreference = "Stop"
$FB = "C:\mtk\platform-tools\fastboot.exe"
$S13 = "C:\mtk\stock"
$D13 = "C:\Users\met\Desktop\telefon-yedek\firmware\stock"
$MAGISK_BOOT = "C:\Users\met\Desktop\telefon-yedek\partisyonlar\boot_a.img"

Write-Host "Fastboot cihazi bekleniyor (Ses Kisma + Guc ile Fastboot moduna alin)..."
& $FB getvar unlocked
& $FB set_active a

Write-Host "Faz 1: V13.0.2.0.SKWMIXM firmware ve boot imajlari yaziliyor (Bootloader ACIK kalir)..."
& $FB flash preloader_ab "$S13\preloader_raw.img"
& $FB flash vbmeta_ab "$S13\vbmeta.img"
& $FB flash vbmeta_system_ab "$S13\vbmeta_system.img"
& $FB flash vbmeta_vendor_ab "$S13\vbmeta_vendor.img"
& $FB flash md1img_ab "$S13\md1img.img"
& $FB flash spmfw_ab "$S13\spmfw.img"
& $FB flash audio_dsp_ab "$S13\audio_dsp.img"
& $FB flash pi_img_ab "$S13\pi_img.img"
& $FB flash dpm_ab "$S13\dpm.img"
& $FB flash scp_ab "$S13\scp.img"
& $FB flash sspm_ab "$S13\sspm.img"
& $FB flash mcupm_ab "$S13\mcupm.img"
& $FB flash cam_vpu1_ab "$S13\cam_vpu1.img"
& $FB flash cam_vpu2_ab "$S13\cam_vpu2.img"
& $FB flash cam_vpu3_ab "$S13\cam_vpu3.img"
& $FB flash gz_ab "$S13\gz.img"
& $FB flash lk_ab "$S13\lk.img"
$bootImg = if ($WithMagisk -and (Test-Path $MAGISK_BOOT)) { $MAGISK_BOOT } else { "$S13\boot.img" }
& $FB flash boot_ab $bootImg
& $FB flash dtbo_ab "$S13\dtbo.img"
& $FB flash tee_ab "$S13\tee.img"
& $FB flash mitee_ab "$S13\mitee.img"

Write-Host "Faz 2: fastbootd gecisi ve super dinamik partisyonlar..."
& $FB reboot fastboot
& $FB resize-logical-partition odm_a 0
& $FB resize-logical-partition odm_b 0
& $FB resize-logical-partition system_b 0
& $FB resize-logical-partition vendor_b 0
& $FB resize-logical-partition product_b 0
& $FB resize-logical-partition system_ext_b 0
& $FB resize-logical-partition system_a 2887729152
& $FB resize-logical-partition vendor_a 2092617728
& $FB resize-logical-partition product_a 1739563008
& $FB resize-logical-partition system_ext_a 692473856

& $FB flash system_a "$D13\system.img"
& $FB flash vendor_a "$D13\vendor.img"
& $FB flash product_a "$D13\product.img"
& $FB flash system_ext_a "$S13\system_ext.img"

& $FB erase userdata
& $FB erase metadata
& $FB set_active a
& $FB reboot
Write-Host "V13.0.2.0.SKWMIXM geri yukleme tamamlandi (Bootloader ACIK)!"

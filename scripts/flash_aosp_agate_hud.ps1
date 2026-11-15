param(
    [switch]$SkipFirmware
)

$FB = "C:\mtk\platform-tools\fastboot.exe"
$S13 = "C:\mtk\stock"
$D13 = "C:\Users\met\Desktop\telefon-yedek\firmware\stock"
$BAK = "C:\Users\met\Desktop\telefon-yedek\geri-donus"
$SYS = "D:\AOSP_OUT\system_agate_hud.img"

function Run-FB {
    param([string[]]$FbArgs)
    Write-Host ">> fastboot $($FbArgs -join ' ')"
    $out = & $FB @FbArgs 2>&1
    $rc = $LASTEXITCODE
    $out | ForEach-Object { Write-Host "   $_" }
    if ($rc -ne 0) {
        throw "fastboot failed (exit=$rc): fastboot $($FbArgs -join ' ')"
    }
    return ($out -join "`n")
}

if (-not (Test-Path $SYS)) {
    throw "Missing AOSP system image: $SYS"
}

$sysSize = (Get-Item $SYS).Length
$venSize = (Get-Item "$D13\vendor.img").Length
Write-Host "AOSP 13 HUD system.img : $sysSize bytes"
Write-Host "V13.0.2.0 vendor.img   : $venSize bytes"

$unlockedOut = Run-FB @("getvar", "unlocked")
if ($unlockedOut -notmatch "unlocked:\s*yes") {
    throw "Bootloader is NOT unlocked! Aborting safely."
}

Run-FB @("set_active", "a")

if (-not $SkipFirmware) {
    Write-Host "=== FAZ 1: V13.0.2.0 Firmware + Unlocked LK + AVB Disabled vbmeta + Android 12 Boot ==="
    Run-FB @("flash", "preloader_ab", "$S13\preloader_raw.img")
    Run-FB @("flash", "--disable-verity", "--disable-verification", "vbmeta_ab", "$S13\vbmeta.img")
    Run-FB @("flash", "--disable-verity", "--disable-verification", "vbmeta_system_ab", "$S13\vbmeta_system.img")
    Run-FB @("flash", "--disable-verity", "--disable-verification", "vbmeta_vendor_ab", "$S13\vbmeta_vendor.img")
    Run-FB @("flash", "md1img_ab", "$S13\md1img.img")
    Run-FB @("flash", "spmfw_ab", "$S13\spmfw.img")
    Run-FB @("flash", "audio_dsp_ab", "$S13\audio_dsp.img")
    Run-FB @("flash", "pi_img_ab", "$S13\pi_img.img")
    Run-FB @("flash", "dpm_ab", "$S13\dpm.img")
    Run-FB @("flash", "scp_ab", "$S13\scp.img")
    Run-FB @("flash", "sspm_ab", "$S13\sspm.img")
    Run-FB @("flash", "mcupm_ab", "$S13\mcupm.img")
    Run-FB @("flash", "cam_vpu1_ab", "$S13\cam_vpu1.img")
    Run-FB @("flash", "cam_vpu2_ab", "$S13\cam_vpu2.img")
    Run-FB @("flash", "cam_vpu3_ab", "$S13\cam_vpu3.img")
    Run-FB @("flash", "gz_ab", "$S13\gz.img")
    Run-FB @("flash", "lk_ab", "$BAK\lk_a_v13_unlocked.img")
    Run-FB @("flash", "boot_ab", "$S13\boot.img")
    Run-FB @("flash", "dtbo_ab", "$S13\dtbo.img")
    Run-FB @("flash", "tee_ab", "$S13\tee.img")
    Run-FB @("flash", "mitee_ab", "$S13\mitee.img")
}

Write-Host "=== FAZ 2: fastbootd gecisi ve super dinamik partisyonlar ==="
Run-FB @("reboot", "fastboot")

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $devs = & $FB devices 2>&1
    if ($devs -match "\S") {
        $u = & $FB getvar is-userspace 2>&1
        if (($u -join "`n") -match "is-userspace:\s*yes") {
            $ready = $true
            break
        }
    }
}
if (-not $ready) {
    throw "fastbootd (is-userspace: yes) did not come up in time!"
}

foreach ($p in @("odm_a", "odm_b", "system_b", "vendor_b", "product_b", "system_ext_b", "product_a", "system_ext_a")) {
    Run-FB @("resize-logical-partition", $p, "0")
}
Run-FB @("resize-logical-partition", "vendor_a", "$venSize")
Run-FB @("resize-logical-partition", "system_a", "$sysSize")

Run-FB @("flash", "vendor_a", "$D13\vendor.img")
Run-FB @("flash", "system_a", $SYS)

Run-FB @("erase", "userdata")
Run-FB @("erase", "metadata")
Run-FB @("set_active", "a")
Run-FB @("reboot")

Write-Host "=== TAMAMLANDI! Xiaomi 11T AOSP 13 HUD ROM baslatiliyor ==="

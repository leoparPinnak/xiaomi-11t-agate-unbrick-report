$(call inherit-product, $(SRC_TARGET_DIR)/product/aosp_arm64.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/gsi_release.mk)

PRODUCT_NAME := aosp_agate_hud
PRODUCT_DEVICE := generic_arm64
PRODUCT_BRAND := Xiaomi
PRODUCT_MODEL := Xiaomi 11T Agate HUD
PRODUCT_MANUFACTURER := Xiaomi

PRODUCT_ENFORCE_ARTIFACT_PATH_REQUIREMENTS := false
DISABLE_ARTIFACT_PATH_REQUIREMENTS := true

# Include custom GPU Cockpit Launcher, Agent, and Framework HUD Theme
PRODUCT_PACKAGES += \
    AgateHudLauncher \
    AgateHudFrameworkOverlay

PRODUCT_COPY_FILES += \
    device/xiaomi/agate/agate_hud.rc:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/init/agate_hud.rc \
    device/xiaomi/agate/agate_charge_limit.sh:$(TARGET_COPY_OUT_SYSTEM_EXT)/bin/agate_charge_limit.sh \
    device/xiaomi/agate/privapp-permissions-com.agate.hud.xml:$(TARGET_COPY_OUT_SYSTEM_EXT)/etc/permissions/privapp-permissions-com.agate.hud.xml \
    device/xiaomi/agate/bootanimation.zip:$(TARGET_COPY_OUT_PRODUCT)/media/bootanimation.zip

PRODUCT_SYSTEM_PROPERTIES += \
    ro.sf.lcd_density=440 \
    ro.surface_flinger.use_content_detection_for_refresh_rate=true \
    ro.surface_flinger.set_idle_timer_ms=0 \
    persist.agate.charge_limit=true \
    persist.sys.theme.accent=agate_hud \
    ro.com.android.dataroaming=false

#!/bin/bash
set -e

# Usage: make_flashable_zip.sh <OUT_DIR> <TARGET_DEVICE> <STOCK_DEVICE> [KERNEL_PACKAGE_PATH] [OUTPUT_ZIP_NAME]

OUT_DIR="$1"
TARGET_DEVICE="$2"
STOCK_DEVICE="$3"
KERNEL_PKG_PATH="${4:-}"
OUTPUT_ZIP_NAME="${5:-QuantumROM_${TARGET_DEVICE}_Port_For_${STOCK_DEVICE}_Recovery.zip}"

QT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER_DIR="$QT_DIR/installer"
BUILD_PKG_DIR="$OUT_DIR/package_tmp"

echo "============================================"
echo "    Creating Flashable Recovery ZIP Package "
echo "============================================"
echo "OUT_DIR: $OUT_DIR"
echo "Target: $TARGET_DEVICE | Stock: $STOCK_DEVICE"
echo "Output ZIP: $OUTPUT_ZIP_NAME"

rm -rf "$BUILD_PKG_DIR"
mkdir -p "$BUILD_PKG_DIR/META-INF/com/google/android"

# Copy installer engine (AOSP compiled update-binary & updater-script)
cp -f "$INSTALLER_DIR/META-INF/com/google/android/update-binary" "$BUILD_PKG_DIR/META-INF/com/google/android/"
cp -f "$INSTALLER_DIR/META-INF/com/google/android/updater-script" "$BUILD_PKG_DIR/META-INF/com/google/android/"
chmod +x "$BUILD_PKG_DIR/META-INF/com/google/android/update-binary"

# Copy super.img (Physical dynamic partition super container)
if [ -f "$OUT_DIR/super.img" ]; then
    echo "[+] Adding super.img ($(du -h "$OUT_DIR/super.img" | cut -f1))"
    cp -f "$OUT_DIR/super.img" "$BUILD_PKG_DIR/super.img"
fi

# Copy Kernel Images (boot.img & dtbo.img)
if [ -f "$OUT_DIR/boot.img" ]; then
    echo "[+] Adding boot.img ($(du -h "$OUT_DIR/boot.img" | cut -f1))"
    cp -f "$OUT_DIR/boot.img" "$BUILD_PKG_DIR/boot.img"
fi

if [ -f "$OUT_DIR/dtbo.img" ]; then
    echo "[+] Adding dtbo.img ($(du -h "$OUT_DIR/dtbo.img" | cut -f1))"
    cp -f "$OUT_DIR/dtbo.img" "$BUILD_PKG_DIR/dtbo.img"
fi

# If KERNEL_PKG_PATH was provided as a zip
if [ -n "$KERNEL_PKG_PATH" ] && [ -f "$KERNEL_PKG_PATH" ]; then
    echo "[*] Handling kernel package: $KERNEL_PKG_PATH"
    UNPACK_K_DIR="$OUT_DIR/kernel_unpack_tmp"
    rm -rf "$UNPACK_K_DIR"
    mkdir -p "$UNPACK_K_DIR"
    unzip -oq "$KERNEL_PKG_PATH" -d "$UNPACK_K_DIR" || true

    if [ -f "$UNPACK_K_DIR/boot.img" ] && [ ! -f "$BUILD_PKG_DIR/boot.img" ]; then
        echo "[+] Found boot.img inside kernel package."
        cp -f "$UNPACK_K_DIR/boot.img" "$BUILD_PKG_DIR/boot.img"
    fi

    if [ -f "$UNPACK_K_DIR/dtbo.img" ] && [ ! -f "$BUILD_PKG_DIR/dtbo.img" ]; then
        echo "[+] Found dtbo.img inside kernel package."
        cp -f "$UNPACK_K_DIR/dtbo.img" "$BUILD_PKG_DIR/dtbo.img"
    fi

    rm -rf "$UNPACK_K_DIR"
fi

# Copy Android OTA package metadata
if [ -d "$QT_DIR/ota" ]; then
    echo "[+] Adding Android OTA metadata..."
    mkdir -p "$BUILD_PKG_DIR/META-INF/com/android"
    [ -f "$QT_DIR/ota/metadata" ] && cp -f "$QT_DIR/ota/metadata" "$BUILD_PKG_DIR/META-INF/com/android/metadata"
    [ -f "$QT_DIR/ota/metadata.pb" ] && cp -f "$QT_DIR/ota/metadata.pb" "$BUILD_PKG_DIR/META-INF/com/android/metadata.pb"
fi

FINAL_ZIP_PATH="$OUT_DIR/$OUTPUT_ZIP_NAME"
rm -f "$FINAL_ZIP_PATH"

echo "[*] Compressing into recovery flashable zip (level 1 for high speed)..."
cd "$BUILD_PKG_DIR"
7z a -tzip "$FINAL_ZIP_PATH" ./* -mx=1

OTA_CERT="$QT_DIR/ota_keys/ota_key.x509.pem"
OTA_KEY="$QT_DIR/ota_keys/ota_key.pk8"
SIGNAPK_BIN="$QT_DIR/bin/signapk/signapk"

# If private key was passed via environment variable (e.g. GitHub Actions secret)
if [ ! -f "$OTA_KEY" ] && [ -n "${OTA_KEY_BASE64:-}" ]; then
    mkdir -p "$QT_DIR/ota_keys"
    echo "$OTA_KEY_BASE64" | base64 -d > "$QT_DIR/ota_keys/ota_key.pk8"
    chmod 600 "$QT_DIR/ota_keys/ota_key.pk8"
    OTA_KEY="$QT_DIR/ota_keys/ota_key.pk8"
fi

if [ -f "$OTA_CERT" ] && [ -f "$OTA_KEY" ] && [ -x "$SIGNAPK_BIN" ]; then
    echo "[*] Signing recovery zip with OTA key (whole-file signature)..."
    SIGNED_ZIP_PATH="${FINAL_ZIP_PATH%.zip}_signed.zip"
    "$SIGNAPK_BIN" -w "$OTA_CERT" "$OTA_KEY" "$FINAL_ZIP_PATH" "$SIGNED_ZIP_PATH"
    if [ -f "$SIGNED_ZIP_PATH" ]; then
        mv -f "$SIGNED_ZIP_PATH" "$FINAL_ZIP_PATH"
        echo "[+] Successfully signed recovery package!"
    fi
fi

echo "============================================"
echo " Flashable ZIP Created Successfully!"
echo " Location: $FINAL_ZIP_PATH"
echo " Size: $(du -h "$FINAL_ZIP_PATH" | cut -f1)"
echo "============================================"

rm -rf "$BUILD_PKG_DIR"

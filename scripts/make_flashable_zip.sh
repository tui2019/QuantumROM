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
mkdir -p "$BUILD_PKG_DIR/tools"
mkdir -p "$BUILD_PKG_DIR/images"

# Copy installer scripts
cp -f "$INSTALLER_DIR/META-INF/com/google/android/update-binary" "$BUILD_PKG_DIR/META-INF/com/google/android/"
cp -f "$INSTALLER_DIR/META-INF/com/google/android/updater-script" "$BUILD_PKG_DIR/META-INF/com/google/android/"
chmod +x "$BUILD_PKG_DIR/META-INF/com/google/android/update-binary"

# Setup tools (lptools)
if [ ! -f "$INSTALLER_DIR/tools/lptools" ]; then
    echo "[*] Downloading static arm64 lptools..."
    mkdir -p "$INSTALLER_DIR/tools"
    wget -q --no-check-certificate \
        "https://raw.githubusercontent.com/osm0sis/AnyKernel3/master/tools/lptools" \
        -O "$INSTALLER_DIR/tools/lptools" || true
    chmod +x "$INSTALLER_DIR/tools/lptools" 2>/dev/null || true
fi

if [ -f "$INSTALLER_DIR/tools/lptools" ]; then
    cp -f "$INSTALLER_DIR/tools/lptools" "$BUILD_PKG_DIR/tools/"
fi

# Copy Partition Images
echo "[*] Copying partition images to package..."
for part in system vendor product odm system_ext; do
    if [ -f "$OUT_DIR/${part}.img" ]; then
        echo " [+] Adding ${part}.img ($(du -h "$OUT_DIR/${part}.img" | cut -f1))"
        cp -f "$OUT_DIR/${part}.img" "$BUILD_PKG_DIR/images/"
    fi
done

# Copy Kernel Images (boot.img & dtbo.img)
if [ -f "$OUT_DIR/boot.img" ]; then
    echo "[+] Adding boot.img ($(du -h "$OUT_DIR/boot.img" | cut -f1))"
    cp -f "$OUT_DIR/boot.img" "$BUILD_PKG_DIR/images/boot.img"
fi

if [ -f "$OUT_DIR/dtbo.img" ]; then
    echo "[+] Adding dtbo.img ($(du -h "$OUT_DIR/dtbo.img" | cut -f1))"
    cp -f "$OUT_DIR/dtbo.img" "$BUILD_PKG_DIR/images/dtbo.img"
fi

# If KERNEL_PKG_PATH was provided as a zip and boot.img was not in OUT_DIR
if [ ! -f "$BUILD_PKG_DIR/images/boot.img" ] && [ -n "$KERNEL_PKG_PATH" ] && [ -f "$KERNEL_PKG_PATH" ]; then
    echo "[*] Extracting kernel package: $KERNEL_PKG_PATH"
    UNPACK_K_DIR="$OUT_DIR/kernel_unpack_tmp"
    rm -rf "$UNPACK_K_DIR"
    mkdir -p "$UNPACK_K_DIR"
    unzip -oq "$KERNEL_PKG_PATH" -d "$UNPACK_K_DIR" || true

    if [ -f "$UNPACK_K_DIR/boot.img" ]; then
        echo "[+] Found boot.img inside kernel package."
        cp -f "$UNPACK_K_DIR/boot.img" "$BUILD_PKG_DIR/images/boot.img"
    fi

    if [ -f "$UNPACK_K_DIR/dtbo.img" ]; then
        echo "[+] Found dtbo.img inside kernel package."
        cp -f "$UNPACK_K_DIR/dtbo.img" "$BUILD_PKG_DIR/images/dtbo.img"
    fi

    # Fallback to store AnyKernel if boot.img wasn't pre-packed
    if [ ! -f "$BUILD_PKG_DIR/images/boot.img" ]; then
        echo "[!] Note: Storing AnyKernel package as fallback."
        mkdir -p "$BUILD_PKG_DIR/kernel"
        cp -f "$KERNEL_PKG_PATH" "$BUILD_PKG_DIR/kernel/kernel.zip"
    fi

    rm -rf "$UNPACK_K_DIR"
fi

FINAL_ZIP_PATH="$OUT_DIR/$OUTPUT_ZIP_NAME"
rm -f "$FINAL_ZIP_PATH"

echo "[*] Compressing into recovery flashable zip..."
cd "$BUILD_PKG_DIR"
7z a -tzip "$FINAL_ZIP_PATH" ./* -mx=5

echo "============================================"
echo " Flashable ZIP Created Successfully!"
echo " Location: $FINAL_ZIP_PATH"
echo " Size: $(du -h "$FINAL_ZIP_PATH" | cut -f1)"
echo "============================================"

rm -rf "$BUILD_PKG_DIR"

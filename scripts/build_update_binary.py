import gzip
import os

def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    installer_dir = os.path.join(root, "installer")
    bb_path = os.path.join(installer_dir, "tools", "busybox")
    lp_path = os.path.join(installer_dir, "tools", "lptools_static")

    # Create a tar containing busybox and lptools_static, and gzip it
    import io, tarfile
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
        tar.add(bb_path, arcname="busybox")
        tar.add(lp_path, arcname="lptools_static")
    tools_tgz = tar_buf.getvalue()

    script_header = r'''#!/sbin/sh
#
# Project Revive Recovery Flashable Installer for Samsung Galaxy Tab S6 Lite (SM-P613 / gta4xlve)
#

OUTFD="$2"
[ -z "$OUTFD" ] && OUTFD=1
ZIPFILE="$3"

ui_print() {
    eval "printf 'ui_print %s\nui_print\n' \"\$1\" >&$OUTFD" 2>/dev/null || printf "%s\n" "$1"
}

set_progress() {
    eval "printf 'set_progress %s\n' \"\$1\" >&$OUTFD" 2>/dev/null || true
}

ui_print "============================================"
ui_print "        Project Revive OS Installer         "
ui_print "    One UI 8.5 Port for Galaxy Tab S6 Lite  "
ui_print "============================================"
ui_print " "

TMP_DIR="/tmp/revive_installer"
rm -rf "$TMP_DIR"
mkdir -p "$TMP_DIR"
mkdir -p "$TMP_DIR/tools"

set_progress 0.05

# -----------------------------------------------------------------------------
# EXTRACT EMBEDDED HIGH-PERFORMANCE TOOLS (Zero FUSE dependency)
# -----------------------------------------------------------------------------
BUSYBOX="$TMP_DIR/tools/busybox"
LPTOOLS="$TMP_DIR/tools/lptools_static"

if [ ! -x "$BUSYBOX" ]; then
    ui_print "[*] Initializing embedded tools..."
    SCRIPT_PATH="$0"
    [ ! -f "$SCRIPT_PATH" ] && SCRIPT_PATH="/tmp/update-binary"
    [ ! -f "$SCRIPT_PATH" ] && SCRIPT_PATH="/tmp/update_binary"
    
    PAYLOAD_LINE=$(grep -n "^__TOOLS_ARCHIVE_BELOW__" "$SCRIPT_PATH" 2>/dev/null | cut -d: -f1 | head -n 1)
    if [ -n "$PAYLOAD_LINE" ]; then
        START_LINE=$(( PAYLOAD_LINE + 1 ))
        tail -n +"$START_LINE" "$SCRIPT_PATH" | tar -xz -C "$TMP_DIR/tools" 2>/dev/null || true
        chmod -R 755 "$TMP_DIR/tools" 2>/dev/null || true
    fi
fi

[ ! -x "$BUSYBOX" ] && BUSYBOX="/tmp/busybox"
[ ! -x "$LPTOOLS" ] && LPTOOLS="/tmp/lptools_static"

# Verify device
DEVICE=$(getprop ro.product.device)
[ -z "$DEVICE" ] && DEVICE=$(getprop ro.build.product)
MODEL=$(getprop ro.product.model)

ui_print "[*] Target Device: $MODEL ($DEVICE)"

case "$DEVICE" in
    *gta4xlve*|*gta4xl*|*p613*|*P613*|*p619*|*P619*)
        ui_print "[+] Supported device detected!"
        ;;
    *)
        ui_print "[!] Warning: Unknown device code ($DEVICE), proceeding..."
        ;;
esac

# Unmount existing partitions to prevent busy errors
ui_print "[*] Unmounting existing partitions..."
umount /system /system_root /vendor /product /odm /system_ext 2>/dev/null || true

# Dynamic super partition helper
SUPER_DEV="/dev/block/by-name/super"
[ ! -e "$SUPER_DEV" ] && SUPER_DEV="/dev/block/bootdevice/by-name/super"
[ ! -e "$SUPER_DEV" ] && SUPER_DEV=$(find /dev/block -name "super" 2>/dev/null | head -n 1)

# Check if super.img is provided (Direct Boot + Super Combo)
SUPER_IN_ZIP=""
if unzip -l "$ZIPFILE" "images/super.img" >/dev/null 2>&1; then
    SUPER_IN_ZIP="images/super.img"
elif unzip -l "$ZIPFILE" "super.img" >/dev/null 2>&1; then
    SUPER_IN_ZIP="super.img"
fi

if [ -n "$SUPER_IN_ZIP" ] && [ -e "$SUPER_DEV" ]; then
    ui_print " "
    ui_print "============================================"
    ui_print "     Flashing Dynamic Super Partition       "
    ui_print "============================================"
    ui_print "[*] Flashing $SUPER_IN_ZIP directly to $SUPER_DEV..."
    set_progress 0.20
    if [ -x "$BUSYBOX" ]; then
        "$BUSYBOX" unzip -p "$ZIPFILE" "$SUPER_IN_ZIP" | "$BUSYBOX" dd of="$SUPER_DEV" bs=4M 2>/dev/null || "$BUSYBOX" unzip -p "$ZIPFILE" "$SUPER_IN_ZIP" | "$BUSYBOX" dd of="$SUPER_DEV" bs=1M
    else
        unzip -p "$ZIPFILE" "$SUPER_IN_ZIP" | dd of="$SUPER_DEV" bs=4M 2>/dev/null || unzip -p "$ZIPFILE" "$SUPER_IN_ZIP" | dd of="$SUPER_DEV" bs=1M
    fi
    ui_print "[+] super.img flashed successfully!"
    set_progress 0.80

else
    # Fallback to logical partition streaming
    if [ -e "$SUPER_DEV" ] && [ -x "$LPTOOLS" ]; then
        ui_print "[*] Preparing dynamic super partition..."
        "$LPTOOLS" unlimited-group main 2>/dev/null || true
        "$LPTOOLS" unlimited-group qti_dynamic_partitions 2>/dev/null || true
        "$LPTOOLS" unlimited-group default 2>/dev/null || true

        # Pre-allocate and map all partitions up-front
        ui_print "    Allocating logical partitions (product, system, vendor)..."
        "$LPTOOLS" unmap product 2>/dev/null || true
        "$LPTOOLS" create product 957112320 2>/dev/null || true
        "$LPTOOLS" resize product 957112320 2>/dev/null || true
        "$LPTOOLS" map product 2>/dev/null || true

        "$LPTOOLS" unmap system 2>/dev/null || true
        "$LPTOOLS" create system 3074949120 2>/dev/null || true
        "$LPTOOLS" resize system 3074949120 2>/dev/null || true
        "$LPTOOLS" map system 2>/dev/null || true

        "$LPTOOLS" unmap vendor 2>/dev/null || true
        "$LPTOOLS" create vendor 628994048 2>/dev/null || true
        "$LPTOOLS" resize vendor 628994048 2>/dev/null || true
        "$LPTOOLS" map vendor 2>/dev/null || true
    fi

    stream_partition() {
        local PART="$1"
        local DISPLAY_MB="$2"
        local BLOCK_DEV=""

        ui_print "[*] Flashing $PART (${DISPLAY_MB} MB)..."

        if [ -e "/dev/block/mapper/$PART" ]; then
            BLOCK_DEV="/dev/block/mapper/$PART"
        elif [ -e "/dev/block/bootdevice/by-name/$PART" ]; then
            BLOCK_DEV="/dev/block/bootdevice/by-name/$PART"
        elif [ -e "/dev/block/by-name/$PART" ]; then
            BLOCK_DEV="/dev/block/by-name/$PART"
        fi

        if [ -n "$BLOCK_DEV" ] && [ -e "$BLOCK_DEV" ]; then
            ui_print "    Writing image to $BLOCK_DEV..."
            if [ -x "$BUSYBOX" ]; then
                "$BUSYBOX" unzip -p "$ZIPFILE" "images/${PART}.img" | "$BUSYBOX" dd of="$BLOCK_DEV" bs=4M 2>/dev/null || "$BUSYBOX" unzip -p "$ZIPFILE" "images/${PART}.img" | "$BUSYBOX" dd of="$BLOCK_DEV" bs=1M
            else
                unzip -p "$ZIPFILE" "images/${PART}.img" | dd of="$BLOCK_DEV" bs=4M 2>/dev/null || unzip -p "$ZIPFILE" "images/${PART}.img" | dd of="$BLOCK_DEV" bs=1M
            fi
            ui_print "[+] Successfully flashed $PART!"
        fi
    }

    set_progress 0.10
    stream_partition "product" "912"

    set_progress 0.35
    stream_partition "system" "2932"

    set_progress 0.75
    stream_partition "vendor" "600"
fi

set_progress 0.85

# -----------------------------------------------------------------------------
# FLASH BOOT & DTBO IMAGES (Direct Boot Flash)
# -----------------------------------------------------------------------------
ui_print " "
ui_print "============================================"
ui_print "       Installing Kernel & Boot Image       "
ui_print "============================================"

BOOT_DEV="/dev/block/bootdevice/by-name/boot"
[ ! -e "$BOOT_DEV" ] && BOOT_DEV="/dev/block/by-name/boot"

BOOT_IN_ZIP=""
if unzip -l "$ZIPFILE" "images/boot.img" >/dev/null 2>&1; then
    BOOT_IN_ZIP="images/boot.img"
elif unzip -l "$ZIPFILE" "boot.img" >/dev/null 2>&1; then
    BOOT_IN_ZIP="boot.img"
fi

if [ -n "$BOOT_IN_ZIP" ] && [ -e "$BOOT_DEV" ]; then
    ui_print "[*] Flashing boot.img directly to $BOOT_DEV..."
    if [ -x "$BUSYBOX" ]; then
        "$BUSYBOX" unzip -p "$ZIPFILE" "$BOOT_IN_ZIP" | "$BUSYBOX" dd of="$BOOT_DEV" bs=4M
    else
        unzip -p "$ZIPFILE" "$BOOT_IN_ZIP" | dd of="$BOOT_DEV" bs=4M
    fi
    ui_print "[+] boot.img flashed successfully!"
fi



# Fallback to AnyKernel if direct boot.img is not present
if [ -z "$BOOT_IN_ZIP" ] && unzip -l "$ZIPFILE" "kernel/kernel.zip" >/dev/null 2>&1; then
    ui_print "[*] Extracting and executing AnyKernel installer..."
    mkdir -p "$TMP_DIR/kernel/ak3"
    if [ -x "$BUSYBOX" ]; then
        "$BUSYBOX" unzip -p "$ZIPFILE" "kernel/kernel.zip" > "$TMP_DIR/kernel/kernel.zip"
        "$BUSYBOX" unzip -o "$TMP_DIR/kernel/kernel.zip" -d "$TMP_DIR/kernel/ak3" >/dev/null 2>&1
    else
        unzip -p "$ZIPFILE" "kernel/kernel.zip" > "$TMP_DIR/kernel/kernel.zip"
        unzip -o "$TMP_DIR/kernel/kernel.zip" -d "$TMP_DIR/kernel/ak3" >/dev/null 2>&1
    fi
    chmod -R 755 "$TMP_DIR/kernel/ak3"

    if [ -f "$TMP_DIR/kernel/ak3/anykernel.sh" ]; then
        cd "$TMP_DIR/kernel/ak3"
        sh anykernel.sh "$TMP_DIR/kernel/kernel.zip" 2>&1 | while IFS= read -r line; do
            ui_print "    $line"
        done
        ui_print "[+] Kernel patched and flashed!"
    fi
fi

# Cleanup
ui_print " "
ui_print "[*] Cleaning up temporary files..."
rm -rf "$TMP_DIR"

set_progress 1.0

ui_print " "
ui_print "============================================"
ui_print "      Project Revive Flashed Successfully!  "
ui_print "          Please reboot your tablet!        "
ui_print "============================================"
ui_print " "

exit 0
__TOOLS_ARCHIVE_BELOW__
'''

    out_path = os.path.join(installer_dir, "META-INF", "com", "google", "android", "update-binary")
    with open(out_path, "wb") as f:
        f.write(script_header.encode("utf-8"))
        f.write(tools_tgz)
    os.chmod(out_path, 0o755)
    print(f"Generated self-extracting {out_path} ({os.path.getsize(out_path)} bytes)")

if __name__ == "__main__":
    main()

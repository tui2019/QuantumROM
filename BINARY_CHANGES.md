# Binary Changes & Patch Documentation for QuantumROM (SM-P613 Port)

This document tracks all binary modifications applied to Samsung system libraries when porting ROMs (e.g., from SM-P620 / Exynos 1280 or Tab S9) to the **Samsung Galaxy Tab S6 Lite 2022 (SM-P613 / Qualcomm Snapdragon 720G `sm7125` / `atoll`)**.

Refer to this document when updating the ROM base to future Android / One UI versions (e.g., One UI 7, 8, 9).

---

## 1. Camera Preview Fix (Black Screen Viewfinder)

### Target Files
- `system/lib64/libcore2nativeutil.camera.samsung.so`
- `system/lib/libcore2nativeutil.camera.samsung.so`

### Component & Context
- **Process**: `com.sec.android.app.camera`
- **Function**: `PlatformUtil::getCurrentVendor()` called by `SurfaceNativeUtilImpl::nativeSetSurfaceFormat(...)`

### Root Cause
When configuring the preview native surface, Samsung queries `PlatformUtil::getCurrentVendor()`:
- `1` = `SLSI` (Exynos)
- `2` = `QCOM` (Qualcomm Snapdragon)
- `3` = `MTK` (MediaTek)

In Exynos builds (SM-P620), Samsung hardcodes `PlatformUtil::getCurrentVendor()` to return `1`. When vendor is `1`, `nativeSetSurfaceFormat` overrides the preview buffer format to `0x11D` (decimal `285` = `HAL_PIXEL_FORMAT_EXYNOS_YCrCb_420_SP_M`).
On Qualcomm devices (Snapdragon 720G / Adreno 618), format `0x11D` is unsupported by `qdgralloc`, crashing `GraphicBufferAllocator` with `-EINVAL (-22)` on every frame and resulting in a black screen.

Changing `PlatformUtil::getCurrentVendor()` to return `2` (`QCOM`) causes `nativeSetSurfaceFormat` to retain standard format `0x11` (`HAL_PIXEL_FORMAT_YCrCb_420_SP` / NV21), which Qualcomm Adreno supports natively.

### Binary Modifications

#### 64-bit (`system/lib64/libcore2nativeutil.camera.samsung.so`)
- **Function**: `PlatformUtil::getCurrentVendor()`
- **Original Disassembly**:
  ```asm
  mov w0, #1          ; 20 00 80 52
  ret                 ; c0 03 5f d6
  ```
- **Patched Disassembly**:
  ```asm
  mov w0, #2          ; 40 00 80 52
  ret                 ; c0 03 5f d6
  ```
- **One UI 6.1 Offset**: `0x184c4`
- **Hex Replacement**: `20 00 80 52` -> `40 00 80 52`

#### 32-bit (`system/lib/libcore2nativeutil.camera.samsung.so`)
- **Function**: `PlatformUtil::getCurrentVendor()`
- **Original Disassembly**:
  ```asm
  movs r0, #1         ; 01 20
  bx lr               ; 70 47
  ```
- **Patched Disassembly**:
  ```asm
  movs r0, #2         ; 02 20
  bx lr               ; 70 47
  ```
- **One UI 6.1 Offset**: `0xfaf0`
- **Hex Replacement**: `01 20` -> `02 20`

### How to Find in Future One UI Versions
Search for the symbol `PlatformUtil::getCurrentVendor` using `nm -D` or `radare2`:
```bash
r2 -q -c "is~getCurrentVendor" libcore2nativeutil.camera.samsung.so
```
If symbols are stripped, search for the `nativeSetSurfaceFormat` function which calls `getCurrentVendor` before checking `cmp w0, #1` / `cmp w19, #0x11` / `mov w19, #0x11d`.

---

## 2. Video Mode Fix (Freeze on Video Tab & `mediaserver` Crash)

### Target Files
- `system/lib64/libstagefright.so`
- `system/lib/libstagefright.so`

### Component & Context
- **Process**: `/system/bin/mediaserver`
- **Function**: `android::ACodec::reconfigEncoder4OtherApps(android::sp<android::AMessage> const&)`

### Root Cause
In Samsung's proprietary additions to AOSP Stagefright (`ACodec.cpp`), Samsung reads `/proc/<pid>/cmdline` to identify the calling application before starting video encoding.
Samsung allocated a 255-byte buffer on the stack (`char buf[255]`), but called `fread(buf, 1, 512, fp)`.
Under Android Bionic Libc's `_FORTIFY_SOURCE=2` runtime protection, `__fread_chk` verifies that `size * count <= buffer_size`. Because `1 * 512 > 255`, Bionic aborts `mediaserver` with:
```
FORTIFY: fread: prevented 512-byte write into 255-byte buffer (SIGABRT)
```
When `mediaserver` crashes, the Samsung Camera app hangs indefinitely waiting for `MediaRecorder` IPC.

Changing the read count parameter in `__fread_chk` from `512` (`0x200`) to `255` (`0xFF`) ensures `1 * 255 <= 255`, satisfying the FORTIFY bounds check and allowing the video recording session to start cleanly.

### Binary Modifications

#### 64-bit (`system/lib64/libstagefright.so`)
- **Function**: `android::ACodec::reconfigEncoder4OtherApps`
- **Original Disassembly**:
  ```asm
  mov w1, #1          ; 21 00 80 52
  mov w2, #0x200      ; 02 40 80 52  <-- BUG (512 bytes)
  mov x3, x20         ; e3 03 14 aa
  mov w4, #0xff       ; e4 1f 80 52  <-- Buffer size is 255
  add x23, sp, 0x10   ; f7 43 00 91
  bl __fread_chk      ; e1 92 05 94
  ```
- **Patched Disassembly**:
  ```asm
  mov w1, #1          ; 21 00 80 52
  mov w2, #0xff       ; e2 1f 80 52  <-- Fixed (255 bytes)
  mov x3, x20         ; e3 03 14 aa
  mov w4, #0xff       ; e4 1f 80 52
  add x23, sp, 0x10   ; f7 43 00 91
  bl __fread_chk      ; e1 92 05 94
  ```
- **One UI 6.1 Offset**: `0xec8bc`
- **Hex Replacement**: `21 00 80 52 02 40 80 52` -> `21 00 80 52 e2 1f 80 52`

#### 32-bit (`system/lib/libstagefright.so`)
- **Function**: `android::ACodec::reconfigEncoder4OtherApps`
- **Original Disassembly**:
  ```asm
  movs r1, #1         ; 01 21
  mov.w r2, #0x200    ; 4f f4 00 72  <-- BUG (512 bytes)
  ```
- **Patched Disassembly**:
  ```asm
  movs r1, #1         ; 01 21
  mov.w r2, #0xff     ; 4f f0 ff 02  <-- Fixed (255 bytes)
  ```
- **One UI 6.1 Offset**: `0xa00c8`
- **Hex Replacement**: `01 21 4f f4 00 72` -> `01 21 4f f0 ff 02`

### How to Find in Future One UI Versions
Search for `reconfigEncoder4OtherApps` symbol:
```bash
r2 -q -c "is~reconfigEncoder4OtherApps" libstagefright.so
```
If symbols are stripped, search for calls to `__fread_chk` that pass `w4 = 0xff` and `w2 = 0x200`.

---

## 3. Automated Python Patching Script

Use this script during ROM builds to automatically apply all patches across the extracted `system` tree:

```python
#!/usr/bin/env python3
import os
import sys

def patch_file(path, old_pattern, new_pattern, name):
    if not os.path.exists(path):
        print(f"[-] {name}: {path} not found, skipping.")
        return False
    with open(path, "rb") as f:
        data = bytearray(f.read())
    
    idx = data.find(old_pattern)
    if idx == -1:
        if new_pattern in data:
            print(f"[!] {name}: Already patched in {path}")
            return True
        print(f"[-] {name}: Target pattern not found in {path}")
        return False
    
    data[idx:idx+len(old_pattern)] = new_pattern
    with open(path, "wb") as f:
        f.write(data)
    print(f"[+] {name}: Successfully patched at offset 0x{idx:x} in {path}")
    return True

def main(system_root):
    # 1. libcore2nativeutil (64-bit)
    patch_file(
        os.path.join(system_root, "system/lib64/libcore2nativeutil.camera.samsung.so"),
        b"\x20\x00\x80\x52\xc0\x03\x5f\xd6",  # mov w0, 1; ret
        b"\x40\x00\x80\x52\xc0\x03\x5f\xd6",  # mov w0, 2; ret
        "Camera Preview (libcore2nativeutil 64-bit)"
    )

    # 2. libstagefright (64-bit)
    patch_file(
        os.path.join(system_root, "system/lib64/libstagefright.so"),
        b"\x21\x00\x80\x52\x02\x40\x80\x52",  # mov w1, 1; mov w2, 0x200
        b"\x21\x00\x80\x52\xe2\x1f\x80\x52",  # mov w1, 1; mov w2, 0xff
        "Video Mode Fortify (libstagefright 64-bit)"
    )

    # 3. libstagefright (32-bit)
    patch_file(
        os.path.join(system_root, "system/lib/libstagefright.so"),
        b"\x01\x21\x4f\xf4\x00\x72",          # movs r1, 1; mov.w r2, 0x200
        b"\x01\x21\x4f\xf0\xff\x02",          # movs r1, 1; mov.w r2, 0xff
        "Video Mode Fortify (libstagefright 32-bit)"
    )

if __name__ == "__main__":
    sys_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    main(sys_dir)
```

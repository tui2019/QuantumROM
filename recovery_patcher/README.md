# Project Revive - Automated Recovery Patcher

A fully automated, deterministic, bit-accurate recovery patching engine designed for Samsung Galaxy Tab (Qualcomm Snapdragon 720G / SM7125) and modern Android Header v2 devices running LineageOS / AOSP recovery.

---

## 📁 Directory Structure

```text
recovery_patcher/
├── patch_recovery.py          # Master patching engine
├── avbtool.py                 # Official Google AOSP AVB 1.3.0 utility
├── config.json                # User configuration file
├── stock_recovery.tar         # Input stock recovery archive (from device maintainer)
├── README.md                  # This documentation
├── assets/                    # Graphic assets folder
│   ├── logo_image.png         # Main Recovery splash logo
│   ├── logo_image_switch.png  # Recovery switch splash logo
│   └── fastbootd.png          # Fastbootd splash logo
├── keys/                      # Cryptographic keys and certificates
│   ├── avb_key.pem            # AVB 1.0 RSA-4096 private signing key
│   └── ota_key.x509.pem       # X.509 OTA verification public certificate
└── output/                    # Generated output directory
    └── Project_Revive_Recovery_v9.tar  # Flashable Odin TAR archive
```

---

## 🎨 Asset Specifications

All graphics drawn by LineageOS / AOSP `ScreenRecoveryUI` must strictly comply with the following format requirements:

| Asset Name | Target Path in Ramdisk | Resolution | Color Mode | Background | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `logo_image.png` | `res/images/logo_image.png` | **384 × 240 px** | RGB or RGBA PNG | `#000000` (Solid Black) | Main recovery centered splash logo |
| `logo_image_switch.png` | `res/images/logo_image_switch.png` | **384 × 240 px** | RGB or RGBA PNG | `#000000` (Solid Black) | Secondary recovery switch splash logo |
| `fastbootd.png` | `res/images/fastbootd.png` | **384 × 240 px** | RGB or RGBA PNG | `#000000` (Solid Black) | Centered splash logo displayed in fastbootd mode |

### Additional Asset Capabilities (Optional)
If you wish to customize other UI graphics, you can drop matching PNGs into `assets/` and reference them in `config.json`:
* **Animation Loops (`loop00000.png` through `loop00029.png`):** `384 × 240 px`, RGB PNG.
* **Status Text Banners (`installing_text.png`, `error_text.png`, `erasing_text.png`):** Pre-rendered localized text PNGs.
* **Navigation Back Icons (`ic_back.png`, `ic_back_sel.png`):** `48 × 48 px`, PNG.

---

## 🔑 Cryptographic Key Specifications

### 1. AVB Signing Key (`keys/avb_key.pem`)
* **Format:** RSA Private Key in PEM format (`-----BEGIN RSA PRIVATE KEY-----` or `-----BEGIN PRIVATE KEY-----`).
* **Key Length:** **4096 bits** (compatible with Google AOSP `testkey_rsa4096.pem`).
* **Algorithm:** `SHA256_RSA4096`.
* **Purpose:** Signs the final recovery payload with an Android Verified Boot (AVB 1.0 / 1.3) hash footer. This prevents Samsung bootloader aborts (`SECURE CHECK FAIL: recovery`).

### 2. OTA Certificate (`keys/ota_key.x509.pem`)
* **Format:** Standard X.509 Certificate in PEM format (`-----BEGIN CERTIFICATE-----`).
* **Key Length:** 2048 or 4096 bits RSA.
* **Signature Algorithm:** `sha256WithRSAEncryption`.
* **Purpose:** Injected directly into `/system/etc/security/otacerts.zip` inside the recovery ramdisk. This authorizes recovery to verify and install custom ROM update packages (`.zip`) created and signed with your corresponding private OTA key, enabling fully automated, prompt-free OTA updates.

---

## 🛠️ How to Generate Your Own Keys

Run these terminal commands from inside the `recovery_patcher/` directory:

### Step 1: Generate AVB Signing Key (`keys/avb_key.pem`)
Generates an unencrypted 4096-bit RSA private key in PEM format:
```bash
openssl genrsa -out keys/avb_key.pem 4096
```
*(Alternatively, to use the standard Google AOSP / Lineage test key:)*
```bash
curl -sSL "https://android.googlesource.com/platform/external/avb/+/refs/heads/main/test/data/testkey_rsa4096.pem?format=TEXT" | base64 --decode > keys/avb_key.pem
```

### Step 2: Generate OTA Verification Certificate (`keys/ota_key.x509.pem`)
Generates a matching keypair (private signing key + public X.509 certificate valid for ~27 years):
```bash
openssl req -new -x509 -nodes -newkey rsa:2048 -days 10000 \
  -subj "/C=US/ST=State/L=City/O=MyCustomROM/OU=OTA/CN=MyCustomROM OTA/emailAddress=ota@myrom.org" \
  -keyout keys/ota_private_key.key \
  -out keys/ota_key.x509.pem
```

*(Optional) Convert the private key to PKCS#8 `.pk8` format for signing ROM update zip files with Android `signapk` / AOSP release tools:*
```bash
openssl pkcs8 -in keys/ota_private_key.key -topk8 -outform DER -out keys/ota_private_key.pk8 -nocrypt
```
> **Security Note:** Keep `ota_private_key.key` and `ota_private_key.pk8` safe on your build machine to sign your ROM update `.zip` packages. Only the public certificate `ota_key.x509.pem` is embedded into the recovery image.

---

## ⚙️ Configuration (`config.json`)

```json
{
  "stock_recovery_tar": "stock_recovery.tar",
  "output_tar": "output/Project_Revive_Recovery_v9.tar",
  "branding": {
    "ro.lineage.version": "Project-Revive-20260903-gta4xlveu",
    "ro.lineage.display.version": "Project Revive Recovery v1.0",
    "ro.build.display.id": "Project Revive Recovery v1.0"
  },
  "ui_colors": {
    "recovery_selected_bg": [255, 255, 255],
    "recovery_selected_fg": "black",
    "recovery_unselected_bg": [22, 22, 22],
    "recovery_info_tags": [255, 32, 0],
    "fastboot_selected_bg": [255, 32, 0],
    "fastboot_selected_fg": "black",
    "fastboot_info_tags": [255, 255, 255]
  },
  "assets": {
    "res/images/logo_image.png": "assets/logo_image.png",
    "res/images/logo_image_switch.png": "assets/logo_image_switch.png",
    "res/images/fastbootd.png": "assets/fastbootd.png"
  },
  "keys": {
    "avb_signing_key": "keys/avb_key.pem",
    "ota_certificates": [
      "keys/ota_key.x509.pem"
    ],
    "zip_entry_datetime": [2026, 9, 3, 14, 40, 34]
  },
  "avb": {
    "partition_name": "recovery",
    "partition_size": 100663296,
    "algorithm": "SHA256_RSA4096",
    "rollback_index": 1,
    "rollback_index_location": 0,
    "fingerprint": "samsung/lineage_gta4xlveu/gta4xlveu:16/BP4A.251205.006/eng.daniel:userdebug/release-keys",
    "salt": "d2c18db4f9997952455808bb33637dc59ff99eb0f2df16ebed5dc0dc6d633a04"
  },
  "tar": {
    "deterministic_mtime": 1788435660,
    "uname": "nobody",
    "gname": "nogroup"
  }
}
```

---

## 🚀 How to Run

1. **Place your files:**
   * Place stock recovery as `stock_recovery.tar` in the folder.
   * Place custom PNGs into `assets/`.
   * Place your AVB key and OTA cert into `keys/`.
2. **Execute the script:**
   ```bash
   python3 patch_recovery.py
   ```
   Or with a custom configuration:
   ```bash
   python3 patch_recovery.py --config my_custom_config.json
   ```
3. **Flashing:**
   The output TAR archive is generated in `output/` (e.g. `output/Project_Revive_Recovery_v9.tar`).
   * Boot the tablet into **Download Mode** (`Power + Vol Down` or `adb reboot download`).
   * Open **Odin3**, place the `.tar` into the **AP** slot, and click **Start**.

---

## 🔬 Under the Hood: Why This Works

1. **In-Memory CPIO File Engine:**  
   Extracting an Android recovery ramdisk onto macOS or unprivileged Linux filesystems destroys root file ownership (converting `uid=0, gid=0` to user `501`) and corrupts permission bitmasks on critical binaries like `/init`. This script processes CPIO headers entirely in RAM, preserving original Linux filesystem semantics byte-for-byte.

2. **AOSP Header v2 Geometry Equation:**  
   Snapdragon 720G bootloaders (`abl`) strictly enforce mathematical alignment for Android Boot Header Version 2:
   $$\text{recovery\_dtbo\_offset} = \text{PAGE\_SIZE} + \text{pad}(\text{kernel\_size}, 4096) + \text{pad}(\text{ramdisk\_size}, 4096)$$
   $$\text{dtb\_offset} = \text{recovery\_dtbo\_offset} + \text{pad}(\text{recovery\_dtbo\_size}, 4096)$$
   If the ramdisk size changes (even by 1 byte) and the header offset is not recomputed to match the exact byte layout, the bootloader aborts boot with `CURRENT BINARY: Custom (0x32E)`. The patcher recomputes all offsets dynamically and regenerates the AOSP header SHA-1 digest across all components.

3. **ARM64 Binary UI Patching (`librecovery_ui.so`):**  
   Direct machine code surgery on `ScreenRecoveryUI::SetColor` modifies the native rendering registers:
   * Selected recovery menu bar: `#FFFFFF` (Solid White background) with `#000000` (Black text).
   * Selected fastboot menu bar: `#FF2000` (Crimson Red background) with `#000000` (Black text).
   * Unselected rows: `#161616` (Neutral Dark Charcoal).
   * Recovery info/device metadata tags: `#FF2000` (Clinical Red).
   * Fastboot info/device metadata tags: `#FFFFFF` (Crisp White).

4. **100% Bit-for-Bit Deterministic Verification:**  
   When configured with exact cryptographic salt and timestamps, this script produces an identical bit-for-bit clone of `Project_Revive_Recovery_v9.tar` down to the exact RSA signature and TAR checksums.

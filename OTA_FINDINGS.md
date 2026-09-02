# LineageOS 23 OTA Updater: Research & Implementation Guide

This document records the comprehensive findings, reverse-engineering results, and architecture required to integrate the official LineageOS 23 (Android 16) Updater into **QuantumROM** (Samsung One UI port for `SM-P613`).

---

## 1. LineageOS Updater Architecture

### Non-A/B Recovery Installation Flow
Unlike A/B devices that stream blocks into an inactive partition via `update_engine`, non-A/B devices (like the Galaxy Tab S6 Lite `gta4xlve` / `SM-P613`) use Android's traditional **Recovery System**:

```text
[LineageOS Updater App]
          │
          ▼  (1) Fetch JSON manifest via HTTPS
[GitHub Raw / OTA Server]
          │
          ▼  (2) Direct download zip with HTTP 302 redirects
[Local Storage: /data/lineageos_updates/]
          │
          ▼  (3) android.os.RecoverySystem.installPackage(context, updateFile)
[Android OS Framework]
          │  Writes "--update_package=/data/lineageos_updates/..." to /cache/recovery/command
          ▼  Reboots with reason "recovery-update"
[Recovery Environment (TWRP / Lineage / Custom)]
          │
          ▼  Executes update-binary & updater-script
[Flash super.img / boot.img into Partitions]
```

1. The app verifies the download (SHA-256 and size).
2. It calls `android.os.RecoverySystem.installPackage(context, updateFile)`.
3. The framework writes `--update_package=/path/to/update.zip` to `/cache/recovery/command`.
4. The framework reboots into recovery mode with the `recovery-update` reason flag.
5. The recovery environment executes `update-binary` and `updater-script` without requiring any root daemon.

---

## 2. Source Compilation vs Pre-built Extraction

### The Standalone Build Barrier
Attempting to compile LineageOS 23 (`lineage-23.2`) Updater outside of an AOSP tree fails with Gradle:
```text
Execution failed for task ':app:compileDebugKotlin'.
> Could not resolve all files for configuration ':app:debugCompileClasspath'.
   > File does not exist: system_libs/SettingsLib.jar
   > File does not exist: system_libs/SpaLib.jar
```
LineageOS 23 migrated the UI to Jetpack Compose and Google's internal **SpaLib** (`com.android.settingslib.spa.*`). These classes are private platform APIs generated during a full OS build (`out/soong/.intermediates/...`). 

### Extraction from Official Builds
The genuine, pre-compiled LineageOS 23 (Android 16) binary is packaged in official builds:
* **Target Partition:** `system_ext` (or `system` on non-split partition builds)
* **Binary Path:** `/system_ext/priv-app/Updater/Updater.apk`
* **Folder Name:** `Updater`
* **APK Name:** `Updater.apk`

---

## 3. Dynamic Server Configuration (Zero Recompilation)

LineageOS designed the Updater to be configured **entirely via system properties at runtime** (`UpdatesNetworkDataSource.kt`):

```kotlin
private val serverUrl: String
    get() {
        val base = DeviceInfoUtils.updaterUri.trim().ifEmpty {
            context.getString(R.string.updater_server_url)
        }
        require(base.startsWith("https://")) {
            "Update server URL must use HTTPS: $base"
        }
        return base
            .replace("{device}", DeviceInfoUtils.device)
            .replace("{type}", DeviceInfoUtils.releaseType.lowercase())
            .replace("{incr}", DeviceInfoUtils.buildVersionIncremental)
    }
```

### Supported Properties

| Property | Description | Example for SM-P613 |
| :--- | :--- | :--- |
| `lineage.updater.uri` | Full HTTPS endpoint URL | `https://raw.githubusercontent.com/tui2019/QuantumROM/main/ota/{device}.json` |
| `ro.lineage.device` | Device identifier (replaces `{device}`) | `SM-P613` |
| `ro.lineage.build.version`| ROM version display & match string | `23.2` |
| `ro.lineage.releasetype` | Channel identifier (replaces `{type}`) | `unofficial` |

> Note: The app enforces HTTPS via `require(base.startsWith("https://"))`. HTTP URLs will crash the network data source.

### Server Response JSON Schema
The app expects an array of update objects:
```json
[
  {
    "datetime": 1781858358,
    "version": "23.2",
    "type": "unofficial",
    "files": [
      {
        "filename": "QuantumROM-SM-P613-v1.0.zip",
        "url": "https://downloads.sourceforge.net/project/quantumrom/SM-P613/QuantumROM-SM-P613-v1.0.zip",
        "size": 3815542737,
        "sha256": "abcdef1234567890...",
        "os_patch_level": "2026-07-01",
        "os_sdk_level": 36
      }
    ]
  }
]
```

---

## 4. Samsung One UI Privileged Hurdles & Solutions

Installing the app on Samsung One UI required solving three distinct platform hurdles:

### Hurdle 1: Privileged Permissions Whitelist
* **Requirement:** Place `Updater.xml` into `/system/etc/permissions/Updater.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<permissions>
    <privapp-permissions package="org.lineageos.updater">
        <permission name="android.permission.ACCESS_CACHE_FILESYSTEM"/>
        <permission name="android.permission.MANAGE_USERS"/>
        <permission name="android.permission.REBOOT"/>
        <permission name="android.permission.RECOVERY"/>
        <permission name="android.permission.START_ACTIVITIES_FROM_BACKGROUND"/>
        <permission name="android.permission.WRITE_SECURE_SETTINGS"/>
    </privapp-permissions>
</permissions>
```

### Hurdle 2: Samsung's Proprietary System Preload Whitelist
* **Problem:** Even with valid privapp permissions, Samsung's `PackageManagerService` rejected the package on boot:
  ```text
  PackageManager: Package is not in allowed list : org.lineageos.updater
  ```
* **Discovery:** Disassembling Samsung's `services.jar` revealed that `InstallPackageHelper;->addForInitLI` checks `systemConfig.mAllowedSystemPreloadApps`. If a system package is not present in that list, Samsung silences and discards the package entirely.
* **Solution:** Create `/system/etc/sysconfig/lineage_updater.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<config>
    <allowed-system-preload package="org.lineageos.updater" />
</config>
```

### Hurdle 3: Storage Directory (`/data/lineageos_updates`)
* **Problem:** When downloading or importing a local update, the app threw:
  ```text
  java.io.FileNotFoundException: /data/lineageos_updates/localUpdate.zip: open failed: ENOENT
  ```
* **Cause:** LineageOS hardcodes `R.string.download_path` to `/data/lineageos_updates/`. On official LineageOS, this is created by `init.rc`. Samsung One UI's `init` does not create it.
* **Solution:** Ensure `/data/lineageos_updates` exists with mode `0777` (or owned by `system:system`).

---

## 5. Local Update Import vs Remote Server OTA

| Feature | "Install local update" (File Picker) | Remote OTA (Server JSON) |
| :--- | :--- | :--- |
| **Trigger** | User picks a local file via DocumentsUI | App fetches `lineage.updater.uri` |
| **Storage Destination** | Copied into `/data/lineageos_updates/localUpdate.zip` | Streamed into `/data/lineageos_updates/<filename>.zip` |
| **Metadata Source**| Read from `META-INF/com/android/metadata.pb` inside the zip | Read from `files` fields in `updates.json` |
| **Crypto Verification** | Calls `RecoverySystem.verifyPackage(otacerts.zip)` | Verified via SHA-256 in manifest |
| **Failure Behavior** | Fails with `Exception: Verification failed, file has been deleted` if unsigned | Installs via `RecoverySystem.installPackage()` once SHA matches |
| **Suitability** | Requires full signed AOSP OTA package | Works with flashable zip containing raw `super.img` |

### Live Test Log of Local Import Failure:
```text
09-02 19:45:15.325  7814 10741 E UpdateImporter: Failed to import update package
09-02 19:45:15.325  7814 10741 E UpdateImporter: java.lang.Exception: Verification failed, file has been deleted
	at org.lineageos.updater.UpdateImporter$$ExternalSyntheticLambda0.run(...)
```
1. File copying succeeded completely (took ~20 seconds to copy 3.6 GB to `/data/lineageos_updates/localUpdate.zip`).
2. Verification immediately failed because the recovery zip was created by `7z` in `make_flashable_zip.sh` without recovery signing (`SignApk` / `otacerts.zip`).
3. `UpdateImporter` deleted the file as required by Lineage security policy.

### Critical Android Framework Keystore Pitfall: Flat `otacerts.zip`
When building `/system/etc/security/otacerts.zip`, `RecoverySystem.getTrustedCerts` iterates over **every** entry in the zip and attempts to parse it as an X.509 certificate:
```java
for (ZipEntry entry : zip.entries()) {
    trusted.add((X509Certificate) cf.generateCertificate(zip.getInputStream(entry)));
}
```
If `otacerts.zip` contains directory entries (e.g. `build/`, `build/target/`), `generateCertificate` receives a 0-byte stream and throws:
`com.android.org.conscrypt.OpenSSLX509CertificateFactory$ParsingException: inStream is empty`.
**Rule:** `otacerts.zip` must always be created flat with `zip -0 -j otacerts.zip *.pem`.



---

## 6. Production Integration Blueprint (for `QuantumRom.sh`)

To permanently include the OTA system in all QuantumROM builds:

### 1. Copy Files into System Image Tree:
```bash
# In QuantumRom.sh:
mkdir -p "$FIRM_DIR/$TARGET_DEVICE/system/system/priv-app/Updater"
cp "$TOOLS_DIR/ota/Updater.apk" "$FIRM_DIR/$TARGET_DEVICE/system/system/priv-app/Updater/Updater.apk"

mkdir -p "$FIRM_DIR/$TARGET_DEVICE/system/system/etc/permissions"
cp "$TOOLS_DIR/ota/Updater.xml" "$FIRM_DIR/$TARGET_DEVICE/system/system/etc/permissions/Updater.xml"

mkdir -p "$FIRM_DIR/$TARGET_DEVICE/system/system/etc/sysconfig"
cp "$TOOLS_DIR/ota/lineage_updater.xml" "$FIRM_DIR/$TARGET_DEVICE/system/system/etc/sysconfig/lineage_updater.xml"
```

### 2. Append Properties to `/system/build.prop`:
```properties
lineage.updater.uri=https://raw.githubusercontent.com/tui2019/QuantumROM/main/ota/{device}.json
ro.lineage.device=SM-P613
ro.lineage.build.version=23.2
ro.lineage.releasetype=unofficial
```

### 3. Initialize `/data/lineageos_updates` on First Boot:
Add to the ROM's init rc or first-boot setup script:
```text
mkdir /data/lineageos_updates 0777 system system
```

---

## 7. Automated Release Pipeline

```text
[GitHub Actions CI]
        │
        ├─► Builds QuantumROM flashable recovery zip
        ├─► Calculates SHA-256 and File Size
        ├─► Uploads flashable zip to SourceForge FRS (rsync / sftp)
        └─► Commits updated ota/SM-P613.json to GitHub repository
                  │
                  ▼
[Tablet / User]
        │
        ├─► Checks update via https://raw.githubusercontent.com/.../ota/SM-P613.json
        ├─► Downloads zip from SourceForge (follows HTTP 302 redirect)
        ├─► Verifies SHA-256 matches manifest
        └─► Calls RecoverySystem.installPackage() and reboots to recovery
```

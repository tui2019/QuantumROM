#!/usr/bin/env python3
import os
import json
import urllib.request
import urllib.error

git_token = os.environ.get("GIT_TOKEN")
kernel_repo = os.environ.get("KERNEL_TARGET_REPO")
inputs_str = os.environ.get("INPUTS_JSON", "{}")

try:
    inputs = json.loads(inputs_str)
except Exception:
    inputs = {}

payload = {
    "trigger_rom": "true",
    "stock_device": inputs.get("STOCK_DEVICE", "SM-P613"),
    "target_device": inputs.get("TARGET_DEVICE", "SM-P620"),
    "target_csc": inputs.get("TARGET_DEVICE_CSC", "EUX"),
    "target_fw_version": inputs.get("TARGET_FW_VERSION", ""),
    "output_fs": inputs.get("OUTPUT_FILESYSTEM", "erofs"),
    "vendor_repo": inputs.get("VENDOR_REPO", "tui2019/vendor_samsung_gta4xlve"),
    "kernel_repo": inputs.get("KERNEL_REPO", "tui2019/android_kernel_samsung_sm7125"),
    "publish_release": inputs.get("PUBLISH_RELEASE", "False"),
    "compress_img_to_xz": inputs.get("COMPRESS_IMG_TO_XZ", "False"),
    "debloat_rom": inputs.get("DEBLOAT_ROM", "True"),
    "use_ui_8_tethering_apex": inputs.get("USE_UI_8_TETHERING_APEX", "False"),
    "add_china_smart_manager": inputs.get("ADD_CHINA_SMART_MANAGER", "False"),
    "add_samsung_flagship_apps": inputs.get("ADD_SAMSUNG_FLAGSHIP_APPS", "False"),
    "add_custom_features": inputs.get("ADD_CUSTOM_FEATURES", "True"),
    "patch_flag_secure": inputs.get("PATCH_FLAG_SECURE", "False"),
    "patch_secure_folder": inputs.get("PATCH_SECURE_FOLDER", "True"),
    "patch_bluetooth_library": inputs.get("PATCH_BLUETOOTH_LIBRARY", "True"),
}

body = json.dumps({
    "event_type": "build-kernel",
    "client_payload": payload
}).encode('utf-8')

req = urllib.request.Request(
    f"https://api.github.com/repos/{kernel_repo}/dispatches",
    data=body,
    headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {git_token}",
        "Content-Type": "application/json"
    }
)

try:
    with urllib.request.urlopen(req) as resp:
        print(f"✅ Successfully dispatched kernel build! HTTP Code: {resp.status}")
except urllib.error.HTTPError as e:
    print(f"❌ Failed to trigger kernel repository dispatch. HTTP Code: {e.code}")
    print(e.read().decode('utf-8', errors='ignore'))
    exit(1)

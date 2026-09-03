#!/bin/bash
set -eo pipefail

# Required environment variables:
# ZIP_PATH, ZIP_NAME, ROM_VERSION, STOCK_DEVICE, TARGET_DEVICE, BUILD_TIME
# SF_SSH_KEY, SF_USERNAME, SF_PROJECT
# Optional: GIT_TOKEN (or GH_TOKEN)

ROM_VERSION="${ROM_VERSION:-16.2}"
DATE_TAG="$(date '+%Y%m%d')"
SF_PROJECT="${SF_PROJECT:-project-revive}"
SF_DIR_NAME="p613"

if [ -z "$ZIP_PATH" ] || [ ! -f "$ZIP_PATH" ]; then
    echo "[!] Error: ZIP_PATH '$ZIP_PATH' not found."
    exit 1
fi

ZIP_NAME="${ZIP_NAME:-$(basename "$ZIP_PATH")}"
FILE_SIZE_BYTES=$(stat -c%s "$ZIP_PATH" 2>/dev/null || stat -f%z "$ZIP_PATH")
FILE_SIZE_HUMAN=$(du -h "$ZIP_PATH" | cut -f1)
SHA256_SUM=$(sha256sum "$ZIP_PATH" | awk '{print $1}')
MD5_SUM=$(md5sum "$ZIP_PATH" | awk '{print $1}')
UNIX_TIMESTAMP=$(date +%s)

echo "=============================================="
echo " Packaging & Release for: $ZIP_NAME"
echo " Size: $FILE_SIZE_HUMAN ($FILE_SIZE_BYTES bytes)"
echo " SHA-256: $SHA256_SUM"
echo " MD5: $MD5_SUM"
echo "=============================================="

# 1. Upload to SourceForge
DOWNLOAD_URL="https://downloads.sourceforge.net/project/${SF_PROJECT}/${SF_DIR_NAME}/${ZIP_NAME}"

if [ -n "$SF_SSH_KEY" ] && [ -n "$SF_USERNAME" ]; then
    echo "[*] Setting up SSH credentials for SourceForge..."
    mkdir -p ~/.ssh
    chmod 700 ~/.ssh
    echo "$SF_SSH_KEY" > ~/.ssh/id_sf_ed25519
    chmod 600 ~/.ssh/id_sf_ed25519
    ssh-keyscan -H frs.sourceforge.net >> ~/.ssh/known_hosts 2>/dev/null || true

    REMOTE_PATH="/home/frs/project/${SF_PROJECT}/${SF_DIR_NAME}"
    echo "[*] Uploading $ZIP_NAME to SourceForge ($REMOTE_PATH)..."
    ssh -i ~/.ssh/id_sf_ed25519 -o StrictHostKeyChecking=no "$SF_USERNAME@frs.sourceforge.net" "mkdir -p $REMOTE_PATH" 2>/dev/null || true
    rsync -avP -e "ssh -i ~/.ssh/id_sf_ed25519 -o StrictHostKeyChecking=no" "$ZIP_PATH" "$SF_USERNAME@frs.sourceforge.net:${REMOTE_PATH}/${ZIP_NAME}"
    echo "[+] Upload to SourceForge completed successfully!"
    echo "[+] Direct Download: $DOWNLOAD_URL"
else
    echo "[!] Warning: SF_SSH_KEY or SF_USERNAME not set. Skipping SourceForge upload."
fi

# 2. Automatically update server-side OTA JSON configs (ota/p613.json & ota/SM-P613.json)
echo "[*] Updating server-side OTA configuration..."
python3 - <<EOF
import json, os

new_entry = {
    "datetime": int("$UNIX_TIMESTAMP"),
    "filename": "$ZIP_NAME",
    "id": "projectrevive_${ROM_VERSION}_${DATE_TAG}",
    "romtype": "unofficial",
    "size": int("$FILE_SIZE_BYTES"),
    "url": "$DOWNLOAD_URL",
    "version": "$ROM_VERSION"
}

for ota_file in ["ota/p613.json", "ota/SM-P613.json"]:
    os.makedirs(os.path.dirname(ota_file), exist_ok=True)
    data = {"response": []}
    if os.path.exists(ota_file):
        try:
            with open(ota_file, "r") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict) and "response" in loaded:
                    data = loaded
                elif isinstance(loaded, list):
                    data = {"response": loaded}
        except Exception as e:
            print(f"Notice: could not parse existing {ota_file}: {e}")

    # Remove existing entry with same filename if re-uploading
    filtered = [e for e in data.get("response", []) if e.get("filename") != "$ZIP_NAME"]
    # Prepend newest build to top of array
    filtered.insert(0, new_entry)
    data["response"] = filtered

    with open(ota_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Updated {ota_file}")
EOF

# 3. Commit and push updated OTA JSON back to git repository
if [ -d ".git" ]; then
    echo "[*] Committing updated OTA JSON configuration to git..."
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add ota/p613.json ota/SM-P613.json || true
    if ! git diff --cached --quiet; then
        git commit -m "chore(ota): release $ZIP_NAME" || true
        # Push with retry
        for attempt in 1 2 3; do
            git pull --rebase origin main || true
            if git push origin main; then
                echo "[+] Successfully pushed updated OTA config to GitHub!"
                break
            fi
            sleep 2
        done
    else
        echo "[i] No changes detected in OTA JSON."
    fi
fi

# 4. Create GitHub Release
GIT_AUTH_TOKEN="${GIT_TOKEN:-${GH_TOKEN:-}}"
if [ -n "$GIT_AUTH_TOKEN" ]; then
    TAG_NAME="v${ROM_VERSION}-${DATE_TAG}"
    RELEASE_TITLE="Project Revive ${ROM_VERSION} (${STOCK_DEVICE})"

    RELEASE_BODY="### 🚀 Project Revive ${ROM_VERSION}
Ported from **${TARGET_DEVICE}** for **${STOCK_DEVICE}**.

#### 📦 Download:
* **SourceForge Mirror:** [${ZIP_NAME}](${DOWNLOAD_URL})

#### 📊 Build Details:
* **Filename:** \`${ZIP_NAME}\`
* **Size:** ${FILE_SIZE_HUMAN} (${FILE_SIZE_BYTES} bytes)
* **Build Time:** ${BUILD_TIME}
* **SHA-256:** \`${SHA256_SUM}\`
* **MD5:** \`${MD5_SUM}\`

#### 📱 ROM Specifications:
* **Target Model:** ${STOCK_DEVICE}
* **Base Firmware:** ${TARGET_DEVICE}
* **ROM Version:** ${ROM_VERSION}
* **Android Version:** ${ANDROID_VERSION:-16}
* **One UI Version:** ${ONE_UI_VERSION:-8.0}
* **Filesystem:** ${OUTPUT_FILESYSTEM:-erofs}

#### 🔄 OTA Updates:
This build supports automated in-app updates via the LineageOS Updater app.
"

    JSON_PAYLOAD=$(python3 -c "
import json
body = '''$RELEASE_BODY'''
print(json.dumps({
    'tag_name': '$TAG_NAME',
    'name': '$RELEASE_TITLE',
    'body': body,
    'draft': False,
    'prerelease': False
}))
")

    echo "[*] Publishing GitHub release: $RELEASE_TITLE ($TAG_NAME)..."
    curl -s -X POST "https://api.github.com/repos/${GITHUB_REPOSITORY}/releases" \
        -H "Authorization: token $GIT_AUTH_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$JSON_PAYLOAD" > /dev/null && echo "[+] GitHub Release published successfully!" || echo "[!] Failed to publish GitHub Release."
fi

echo "[SUCCESS] Build packaging, SourceForge upload, and OTA configuration completed!"

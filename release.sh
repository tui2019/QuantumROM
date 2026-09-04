#!/bin/bash
set -eo pipefail

# Environment variables:
# ZIP_PATH, ZIP_NAME, ROM_VERSION, STOCK_DEVICE, TARGET_DEVICE, BUILD_TIME
# PUBLISH_RELEASE ("True" or "False", default: "False")
# If PUBLISH_RELEASE == "True": SF_SSH_KEY, SF_USERNAME, SF_PROJECT
# Optional: GIT_TOKEN (or GH_TOKEN)

PUBLISH_RELEASE="${PUBLISH_RELEASE:-False}"
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
GIT_AUTH_TOKEN="${GIT_TOKEN:-${GH_TOKEN:-}}"

echo "=============================================="
echo " ROM Packaging & Release Manager"
echo " File: $ZIP_NAME"
echo " Size: $FILE_SIZE_HUMAN ($FILE_SIZE_BYTES bytes)"
echo " Mode: PUBLISH_RELEASE = $PUBLISH_RELEASE"
echo " SHA-256: $SHA256_SUM"
echo " MD5: $MD5_SUM"
echo "=============================================="

# ---------------------------------------------------------
# STEP 1: ALWAYS UPLOAD TO GOFILE (Fast Direct Mirror)
# ---------------------------------------------------------
echo "[*] Uploading $ZIP_NAME to GoFile for fast direct downloads..."
GOFILE_LINK=""
if [ -f "upload.sh" ]; then
    GOFILE_LINK=$(bash upload.sh "$ZIP_PATH" | tail -n 1 || true)
fi

if [ -n "$GOFILE_LINK" ] && [[ "$GOFILE_LINK" == http* ]]; then
    echo "=============================================="
    echo " ⚡ GoFile Fast Download: $GOFILE_LINK"
    echo "=============================================="
else
    echo "[!] Notice: GoFile upload did not return a valid URL (got: '$GOFILE_LINK')."
    GOFILE_LINK=""
fi


# ---------------------------------------------------------
# STEP 2: HANDLE PUBLISH_RELEASE (SourceForge + OTA Config)
# ---------------------------------------------------------
if [ "$PUBLISH_RELEASE" = "True" ]; then
    echo ">>> [MODE: OFFICIAL RELEASE] Uploading to SourceForge & updating OTA configuration..."

    DOWNLOAD_URL="https://downloads.sourceforge.net/project/${SF_PROJECT}/${SF_DIR_NAME}/${ZIP_NAME}"

    # 1. Upload to SourceForge
    if [ -n "$SF_SSH_KEY" ] && [ -n "$SF_USERNAME" ]; then
        echo "[*] Setting up SSH credentials for SourceForge..."
        mkdir -p ~/.ssh
        chmod 700 ~/.ssh
        echo "$SF_SSH_KEY" > ~/.ssh/id_sf_ed25519
        chmod 600 ~/.ssh/id_sf_ed25519
        ssh-keyscan -H frs.sourceforge.net >> ~/.ssh/known_hosts 2>/dev/null || true

        REMOTE_BASE="/home/frs/project/${SF_PROJECT}"
        echo "[*] Uploading $ZIP_NAME to SourceForge (${REMOTE_BASE}/${SF_DIR_NAME}/)..."

        TEMP_STAGE="$(mktemp -d)"
        mkdir -p "${TEMP_STAGE}/${SF_DIR_NAME}"
        ln -s "$ZIP_PATH" "${TEMP_STAGE}/${SF_DIR_NAME}/${ZIP_NAME}" 2>/dev/null || cp "$ZIP_PATH" "${TEMP_STAGE}/${SF_DIR_NAME}/${ZIP_NAME}"

        rsync -avPL -e "ssh -i ~/.ssh/id_sf_ed25519 -o StrictHostKeyChecking=no" \
            "${TEMP_STAGE}/${SF_DIR_NAME}" \
            "$SF_USERNAME@frs.sourceforge.net:${REMOTE_BASE}/"

        rm -rf "$TEMP_STAGE"
        echo "[+] Upload to SourceForge completed successfully!"
        echo "[+] Direct Download URL: $DOWNLOAD_URL"
    else
        echo "[!] Warning: SF_SSH_KEY or SF_USERNAME not set. Skipping SourceForge upload."
    fi

    # 2. Update server-side OTA JSON configs
    echo "[*] Updating server-side OTA configuration..."
    python3 - <<EOF
import json, os

new_entry = {
    "datetime": int("$UNIX_TIMESTAMP"),
    "type": "unofficial",
    "version": "$ROM_VERSION",
    "files": [
        {
            "filename": "$ZIP_NAME",
            "url": "$DOWNLOAD_URL",
            "size": int("$FILE_SIZE_BYTES"),
            "sha256": "$SHA256_SUM"
        }
    ]
}

for ota_file in ["ota/p613.json", "ota/SM-P613.json"]:
    os.makedirs(os.path.dirname(ota_file), exist_ok=True)
    data = []
    if os.path.exists(ota_file):
        try:
            with open(ota_file, "r") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    data = loaded
                elif isinstance(loaded, dict) and "response" in loaded:
                    data = []
                    for item in loaded["response"]:
                        data.append({
                            "datetime": item.get("datetime", int("$UNIX_TIMESTAMP")),
                            "type": item.get("romtype", "unofficial"),
                            "version": item.get("version", "$ROM_VERSION"),
                            "files": [
                                {
                                    "filename": item.get("filename", ""),
                                    "url": item.get("url", ""),
                                    "size": item.get("size", 0),
                                    "sha256": item.get("sha256", "")
                                }
                            ]
                        })
        except Exception as e:
            print(f"Notice: could not parse existing {ota_file}: {e}")

    # Remove existing entry with identical filename if rebuilding/re-uploading
    filtered = [e for e in data if not any(f.get("filename") == "$ZIP_NAME" for f in e.get("files", []))]
    # Prepend newest build to top of array, keeping all older releases intact
    filtered.insert(0, new_entry)

    with open(ota_file, "w") as f:
        json.dump(filtered, f, indent=2)
    print(f"[+] Updated {ota_file} (Total releases in history: {len(filtered)})")
EOF

    # 3. Also sync p613.json to SourceForge for visibility
    if [ -n "$SF_SSH_KEY" ] && [ -n "$SF_USERNAME" ] && [ -f "ota/p613.json" ]; then
        echo "[*] Syncing ota/p613.json to SourceForge..."
        scp -i ~/.ssh/id_sf_ed25519 -o StrictHostKeyChecking=no \
            "ota/p613.json" "$SF_USERNAME@frs.sourceforge.net:${REMOTE_BASE}/${SF_DIR_NAME}/p613.json" || true
    fi

    # 4. Commit and push updated OTA JSON back to git repository
    if [ -d ".git" ]; then
        echo "[*] Committing updated OTA JSON configuration to git..."
        git config user.name "github-actions[bot]"
        git config user.email "github-actions[bot]@users.noreply.github.com"
        git add ota/p613.json ota/SM-P613.json || true
        if ! git diff --cached --quiet; then
            git commit -m "chore(ota): release $ZIP_NAME" || true
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

    # 5. Create Official GitHub Release with BOTH mirrors
    if [ -n "$GIT_AUTH_TOKEN" ]; then
        TAG_NAME="v${ROM_VERSION}-${DATE_TAG}"
        RELEASE_TITLE="Project Revive ${ROM_VERSION} (${STOCK_DEVICE})"

        DOWNLOAD_LINKS="* **SourceForge (Official & OTA Mirror):** [${ZIP_NAME}](${DOWNLOAD_URL})"
        if [ -n "$GOFILE_LINK" ]; then
            DOWNLOAD_LINKS="* **GoFile (Fast Direct Download):** [${ZIP_NAME}](${GOFILE_LINK})
* **SourceForge (Official & OTA Mirror):** [${ZIP_NAME}](${DOWNLOAD_URL})"
        fi

        RELEASE_BODY="### 🚀 Project Revive ${ROM_VERSION}
Ported from **${TARGET_DEVICE}** for **${STOCK_DEVICE}**.

#### 📦 Downloads:
${DOWNLOAD_LINKS}

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

    echo "[SUCCESS] Official release published to SourceForge & OTA config updated!"

else
    echo ">>> [MODE: TEST BUILD] PUBLISH_RELEASE is False."

    DOWNLOAD_MD="* **Download (GoFile):** \`GoFile upload unavailable\`"
    if [ -n "$GOFILE_LINK" ]; then
        DOWNLOAD_MD="* **Download (GoFile):** [$ZIP_NAME]($GOFILE_LINK)"
    fi

    if [ -n "$GITHUB_STEP_SUMMARY" ]; then
        {
            echo "### 🧪 Test Build Completed"
            echo "$DOWNLOAD_MD"
            echo "* **Size:** $FILE_SIZE_HUMAN"
            echo "* **SHA-256:** \`$SHA256_SUM\`"
            echo ""
            echo "> [!NOTE]"
            echo "> This build was created in test mode (\`PUBLISH_RELEASE=False\`). It was not published to SourceForge or the OTA update channel."
        } >> "$GITHUB_STEP_SUMMARY"
    fi

    # Create GitHub Release for Test Build
    if [ -n "$GIT_AUTH_TOKEN" ]; then
        TAG_NAME="test-${STOCK_DEVICE}-${UNIX_TIMESTAMP}"
        RELEASE_TITLE="Test Build: ${ZIP_NAME}"

        RELEASE_BODY="### 🧪 Project Revive ${ROM_VERSION} (Test Build)
Ported from **${TARGET_DEVICE}** for **${STOCK_DEVICE}**.

#### 📦 Download:
${DOWNLOAD_MD}

#### 📊 Build Details:
* **Filename:** \`${ZIP_NAME}\`
* **Size:** ${FILE_SIZE_HUMAN} (${FILE_SIZE_BYTES} bytes)
* **Build Time:** ${BUILD_TIME}
* **SHA-256:** \`${SHA256_SUM}\`
* **MD5:** \`${MD5_SUM}\`

> [!NOTE]
> This is a test/staging build. It was not pushed to the public OTA channel or SourceForge.
"

        JSON_PAYLOAD=$(python3 -c "
import json
body = '''$RELEASE_BODY'''
print(json.dumps({
    'tag_name': '$TAG_NAME',
    'name': '$RELEASE_TITLE',
    'body': body,
    'draft': False,
    'prerelease': True
}))
")

        echo "[*] Publishing test GitHub release: $RELEASE_TITLE ($TAG_NAME)..."
        curl -s -X POST "https://api.github.com/repos/${GITHUB_REPOSITORY}/releases" \
            -H "Authorization: token $GIT_AUTH_TOKEN" \
            -H "Content-Type: application/json" \
            -d "$JSON_PAYLOAD" > /dev/null && echo "[+] Test GitHub Release published successfully!" || echo "[!] Failed to publish GitHub Release."
    fi

    echo "[SUCCESS] Test build processed!"
fi

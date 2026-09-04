#!/bin/bash
set -eo pipefail

if [[ "$#" == '0' ]]; then
    echo "[-] ERROR: No File Specified!" && exit 1
fi

FILE="$1"
if [ ! -f "$FILE" ]; then
    echo "[-] ERROR: File '$FILE' not found!" && exit 1
fi

echo "[*] Querying GoFile server..."
SERVER=$(curl -s https://api.gofile.io/servers | jq -r '.data.servers[0].name // empty')
if [ -z "$SERVER" ] || [ "$SERVER" == "null" ]; then
    SERVER="store1"
fi
echo "[*] Selected GoFile server: $SERVER"

echo "[*] Uploading $(basename "$FILE") to GoFile..."
RESPONSE=$(curl -# -F "file=@$FILE" "https://${SERVER}.gofile.io/uploadFile")

LINK=$(echo "$RESPONSE" | jq -r '.data.downloadPage // empty')

if [ -z "$LINK" ] || [ "$LINK" == "null" ]; then
    echo "[-] Error uploading to GoFile: $RESPONSE"
    exit 1
fi

echo "[+] Upload complete!"
echo "$LINK"

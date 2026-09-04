#!/usr/bin/env python3
"""
Project Revive - Automated Recovery Patcher
Author: Antigravity & Project Revive Team
Description:
    Fully automated, bit-accurate recovery patching engine for Samsung / Qualcomm devices.
    Performs in-memory CPIO ramdisk surgery, ARM64 UI opcode customization,
    AOSP Header v2 geometry alignment, AVB cryptographic re-signing, and GNU TAR packaging.
"""

import sys
import os
import json
import gzip
import io
import struct
import tarfile
import hashlib
import subprocess
import zipfile
import argparse
import time

PAGE_SIZE = 4096

def parse_cpio(data):
    """Parses a newc (070701) format CPIO archive in-memory into structured entries."""
    entries = []
    pos = 0
    while pos < len(data) - 110:
        magic = data[pos:pos+6]
        if magic != b'070701':
            break
        ino = int(data[pos+6:pos+14], 16)
        mode = int(data[pos+14:pos+22], 16)
        uid = int(data[pos+22:pos+30], 16)
        gid = int(data[pos+30:pos+38], 16)
        nlink = int(data[pos+38:pos+46], 16)
        mtime = int(data[pos+46:pos+54], 16)
        filesize = int(data[pos+54:pos+62], 16)
        devmajor = int(data[pos+62:pos+70], 16)
        devminor = int(data[pos+70:pos+78], 16)
        rdevmajor = int(data[pos+78:pos+86], 16)
        rdevminor = int(data[pos+86:pos+94], 16)
        namesize = int(data[pos+94:pos+102], 16)
        check = int(data[pos+102:pos+110], 16)
        
        name = data[pos+110 : pos+110+namesize-1].decode('latin1')
        pos_after_name = pos + 110 + namesize
        name_pad = (4 - (pos_after_name % 4)) % 4
        file_start = pos_after_name + name_pad
        content = data[file_start : file_start + filesize]
        file_pad = (4 - ((file_start + filesize) % 4)) % 4
        
        entries.append({
            'ino': ino, 'mode': mode, 'uid': uid, 'gid': gid,
            'nlink': nlink, 'mtime': mtime, 'filesize': filesize,
            'devmajor': devmajor, 'devminor': devminor,
            'rdevmajor': rdevmajor, 'rdevminor': rdevminor,
            'namesize': namesize, 'check': check,
            'name': name, 'content': content
        })
        pos = file_start + filesize + file_pad
        if name == 'TRAILER!!!':
            break
    return entries

def write_cpio(entries):
    """Serializes in-memory entries back into an exact byte-aligned CPIO newc byte stream."""
    out = io.BytesIO()
    for e in entries:
        content = e['content']
        filesize = len(content)
        name_bytes = e['name'].encode('latin1') + b'\x00'
        namesize = len(name_bytes)
        hdr = (
            f"070701"
            f"{e['ino']:08x}"
            f"{e['mode']:08x}"
            f"{e['uid']:08x}"
            f"{e['gid']:08x}"
            f"{e['nlink']:08x}"
            f"{e['mtime']:08x}"
            f"{filesize:08x}"
            f"{e['devmajor']:08x}"
            f"{e['devminor']:08x}"
            f"{e['rdevmajor']:08x}"
            f"{e['rdevminor']:08x}"
            f"{namesize:08x}"
            f"{e['check']:08x}"
        ).encode('ascii')
        out.write(hdr)
        out.write(name_bytes)
        n_pad = (4 - ((110 + namesize) % 4)) % 4
        out.write(b'\x00' * n_pad)
        out.write(content)
        f_pad = (4 - (filesize % 4)) % 4
        out.write(b'\x00' * f_pad)
    val = out.getvalue()
    rem = len(val) % 512
    if rem != 0:
        val += b'\x00' * (512 - rem)
    return val

def patch_ui_library(so_bytes):
    """Patches ARM64 opcodes in ScreenRecoveryUI::SetColor for custom monochrome/red palette."""
    data = bytearray(so_bytes)
    
    # 1. Recovery selected menu background -> Solid White (255, 255, 255, 255)
    # At 0x24050: mov w0, #0xff; mov w1, #0xff
    data[0x24050:0x24054] = bytes([0xe0, 0x1f, 0x80, 0x52])
    data[0x24054:0x24058] = bytes([0xe1, 0x1f, 0x80, 0x52])
    
    # 2. Fastboot selected menu background -> Crimson Red (255, 32, 0, 255)
    # At 0x23f70: mov w0, #0xff; mov w1, #0x20
    data[0x23f70:0x23f74] = bytes([0xe0, 0x1f, 0x80, 0x52])
    data[0x23f74:0x23f78] = bytes([0x01, 0x04, 0x80, 0x52])
    
    # 3. Selected menu text -> Solid Black for both Recovery and Fastboot
    # At 0x24004: replace b.ne with NOP to fall through to 0x24008 (wzr, wzr, wzr, 0xff)
    data[0x24004:0x24008] = bytes([0x1f, 0x20, 0x03, 0xd5])
    
    # 4. Unselected rows background -> Neutral Dark Charcoal (#161616)
    # At 0x240a0: mov w0, #0x16; mov w1, #0x16; mov w2, #0x16
    data[0x240a0:0x240a4] = bytes([0xc0, 0x02, 0x80, 0x52])
    data[0x240a4:0x240a8] = bytes([0xc1, 0x02, 0x80, 0x52])
    data[0x240a8:0x240ac] = bytes([0xc2, 0x02, 0x80, 0x52])
    
    # 5. Top-left version/info tags (w1 == 1):
    # - Fastboot: Pure Crisp White (255, 255, 255)
    data[0x23fb8:0x23fbc] = bytes([0xe0, 0x1f, 0x80, 0x52]) # mov w0, #0xff
    data[0x23fbc:0x23fc0] = bytes([0xe1, 0x1f, 0x80, 0x52]) # mov w1, #0xff
    data[0x23fc0:0x23fc4] = bytes([0x26, 0x00, 0x00, 0x14]) # b 0x24058
    
    # - Recovery: Vibrant Clinical Red (255, 32, 0)
    data[0x24044:0x24048] = bytes([0xe0, 0x1f, 0x80, 0x52]) # mov w0, #0xff
    data[0x24048:0x2404c] = bytes([0x01, 0x04, 0x80, 0x52]) # mov w1, #0x20
    data[0x2404c:0x24050] = bytes([0xf1, 0xff, 0xff, 0x17]) # b 0x24010
    
    return bytes(data)

def build_aosp_recovery(kernel_data, ramdisk_data, dtbo_data, dtb_data, orig_header):
    """Assembles Android Boot Header v2 payload with strictly aligned dynamic geometry."""
    k_pad = ((len(kernel_data) + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
    r_pad = ((len(ramdisk_data) + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
    dtbo_pad = ((len(dtbo_data) + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
    dtb_pad = ((len(dtb_data) + PAGE_SIZE - 1) // PAGE_SIZE) * PAGE_SIZE
    
    dtbo_offset = PAGE_SIZE + k_pad + r_pad
    
    header = bytearray(orig_header[:PAGE_SIZE])
    header[8:12] = struct.pack('<I', len(kernel_data))
    header[16:20] = struct.pack('<I', len(ramdisk_data))
    header[1632:1636] = struct.pack('<I', len(dtbo_data))
    header[1636:1644] = struct.pack('<Q', dtbo_offset)
    header[1648:1652] = struct.pack('<I', len(dtb_data))
    header[1652:1660] = struct.pack('<Q', 0x1f00000)
    
    sha = hashlib.sha1()
    sha.update(kernel_data)
    sha.update(struct.pack('I', len(kernel_data)))
    sha.update(ramdisk_data)
    sha.update(struct.pack('I', len(ramdisk_data)))
    sha.update(struct.pack('I', 0))
    sha.update(dtbo_data)
    sha.update(struct.pack('I', len(dtbo_data)))
    sha.update(dtb_data)
    sha.update(struct.pack('I', len(dtb_data)))
    header[576:596] = sha.digest()
    header[596:608] = b'\x00' * 12
    
    payload = (
        header +
        kernel_data + b'\x00' * (k_pad - len(kernel_data)) +
        ramdisk_data + b'\x00' * (r_pad - len(ramdisk_data)) +
        dtbo_data + b'\x00' * (dtbo_pad - len(dtbo_data)) +
        dtb_data + b'\x00' * (dtb_pad - len(dtb_data))
    )
    return payload, dtbo_offset

def main():
    parser = argparse.ArgumentParser(description="Automated Bit-Accurate Android Recovery Patcher")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, args.config)
    if not os.path.exists(config_path):
        print(f"[-] Error: Config file not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r") as f:
        cfg = json.load(f)

    stock_tar_path = os.path.normpath(os.path.join(base_dir, cfg["stock_recovery_tar"]))
    out_tar_path = os.path.normpath(os.path.join(base_dir, cfg["output_tar"]))
    os.makedirs(os.path.dirname(out_tar_path), exist_ok=True)

    print(f"[*] Opening stock recovery archive: {stock_tar_path}")
    t_orig = tarfile.open(stock_tar_path)
    rec_bytes = t_orig.extractfile("recovery.img").read()
    vb_bytes = t_orig.extractfile("vbmeta.img").read()

    k_sz = struct.unpack('<I', rec_bytes[8:12])[0]
    r_sz = struct.unpack('<I', rec_bytes[16:20])[0]
    dtbo_sz = struct.unpack('<I', rec_bytes[1632:1636])[0]
    dtbo_off = struct.unpack('<Q', rec_bytes[1636:1644])[0]
    dtb_sz = struct.unpack('<I', rec_bytes[1648:1652])[0]

    k_data = rec_bytes[PAGE_SIZE : PAGE_SIZE + k_sz]
    r_off = PAGE_SIZE + ((k_sz + PAGE_SIZE - 1)//PAGE_SIZE)*PAGE_SIZE
    r_data_unmod = rec_bytes[r_off : r_off + r_sz]
    dtbo_data = rec_bytes[dtbo_off : dtbo_off + dtbo_sz]
    dtb_off = dtbo_off + ((dtbo_sz + PAGE_SIZE - 1)//PAGE_SIZE)*PAGE_SIZE
    dtb_data = rec_bytes[dtb_off : dtb_off + dtb_sz]

    print("[*] Decompressing stock CPIO ramdisk in RAM...")
    r_cpio_raw = gzip.decompress(r_data_unmod)
    entries = parse_cpio(r_cpio_raw)
    print(f"[+] Successfully parsed {len(entries)} CPIO entries with native root UID/GID.")

    # 1. Update Assets
    for target_name, rel_asset_path in cfg.get("assets", {}).items():
        full_asset_path = os.path.join(base_dir, rel_asset_path)
        if os.path.exists(full_asset_path):
            with open(full_asset_path, "rb") as af:
                asset_content = af.read()
            found = False
            for e in entries:
                if e["name"] == target_name:
                    e["content"] = asset_content
                    e["filesize"] = len(asset_content)
                    found = True
                    print(f"[+] Replaced asset '{target_name}' with {full_asset_path} ({len(asset_content)} bytes)")
                    break
            if not found:
                print(f"[!] Warning: Target entry '{target_name}' not found in ramdisk.")
        else:
            print(f"[i] Notice: Asset '{rel_asset_path}' not found in assets/ -> Retaining stock LineageOS graphic for '{target_name}'.")

    # 2. Patch UI Colors in librecovery_ui.so
    so_entry = next((e for e in entries if e["name"] == "system/lib64/librecovery_ui.so"), None)
    if so_entry:
        print("[*] Applying ARM64 color palette opcodes to librecovery_ui.so...")
        patched_so = patch_ui_library(so_entry["content"])
        so_entry["content"] = patched_so
        so_entry["filesize"] = len(patched_so)
        print("[+] librecovery_ui.so successfully patched.")

    # 3. Update OTA Certificates
    ota_certs_to_add = cfg.get("keys", {}).get("ota_certificates", [])
    if ota_certs_to_add:
        otacerts_entry = next((e for e in entries if e["name"] == "system/etc/security/otacerts.zip"), None)
        if otacerts_entry:
            orig_zf = zipfile.ZipFile(io.BytesIO(otacerts_entry["content"]))
            bio = io.BytesIO()
            zip_dt_list = cfg.get("keys", {}).get("zip_entry_datetime")
            zip_dt = tuple(zip_dt_list) if zip_dt_list else None

            with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as new_zf:
                # Retain existing certs
                for name in orig_zf.namelist():
                    data = orig_zf.read(name)
                    if zip_dt:
                        zi = zipfile.ZipInfo(name, zip_dt)
                        zi.compress_type = zipfile.ZIP_DEFLATED
                        zi.external_attr = 0x1800000
                        new_zf.writestr(zi, data)
                    else:
                        new_zf.writestr(name, data)
                # Add new certs
                for cert_rel_path in ota_certs_to_add:
                    cert_full_path = os.path.join(base_dir, cert_rel_path)
                    if os.path.exists(cert_full_path):
                        with open(cert_full_path, "rb") as cf:
                            c_bytes = cf.read()
                        c_name = os.path.basename(cert_rel_path)
                        if zip_dt:
                            zi = zipfile.ZipInfo(c_name, zip_dt)
                            zi.compress_type = zipfile.ZIP_DEFLATED
                            zi.external_attr = 0x1800000
                            new_zf.writestr(zi, c_bytes)
                        else:
                            new_zf.writestr(c_name, c_bytes)
                        print(f"[+] Embedded OTA cert '{c_name}' into otacerts.zip")
            new_otacerts_bytes = bio.getvalue()
            otacerts_entry["content"] = new_otacerts_bytes
            otacerts_entry["filesize"] = len(new_otacerts_bytes)

    # 4. Update prop.default
    branding_dict = cfg.get("branding", {})
    if branding_dict:
        prop_entry = next((e for e in entries if e["name"] == "prop.default"), None)
        if prop_entry:
            lines = prop_entry["content"].decode("utf-8").splitlines(keepends=True)
            new_lines = []
            for l in lines:
                matched = False
                for k, v in branding_dict.items():
                    if l.startswith(f"{k}="):
                        new_lines.append(f"{k}={v}\n")
                        matched = True
                        break
                if not matched:
                    new_lines.append(l)
            prop_entry["content"] = "".join(new_lines).encode("utf-8")
            prop_entry["filesize"] = len(prop_entry["content"])
            print("[+] Updated prop.default branding properties.")

    # 5. Serialize and Compress Ramdisk
    print("[*] Re-serializing in-memory CPIO and compressing with gzip (mtime=0)...")
    new_cpio = write_cpio(entries)
    new_ramdisk_gz = gzip.compress(new_cpio, compresslevel=9, mtime=0)
    print(f"[+] Compressed ramdisk size: {len(new_ramdisk_gz)} bytes")

    # 6. Build AOSP Boot Header v2 Payload
    payload, dynamic_dtbo_off = build_aosp_recovery(k_data, new_ramdisk_gz, dtbo_data, dtb_data, rec_bytes[:PAGE_SIZE])
    print(f"[+] AOSP Geometry aligned: recovery_dtbo_offset = {dynamic_dtbo_off}")
    print(f"[+] Total recovery payload size: {len(payload)} bytes")

    temp_payload_path = os.path.normpath(os.path.join(base_dir, "output", "recovery_payload.tmp"))
    with open(temp_payload_path, "wb") as f:
        f.write(payload)

    # 7. AVB Signing
    avb_cfg = cfg.get("avb", {})
    avb_key_rel = cfg.get("keys", {}).get("avb_signing_key", "keys/avb_key.pem")
    avb_key_path = os.path.normpath(os.path.join(base_dir, avb_key_rel))
    avbtool_path = os.path.normpath(os.path.join(base_dir, "avbtool.py"))

    if not os.path.exists(avb_key_path):
        print(f"[i] Notice: AVB signing key not found at '{avb_key_path}'.")
        print(f"[*] Automatically generating a new standard RSA-4096 AVB key at '{avb_key_path}'...")
        os.makedirs(os.path.dirname(avb_key_path), exist_ok=True)
        subprocess.run(["openssl", "genrsa", "-out", avb_key_path, "4096"], check=True)
        print(f"[+] Successfully generated new AVB key: {avb_key_path}")

    cmd = [
        sys.executable, avbtool_path, "add_hash_footer",
        "--image", temp_payload_path,
        "--partition_size", str(avb_cfg.get("partition_size", 100663296)),
        "--partition_name", avb_cfg.get("partition_name", "recovery"),
        "--key", avb_key_path,
        "--algorithm", avb_cfg.get("algorithm", "SHA256_RSA4096"),
        "--rollback_index", str(avb_cfg.get("rollback_index", 1)),
        "--rollback_index_location", str(avb_cfg.get("rollback_index_location", 0)),
        "--prop", f"com.android.build.recovery.fingerprint:{avb_cfg.get('fingerprint', '')}"
    ]

    salt = avb_cfg.get("salt")
    if salt:
        cmd.extend(["--salt", salt])

    print("[*] Signing recovery image with AVB footer via avbtool...")
    subprocess.run(cmd, check=True)

    with open(temp_payload_path, "rb") as f:
        final_rec_bytes = f.read()
    os.remove(temp_payload_path)
    print(f"[+] Final signed recovery.img size: {len(final_rec_bytes)} bytes")

    # 8. Package into Odin GNU TAR
    tar_cfg = cfg.get("tar", {})
    tar_mtime = tar_cfg.get("deterministic_mtime", int(time.time()))
    uname = tar_cfg.get("uname", "nobody")
    gname = tar_cfg.get("gname", "nogroup")

    print(f"[*] Packaging into Odin GNU TAR: {out_tar_path}")
    with tarfile.open(out_tar_path, "w", format=tarfile.GNU_FORMAT) as t:
        ti_rec = tarfile.TarInfo("recovery.img")
        ti_rec.size = len(final_rec_bytes)
        ti_rec.mtime = tar_mtime
        ti_rec.mode = 0o644
        ti_rec.uname = uname
        ti_rec.gname = gname
        t.addfile(ti_rec, io.BytesIO(final_rec_bytes))

        ti_vb = tarfile.TarInfo("vbmeta.img")
        ti_vb.size = len(vb_bytes)
        ti_vb.mtime = tar_mtime
        ti_vb.mode = 0o644
        ti_vb.uname = uname
        ti_vb.gname = gname
        t.addfile(ti_vb, io.BytesIO(vb_bytes))

    print(f"[SUCCESS] Recovery package built: {out_tar_path}")
    sha256 = hashlib.sha256(open(out_tar_path, "rb").read()).hexdigest()
    print(f"[+] SHA-256: {sha256}")

if __name__ == "__main__":
    main()

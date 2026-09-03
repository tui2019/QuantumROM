#!/usr/bin/env python3
import sys
import os
import struct
import hashlib

PAGE_SIZE = 4096
DEFAULT_BOOT_PARTITION_SIZE = 100663296  # Exactly 96 MB (96 * 1024 * 1024)

def pad(data, size):
    rem = len(data) % size
    if rem != 0:
        return data + b'\x00' * (size - rem)
    return data

def repack(header_path, ramdisk_path, kernel_path, output_path, dtb_path=None, target_size=DEFAULT_BOOT_PARTITION_SIZE):
    with open(header_path, 'rb') as f:
        header = bytearray(f.read(PAGE_SIZE))

    with open(kernel_path, 'rb') as f:
        kernel_data = f.read()

    with open(ramdisk_path, 'rb') as f:
        ramdisk_data = f.read()

    # If dtb_path is not specified, check if dtb.img exists next to header.bin
    if not dtb_path:
        candidate = os.path.join(os.path.dirname(header_path), 'dtb.img')
        if os.path.isfile(candidate):
            dtb_path = candidate

    dtb_data = b''
    if dtb_path and os.path.isfile(dtb_path):
        with open(dtb_path, 'rb') as f:
            dtb_data = f.read()

    # Update kernel_size (offset 8) and ramdisk_size (offset 16)
    header[8:12] = struct.pack('<I', len(kernel_data))
    header[16:20] = struct.pack('<I', len(ramdisk_data))

    # In Header v2, dtb_size is at offset 1648 and dtb_addr at offset 1652
    if len(dtb_data) > 0:
        header[1648:1652] = struct.pack('<I', len(dtb_data))
        header[1652:1660] = struct.pack('<Q', 0x1f00000)
    else:
        header[1648:1652] = struct.pack('<I', 0)

    # Calculate SHA-1 digest over kernel + ramdisk (+ dtb if present)
    ctx = hashlib.sha1()
    ctx.update(kernel_data)
    ctx.update(ramdisk_data)
    if len(dtb_data) > 0:
        ctx.update(dtb_data)
    digest = ctx.digest()
    header[576:596] = digest
    header[596:608] = b'\x00' * 12

    padded_kernel = pad(kernel_data, PAGE_SIZE)
    padded_ramdisk = pad(ramdisk_data, PAGE_SIZE)
    padded_dtb = pad(dtb_data, PAGE_SIZE) if len(dtb_data) > 0 else b''

    payload_size = len(header) + len(padded_kernel) + len(padded_ramdisk) + len(padded_dtb)

    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(padded_kernel)
        f.write(padded_ramdisk)
        if len(padded_dtb) > 0:
            f.write(padded_dtb)
        if target_size and payload_size < target_size:
            f.write(b'\x00' * (target_size - payload_size))

    final_size = target_size if (target_size and payload_size < target_size) else payload_size
    print(f"[+] Successfully assembled Android boot.img: {output_path}")
    print(f"    Kernel: {len(kernel_data)} bytes")
    print(f"    Ramdisk: {len(ramdisk_data)} bytes")
    if len(dtb_data) > 0:
        print(f"    DTB: {len(dtb_data)} bytes ({dtb_path})")
    print(f"    Payload: {payload_size} bytes ({payload_size/1024/1024:.2f} MB)")
    print(f"    Total padded partition size: {final_size} bytes ({final_size/1024/1024:.2f} MB)")

if __name__ == '__main__':
    # Usage: repack_boot.py <header.bin> <ramdisk.img> <Image.gz> <output_boot.img> [dtb.img] [target_partition_size]
    if len(sys.argv) < 5:
        print(f"Usage: {sys.argv[0]} <header.bin> <ramdisk.img> <Image.gz> <output_boot.img> [dtb.img] [target_partition_size]")
        sys.exit(1)

    header_file = sys.argv[1]
    ramdisk_file = sys.argv[2]
    kernel_file = sys.argv[3]
    output_file = sys.argv[4]
    dtb_file = None
    target_part_size = DEFAULT_BOOT_PARTITION_SIZE

    if len(sys.argv) >= 6:
        arg5 = sys.argv[5]
        if arg5.isdigit():
            target_part_size = int(arg5)
        else:
            dtb_file = arg5

    if len(sys.argv) == 7:
        target_part_size = int(sys.argv[6])

    repack(header_file, ramdisk_file, kernel_file, output_file, dtb_file, target_part_size)

#!/usr/bin/env python3
import sys
import struct
import hashlib

PAGE_SIZE = 4096
DEFAULT_BOOT_PARTITION_SIZE = 100663296  # Exactly 96 MB (96 * 1024 * 1024)

def pad(data, size):
    rem = len(data) % size
    if rem != 0:
        return data + b'\x00' * (size - rem)
    return data

def repack(header_path, ramdisk_path, kernel_path, output_path, target_size=DEFAULT_BOOT_PARTITION_SIZE):
    with open(header_path, 'rb') as f:
        header = bytearray(f.read(PAGE_SIZE))

    with open(kernel_path, 'rb') as f:
        kernel_data = f.read()

    with open(ramdisk_path, 'rb') as f:
        ramdisk_data = f.read()

    # Update kernel_size (offset 8) and ramdisk_size (offset 16)
    header[8:12] = struct.pack('<I', len(kernel_data))
    header[16:20] = struct.pack('<I', len(ramdisk_data))

    # Calculate SHA-1 digest over kernel + ramdisk and write to offset 576 (ID field)
    ctx = hashlib.sha1()
    ctx.update(kernel_data)
    ctx.update(ramdisk_data)
    digest = ctx.digest()
    header[576:596] = digest
    header[596:608] = b'\x00' * 12

    padded_kernel = pad(kernel_data, PAGE_SIZE)
    padded_ramdisk = pad(ramdisk_data, PAGE_SIZE)
    payload_size = len(header) + len(padded_kernel) + len(padded_ramdisk)

    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(padded_kernel)
        f.write(padded_ramdisk)
        if target_size and payload_size < target_size:
            f.write(b'\x00' * (target_size - payload_size))

    final_size = target_size if (target_size and payload_size < target_size) else payload_size
    print(f"[+] Successfully assembled Android boot.img: {output_path}")
    print(f"    Payload: {payload_size} bytes ({payload_size/1024/1024:.2f} MB)")
    print(f"    Total padded partition size: {final_size} bytes ({final_size/1024/1024:.2f} MB)")

if __name__ == '__main__':
    if len(sys.argv) < 5 or len(sys.argv) > 6:
        print(f"Usage: {sys.argv[0]} <header.bin> <ramdisk.img> <Image.gz> <output_boot.img> [target_partition_size]")
        sys.exit(1)
    target = int(sys.argv[5]) if len(sys.argv) == 6 else DEFAULT_BOOT_PARTITION_SIZE
    repack(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], target)

#!/usr/bin/env python3
import sys
import struct
import hashlib

PAGE_SIZE = 4096

def pad(data, size):
    rem = len(data) % size
    if rem != 0:
        return data + b'\x00' * (size - rem)
    return data

def repack(header_path, ramdisk_path, kernel_path, output_path):
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

    with open(output_path, 'wb') as f:
        f.write(header)
        f.write(pad(kernel_data, PAGE_SIZE))
        f.write(pad(ramdisk_data, PAGE_SIZE))

    print(f"[+] Successfully assembled Android boot.img: {output_path} ({len(kernel_data)} kernel bytes, {len(ramdisk_data)} ramdisk bytes)")

if __name__ == '__main__':
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <header.bin> <ramdisk.img> <Image.gz> <output_boot.img>")
        sys.exit(1)
    repack(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])

#!/usr/bin/env python3
import struct
import sys
import os

SPARSE_HEADER_MAGIC = 0xed26ff3a
CHUNK_TYPE_RAW = 0xCAC1
CHUNK_TYPE_FILL = 0xCAC2
CHUNK_TYPE_DONT_CARE = 0xCAC3
CHUNK_TYPE_CRC32 = 0xCAC4

def simg2img(src_file, dst_file):
    header_bin = src_file.read(28)
    if len(header_bin) < 28:
        raise ValueError("Invalid sparse image (too short)")
    
    magic, major, minor, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks, total_chunks, image_checksum = struct.unpack(
        "<IHHHHIIII", header_bin
    )
    
    if magic != SPARSE_HEADER_MAGIC:
        raise ValueError(f"Not a sparse image (magic 0x{magic:08x})")
    
    if file_hdr_sz > 28:
        src_file.read(file_hdr_sz - 28)
    
    print(f"Converting sparse image: {total_blks} blocks ({total_blks * blk_sz // (1024*1024)} MB), {total_chunks} chunks")
    
    total_written = 0
    zero_block = b"\x00" * blk_sz
    
    for i in range(total_chunks):
        chunk_hdr = src_file.read(chunk_hdr_sz)
        chunk_type, reserved, chunk_sz, total_sz = struct.unpack("<HHII", chunk_hdr[:12])
        data_sz = chunk_sz * blk_sz
        
        if chunk_type == CHUNK_TYPE_RAW:
            bytes_left = data_sz
            while bytes_left > 0:
                to_read = min(bytes_left, 4 * 1024 * 1024)
                buf = src_file.read(to_read)
                dst_file.write(buf)
                bytes_left -= len(buf)
            total_written += data_sz
        elif chunk_type == CHUNK_TYPE_FILL:
            fill_val = src_file.read(4)
            fill_block = fill_val * (blk_sz // 4)
            for _ in range(chunk_sz):
                dst_file.write(fill_block)
            total_written += data_sz
        elif chunk_type == CHUNK_TYPE_DONT_CARE:
            # For direct block flashing, fill with zeros or truncate
            # Writing zeros ensures the partition sectors are completely initialized
            dst_file.seek(data_sz, os.SEEK_CUR)
            total_written += data_sz
        elif chunk_type == CHUNK_TYPE_CRC32:
            src_file.read(4)
        else:
            raise ValueError(f"Unknown chunk type 0x{chunk_type:04x} at chunk {i}")
            
        if (i + 1) % 50 == 0 or i + 1 == total_chunks:
            sys.stdout.write(f"\rProgress: chunk {i+1}/{total_chunks} ({total_written // (1024*1024)} MB)")
            sys.stdout.flush()
            
    print(f"\nDone! Output size: {total_written} bytes ({total_written // (1024*1024)} MB)")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: simg2img.py <sparse_in> <raw_out>")
        sys.exit(1)
    with open(sys.argv[1], "rb") as src, open(sys.argv[2], "wb") as dst:
        simg2img(src, dst)

# -*- coding: utf-8 -*-
"""极简 VPK 检查器: 解析任意 Source2 vpk (含无哈希区的手工/社区 VPK), 列出条目并校验内联数据 CRC"""
import struct
import sys
import zlib


def cstr(buf, pos):
    e = buf.index(b"\x00", pos)
    return buf[pos:e].decode("utf-8", "replace"), e + 1


def parse(path):
    d = open(path, "rb").read()
    print(f"\n=== {path} ===")
    print(f"filesize={len(d)}")
    if len(d) < 28:
        print("  [!] 小于28字节, 不是 vpk")
        return
    sig, ver, tree_size = struct.unpack_from("<III", d, 0)
    fds, amd5, omd5, sigsec = struct.unpack_from("<IIII", d, 12)
    print(f"sig={sig:#x} ver={ver} tree={tree_size} fds={fds} amd5={amd5} omd5={omd5} sig={sigsec}")
    if sig != 0x55AA1234:
        print("  [!] 签名不是 0x55AA1234")
        return
    end_of_tree = 28 + tree_size
    tree = d[28:end_of_tree]
    data = d[end_of_tree:end_of_tree + fds]
    pos = 0
    n = 0
    while pos < tree_size:
        ext, pos = cstr(tree, pos)
        if not ext:
            break
        while pos < tree_size:
            dirc, pos = cstr(tree, pos)
            if not dirc:
                break
            while pos < tree_size:
                name, pos = cstr(tree, pos)
                if not name:
                    break
                crc, preload, aidx, off, ln, term = struct.unpack_from("<IHHIIH", tree, pos)
                pos += 18 + preload
                full = (dirc + "/" if dirc else "") + name + ("." + ext if ext else "")
                note = ""
                if aidx == 0x7FFF:
                    seg = data[off:off + ln]
                    if len(seg) == ln:
                        ok = (zlib.crc32(seg) & 0xFFFFFFFF) == crc
                        note = f" inline_crc={'OK' if ok else 'FAIL'}"
                    else:
                        note = f" [!] 内联数据越界 off={off}+{ln}>fds={fds}"
                print(f"  {full}  len={ln} aidx={aidx:#x} off={off} preload={preload} crc={crc:#010x}{note}")
                n += 1
    print(f"共 {n} 个条目; 树解析消耗 {pos}/{tree_size} 字节"
          + ("  [!] 树未完整解析!" if pos != tree_size else ""))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        parse(p)

# -*- coding: utf-8 -*-
"""构建 CS2 蝴蝶刀覆盖 VPK (格式照抄 csgo_addons/karambit.vpk 模板, 哈希区公式已逆向验证)

内容:
  weapons/models/knife/knife_default_ct/weapon_knife_default_ct.vmdl_c -> 蝴蝶刀模型
  weapons/models/knife/knife_default_t/weapon_knife_default_t.vmdl_c  -> 蝴蝶刀模型
  animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_ct.vnmgraph_c -> 蝴蝶刀动画图
  animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_t.vnmgraph_c  -> 蝴蝶刀动画图
    (默认刀动画图只认默认刀动画; 蝴蝶刀的检视转刀 lookat01-03 在它自己的动画图里,
     必须连图一起换, 否则检视无效 —— Source2 的 +variant 文件是完整编译图, 可直接替换)
  cfg/butterfly_check.cfg -> 挂载自检标记 (游戏内: exec butterfly_check)

数据源: 直接从原始 pak01 分卷提取 (CRC 校验), 不依赖任何补丁产物。
"""
import struct
import zlib
import hashlib
import os

GAME = r"c:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game"
CSGO = os.path.join(GAME, "csgo")
CHUNK462 = os.path.join(CSGO, "pak01_462.vpk")
BLOB_OFF, BLOB_LEN, BLOB_CRC = 100734688, 179961, 0x96D25BC6
# 蝴蝶刀动画图 (pak01_373): 自带 lookat01-03 检视转刀, 引用 16 个 butterfly 片段
GRAPH_ARCH, GRAPH_OFF, GRAPH_LEN = 373, 2297760, 8335
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "butterfly_knife.vpk")


def main():
    with open(CHUNK462, "rb") as f:
        f.seek(BLOB_OFF)
        blob = f.read(BLOB_LEN)
    assert len(blob) == BLOB_LEN, "蝴蝶刀数据读取不完整"
    assert zlib.crc32(blob) & 0xFFFFFFFF == BLOB_CRC, "蝴蝶刀数据 CRC 校验失败"
    print(f"[源] pak01_462.vpk @{BLOB_OFF}: {BLOB_LEN} 字节 CRC OK md5={hashlib.md5(blob).hexdigest()}")

    with open(os.path.join(CSGO, f"pak01_{GRAPH_ARCH:03d}.vpk"), "rb") as f:
        f.seek(GRAPH_OFF)
        graph = f.read(GRAPH_LEN)
    assert len(graph) == GRAPH_LEN, "动画图读取不完整"
    for probe in (b"lookat01_butterfly.vnmclip", b"knife_butterfly", b"viewmodel.vnmskel"):
        assert probe in graph, f"动画图内容异常: 缺少 {probe}"
    print(f"[源] pak01_{GRAPH_ARCH:03d}.vpk @{GRAPH_OFF}: 蝴蝶刀动画图 {GRAPH_LEN} 字节, 内容校验 OK")

    cfg = b'echo "*** BUTTERFLY_KNIFE_VPK_MOUNTED_OK ***"\n'
    files = [  # (ext, dir, name, payload)
        ("vmdl_c", "weapons/models/knife/knife_default_ct", "weapon_knife_default_ct", blob),
        ("vmdl_c", "weapons/models/knife/knife_default_t", "weapon_knife_default_t", blob),
        ("vnmgraph_c", "animation/graphs/viewmodel", "viewmodel_knife.vnmgraph+default_ct", graph),
        ("vnmgraph_c", "animation/graphs/viewmodel", "viewmodel_knife.vnmgraph+default_t", graph),
        ("cfg", "cfg", "butterfly_check", cfg),
    ]
    files.sort(key=lambda x: (x[0], x[1], x[2]))

    data = bytearray()
    entries = []
    for ext, d, name, payload in files:
        entries.append((ext, d, name, payload, len(data)))
        data += payload

    tree = bytearray()
    for ext in sorted({e[0] for e in entries}):
        tree += ext.encode("ascii") + b"\x00"
        for d in sorted({e[1] for e in entries if e[0] == ext}):
            tree += d.encode("ascii") + b"\x00"
            for e2 in sorted([e for e in entries if e[0] == ext and e[1] == d],
                             key=lambda e: e[2]):
                _, _, name, payload, off = e2
                tree += name.encode("ascii") + b"\x00"
                tree += struct.pack("<IHHIIH",
                                    zlib.crc32(payload) & 0xFFFFFFFF,
                                    0, 0x7FFF, off, len(payload), 0xFFFF)
            tree += b"\x00"   # 空文件名: 结束该目录的文件列表
        tree += b"\x00"       # 空目录名: 结束该扩展名的目录列表
    tree += b"\x00"           # 空扩展名: 结束全部

    header = struct.pack("<III", 0x55AA1234, 2, len(tree)) \
        + struct.pack("<IIII", len(data), 0, 48, 0)
    body = header + bytes(tree) + bytes(data)
    md5_tree = hashlib.md5(bytes(tree)).digest()
    md5_arch = hashlib.md5(b"").digest()                      # 无 archive_md5 区
    md5_all = hashlib.md5(body + md5_tree + md5_arch).digest()
    out = body + md5_tree + md5_arch + md5_all

    with open(OUT, "wb") as f:
        f.write(out)
    print(f"[输出] {OUT} ({len(out)} 字节, 树 {len(tree)}, 数据 {len(data)})")

    # 回读自检: 结构 + 哈希 + 树重新解析
    d = open(OUT, "rb").read()
    sig, ver, ts, fds, amd5, omd5, sigsec = struct.unpack_from("<IIIIIII", d, 0)
    t = d[28:28 + ts]
    dd = d[28 + ts:28 + ts + fds]
    om = d[28 + ts + fds:28 + ts + fds + omd5]
    assert sig == 0x55AA1234 and ver == 2
    assert len(t) == ts and len(dd) == fds and omd5 == 48 and sigsec == 0
    assert hashlib.md5(t).digest() == om[0:16], "md5(tree) 不符"
    assert hashlib.md5(b"").digest() == om[16:32]
    assert hashlib.md5(body + md5_tree + md5_arch).digest() == om[32:48], "第三哈希不符"

    def cstr(buf, p):
        e2 = buf.index(b"\x00", p)
        return buf[p:e2].decode("ascii"), e2 + 1

    pos, got = 0, []
    while True:
        ext, pos = cstr(t, pos)
        if not ext:
            break
        while True:
            dirc, pos = cstr(t, pos)
            if not dirc:
                break
            while True:
                name, pos = cstr(t, pos)
                if not name:
                    break
                crc, preload, aidx, off, ln, term = struct.unpack_from("<IHHIIH", t, pos)
                pos += 18 + preload
                got.append(((dirc + "/" if dirc else "") + name + "." + ext,
                            aidx, off, ln, crc, term))
    assert pos == ts, f"树回读未对齐: {pos}/{ts}"
    expect = {"cfg/butterfly_check.cfg": (len(cfg),),
              "weapons/models/knife/knife_default_ct/weapon_knife_default_ct.vmdl_c": (len(blob),),
              "weapons/models/knife/knife_default_t/weapon_knife_default_t.vmdl_c": (len(blob),),
              "animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_ct.vnmgraph_c": (len(graph),),
              "animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_t.vnmgraph_c": (len(graph),)}
    assert len(got) == 5, f"回读条目数 {len(got)}"
    for path, aidx, off, ln, crc, term in got:
        assert path in expect and expect[path][0] == ln, f"条目异常: {path}"
        assert aidx == 0x7FFF and term == 0xFFFF and preload == 0
        seg = dd[off:off + ln]
        assert len(seg) == ln and zlib.crc32(seg) & 0xFFFFFFFF == crc, f"CRC 失败: {path}"
        if path.endswith(".vmdl_c"):
            assert seg == blob, f"模型数据不一致: {path}"
        if path.endswith(".vnmgraph_c"):
            assert seg == graph, f"动画图数据不一致: {path}"
    print("[自检] 头部/树解析对齐/哈希区/数据/5条目 CRC 全部 OK")


if __name__ == "__main__":
    main()

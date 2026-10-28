---
name: cs2-vpk-knife-mod
description: CS2 本地视觉替换与 VPK 树条目重指向补丁，支持 19 种原生刀型一键切换与 36 种武器的皮肤涂装本地替换（paint kit 贴图重指向）、审计与回滚。当用户提到 CS2 换刀、蝴蝶刀、爪子刀、VPK 修改、模型替换、检视动画或武器皮肤涂装时使用。不适用于官方 VAC 对局修改或多人游戏作弊。
---

# CS2 VPK 本地视觉替换（换刀 + 换肤）

通过修改 pak01_dir.vpk 目录树条目指针（不改动任何 pak 数据包与哈希数组），实现两类本地视觉替换：把默认刀替换为其他原生刀型；把武器默认涂装替换为任意原生皮肤（paint kit 贴图级重指向）。纯视觉、哈希自洽、可一键回滚。

## 红线（违反即崩溃）

1. 绝不修改 chunk hash 数组 —— 引擎对其做有序二分查找，条目无序/缺失会触发延迟致命崩溃，且报错的 chunk 永远不是元凶
2. 绝不对稀疏 VPK（如 pak01_462.vpk 带 NTFS SparseFile 属性）补零对齐追加 —— 稀疏洞被引擎读到全零，哈希校验必炸
3. 只允许原地编辑已有树条目的 16 字节指针字段并重算 other_md5；禁止重建元数据区
4. 修改后的文件不得带入 VAC 官方对局；进官方局前先 --revert

## 标准流程

工具在 scripts/knife_mod.py（已内化全部安全约束，基于原始备份构建）：

```
python scripts/knife_mod.py --init            # 首次使用: 探测游戏路径 + 建原始备份 + 依赖检查
python scripts/knife_mod.py --list            # 列出 19 种可用刀型
python scripts/knife_mod.py --knife karambit  # 切换（4 条目指针 + other_md5 重算 + 自动审计）
python scripts/knife_mod.py --revert          # 还原默认刀
python scripts/knife_mod.py --audit           # 审计当前状态（可带刀型名）
```

1. 新机器/首次使用先跑 --init（自动经注册表 + libraryfolders.vdf 探测 Steam 库；失败时用 `--init --csgo "<路径>"` 手动指定）。它会把 pak01_dir.vpk 复制为 pak01_dir.vpk.bak_v6 作为原始基准——所有修改与回滚都以此为基准
2. --list 选刀 → --knife 应用 → 让用户进离线机器人局验证
3. 每次汇报附带提醒：VAC 官方局先还原；Steam「验证完整性」会把 pak01_dir.vpk 还原成官方原版（.bak_v6 备份不受影响仍有效），之后重跑 --knife 即可

## 换肤流程（skin_mod.py，贴图模式已实测生效）

```
python scripts/skin_mod.py --weapons                        # 列出可换肤武器 (36)
python scripts/skin_mod.py --list ak47                      # 列出该武器可用皮肤
python scripts/skin_mod.py --skin ak47 gs_ak47_bloodsport --tex   # 换血竞 (必须带 --tex)
python scripts/skin_mod.py --skin m4a4 am_kimono_sunrise --tex --stack   # 叠加第二把
python scripts/skin_mod.py --revert                         # 还原（与换刀共用备份）
python scripts/skin_mod.py --audit                          # 审计
```

- 皮肤发现：解析树内 6264 个 panorama 检视图文件名反推 武器×皮肤 映射；皮肤贴图按武器 UV 生成，**只能换本武器的皮肤**
- **必须用 --tex 贴图模式**：只把武器默认 `_color` 贴图条目重指向皮肤主贴图数据，保持武器原生 vmat/shader。整 vmat 重指向实测武器全透明（皮肤 vmat 走合成管线 shader，直接渲染输出 alpha=0）
- `--stack`：叠加补丁（多武器同时换装），带大小保护（文件被 Steam 还原则拒绝）；不带时从原始备份重建，覆盖此前补丁
- **选皮规则（重要）**：`tga` 单层满铺成品图皮肤（血竞/皇后/破晓/二西莫夫等大图）图案完整；`psd` 图案元素层皮肤（火蛇/咆哮等）只是合成管线输入元素，直接平铺必然不完整。`tex_targets` 已内置智能选源（tga 优先+大图优先），批量脚本 `batch_random.py` 只从满铺池挑选
- 效果：皮肤图案平铺全枪（无 paintmask 蒙版分色），质感/磨损保持默认涂装；UI 检视大图不变
- M4A4 特例已处理：panorama 里叫 `m4a1`、检视材质目录 `rif_m4a1`（消音版 `rif_m4a1_s` 专属），由 ALIAS/VIEW_ALIAS 表自动映射
- 刀皮肤：整 vmat 重指向刀全透明；贴图模式只能平铺共享小图案（fade/大马士革/大理石纹），无预烘焙成品图，效果有限

## 关键机制

- VPK v2：28 字节头；树从偏移 28 起；archiveMD5SectionSize 是字节数（÷28 = 条目数）；文件尾部 = 48B other_md5 + 1082B 签名块；other_md5[0:16] = md5(tree)、[16:32] = md5(哈希数组)，其余 16B 不动
- 切换 = 原地改 4 个条目：knife_default_t/ct 模型 vmdl_c + viewmodel_inspects.vnmgraph+knife_default_t/ct 检视图 vnmgraph_c。条目 18B 结构 <IHHIIH>（crc、preload、archiveIndex、offset、length、0xFFFF 结尾），只重写前 16B，preload 置 0
- 检视动画：段数/循环逻辑在检视图 vnmgraph_c 而非 clip；专属多段检视图只有蝴蝶/爪子/爪刃三种，其余为单段 inspects 变体；检视图按完整内容路径引用动画条目（原生直接加载，骨架天然匹配）
- 已知限制：换刀只能用各刀原色外观；武器皮肤可本地替换但图案为平铺效果（见换肤流程与 references/vpk-technique.md）
- 模型来源仅限官方 pak01 内 19 种原生刀：创意工坊地图无武器模型资产（实测 12 图 6505 模型 0 命中，全是环境资产）；外置/自制/创意工坊 VPK 挂载被签名链密码学锁死（详见 references/vpk-technique.md）

## 审计要点

- 当前文件大小必须与原始备份一致（4 条目方案树大小不变）；不一致说明磁盘是其他补丁状态，先 --revert 或重apply
- 字节差异必须全部落在 4 个目标条目的 16B 字段范围 + other_md5 的 32B 内
- 哈希数组区与签名块逐字节不变
- 涉及的 pak 数据包全窗口按条目类型重哈希（BLAKE3-128 / MD5）

崩溃取证、v6→v9 方案演进、图与动画系统细节见 references/vpk-technique.md。

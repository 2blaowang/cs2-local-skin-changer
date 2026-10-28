---
name: cs2-vpk-knife-mod
description: CS2 本地视觉替换与 VPK 树条目重指向补丁，支持 19 种原生刀型一键切换、36 种武器的皮肤整材质换肤（拥有皮肤时引擎跑完整合成管线，官方级效果）、72 个手套皮肤同家族互换、审计与回滚。当用户提到 CS2 换刀、蝴蝶刀、爪子刀、VPK 修改、模型替换、皮肤替换、手套替换、检视动画时使用。不适用于官方 VAC 对局修改或多人游戏作弊。
---

# CS2 VPK 本地视觉替换（换刀 + 换肤 + 换手套）

通过修改 pak01_dir.vpk 目录树条目指针（不改动任何 pak 数据包与哈希数组），实现三类本地视觉替换：把默认刀替换为其他原生刀型；把**已拥有的皮肤**整份换成另一款同武器皮肤（官方级效果）；把手套换成同家族另一款。纯视觉、哈希自洽、可一键回滚。

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

## 换肤流程 A：整材质换肤（`--swap`，拥有皮肤时首选）

前提：你**真拥有**该武器上的任意一款皮肤（服务端下发 paintindex）。此时引擎本来就会跑完整合成管线（蒙版/磨损/污渍/paintseed），我们只把"已拥有皮肤"的材质条目重指向"想显示皮肤"的——**1~2 个条目，官方级效果**。

```
python scripts/skin_mod.py --weapons                                     # 列出可换肤武器 (36)
python scripts/skin_mod.py --list ak47                                   # 列出皮肤，带 [legacy]/[composite] 标记
python scripts/skin_mod.py --swap ak47 cu_ak47_mastery cu_ak_island_floral          # 精英之作 → 野荷
python scripts/skin_mod.py --swap awp awp_tempered awp_queens_gambit --stack        # 叠加（保留已有补丁）
python scripts/skin_mod.py --revert                                      # 还原（与换刀共用备份）
python scripts/skin_mod.py --audit                                       # 审计
```

- **唯一的硬约束是"资源形态"必须相同**（`form_of()` 已硬拦）：
  - `legacy` = 有独立 `vmats/<kit>.vmat`，vcompmat 只是转交声明（约 4.2KB + 1.5KB 两条）
  - `composite` = 只有 vcompmat 完整节点图，无 vmat（约 5.8KB 一条，2023 年后新版工作室皮肤）
  - 跨形态互换必然图案错乱。**style 不是分界线**（style 7 里也有 45 个 composite），形态才是
  - 判形态只看有没有 `vmats/<kit>.vmat`，不看名字也不看 style：`cu_glitter_deagle` 星尘拱廊名字带 `cu_`、style 7，但无 vmat，是 composite
- 一条入口皮肤 = 一个可显示槽位。想同时看多个皮肤，需拥有多个入口（各自打补丁，`--stack` 叠加）
- 实测成功：legacy→legacy（AK 火蛇/野荷、AWP 巨龙传说、沙鹰 沙漠之狐、M4A4 咆哮）、composite→composite（镀铬大炮→后翼弃兵、战鹰→吞天巨蛇、书法涂鸦→星尘拱廊）
- **style 已正交验证为无关变量**：变频器(2)→咆哮(7)、青铜装饰(5)→沙漠之狐(9)、书法涂鸦(9)→星尘拱廊(7) 全部成功，唯一失败样本是跨形态。无需收紧成"形态+style 双匹配"
- 图标不变：背包/检视 UI 是预烘焙 panorama png

## 换肤流程 B：手套（`--glove`）

```
python scripts/skin_mod.py --gloves                                      # 72 个手套皮肤按 7 家族分组
python scripts/skin_mod.py --glove sporty_hunter sporty_purple --stack   # 大型猎物 → 潘多拉之盒
```

- 手套 72 个 kit **全部 legacy 形态**，没有 composite 变体，比武器更规整
- **只能同家族换**：kit 自带 mask/normal 按该家族手部 UV 绘制，跨家族会花纹错位（需连模型一起换，本工具不做，已硬拦）
- 同家族 UV 同源：实测大型猎物与潘多拉之盒的 AO/法线指向同一张贴图，只有 mask 不同
- **命名陷阱**：潘多拉之盒 = `sporty_purple`（不是 `sporty_pandoras_box`）、树篱迷宫 = `sporty_green`、双栖 = `sporty_poison_frog_blue_white`。中文名一律用 `cn_names()` 查 `PaintKit_<kit>_tag`，不要按字面猜

## 换肤流程 C：贴图模式（`--skin --tex`，没有皮肤时的降级方案）

```
python scripts/skin_mod.py --skin ak47 gs_ak47_bloodsport --tex   # 换血竞 (必须带 --tex)
python scripts/skin_mod.py --skin m4a4 am_kimono_sunrise --tex --stack   # 叠加第二把
```

- 只把武器默认 `_color` 贴图条目重指向皮肤主贴图数据，保持武器原生 vmat/shader。整 vmat 重指向实测武器全透明（皮肤 vmat 走合成管线 shader，直接渲染输出 alpha=0）
- **效果上限是"图案平铺全枪"**：无 paintmask 蒙版分色、无磨损合成，质感仍是默认涂装
- **选皮规则**：`tga` 单层满铺成品图（血竞/皇后/破晓等大图）图案完整；`psd` 图案元素层（火蛇/咆哮等）只是合成管线输入，直接平铺必然残缺。`tex_targets` 已内置 tga 优先+大图优先，`batch_random.py` 只从满铺池挑选
- 诊断工具：`python scripts/diagnose_skin.py --weapons` 列出每个皮肤的完整度评级（FULL/BROKEN）
- `--stack`：叠加补丁（多武器同时换装），带大小保护（文件被 Steam 还原则拒绝）；不带时从原始备份重建，覆盖此前补丁
- M4A4 特例已处理：panorama 里叫 `m4a1`、检视材质目录 `rif_m4a1`（消音版 `rif_m4a1_s` 专属），由 ALIAS/VIEW_ALIAS 表自动映射
- 刀皮肤：整 vmat 重指向刀全透明；贴图模式只能平铺共享小图案（fade/大马士革/大理石纹），无预烘焙成品图，效果有限

## 关键机制

- VPK v2：28 字节头；树从偏移 28 起；archiveMD5SectionSize 是字节数（÷28 = 条目数）；文件尾部 = 48B other_md5 + 1082B 签名块；other_md5[0:16] = md5(tree)、[16:32] = md5(哈希数组)，其余 16B 不动
- 切换 = 原地改 4 个条目：knife_default_t/ct 模型 vmdl_c + viewmodel_inspects.vnmgraph+knife_default_t/ct 检视图 vnmgraph_c。条目 18B 结构 <IHHIIH>（crc、preload、archiveIndex、offset、length、0xFFFF 结尾），只重写前 16B，preload 置 0
- 检视动画：段数/循环逻辑在检视图 vnmgraph_c 而非 clip；专属多段检视图只有蝴蝶/爪子/爪刃三种，其余为单段 inspects 变体；检视图按完整内容路径引用动画条目（原生直接加载，骨架天然匹配）
- 已知限制：换刀只能用各刀原色外观；换肤效果取决于走哪条流程——`--swap`（拥有皮肤）是官方级，`--skin --tex`（无皮肤）只能是图案平铺（见 references/vpk-technique.md）
- 模型来源仅限官方 pak01 内 19 种原生刀：创意工坊地图无武器模型资产（实测 12 图 6505 模型 0 命中，全是环境资产）；外置/自制/创意工坊 VPK 挂载被签名链密码学锁死（详见 references/vpk-technique.md）

## 审计要点

- 当前文件大小必须与原始备份一致（只改树条目指针，树大小不变）；不一致说明磁盘是其他补丁状态，先 --revert 或重 apply
- 字节差异必须全部落在被改条目的 16B 字段范围 + other_md5 的 32B 内（换刀 4 条、整材质换肤 1~2 条/入口，字节差异随改动条数线性变化）
- 哈希数组区与签名块逐字节不变
- 涉及的 pak 数据包全窗口按条目类型重哈希（BLAKE3-128 / MD5）

崩溃取证、v6→v9 方案演进、图与动画系统细节见 references/vpk-technique.md。

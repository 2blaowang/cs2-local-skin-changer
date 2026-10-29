---
name: cs2-local-skin-changer
description: CS2本地换肤器 —— CS2 本地视觉替换与 VPK 树条目重指向补丁，支持 19 种原生刀型一键切换（模型+主图+检视三层齐换）、34 种武器的皮肤整材质换肤（拥有皮肤时引擎跑完整合成管线，官方级效果）、72 个手套皮肤同家族互换、跨武器/跨形态试探（--force，如把刀的多普勒/宝石挂到枪上）、按名字查同族材质（--family）、审计与回滚，并附图形化控制台（Web/PySide6）可预览贴图。当用户提到 CS2 换刀、换肤、换手套、蝴蝶刀、爪子刀、拔刀动作不对、手模不对、检视动画异常、VPK 修改、模型替换、皮肤替换、多普勒/蓝宝石/黑珍珠、手套替换时使用。仅面向本机离线与社区服场景。
---

# CS2本地换肤器（换刀 + 换肤 + 换手套）

通过修改 pak01_dir.vpk 目录树条目指针（不改动任何 pak 数据包与哈希数组），实现三类本地视觉替换：把默认刀替换为其他原生刀型；把**已拥有的皮肤**整份换成另一款同武器皮肤（官方级效果）；把手套换成同家族另一款。纯视觉、哈希自洽、可一键回滚。

不想敲命令时用图形界面（`gui/`）：`python gui/serve.py` 开浏览器版（零依赖），`gui\run_gui.bat` 开桌面版。界面只是壳，所有写盘仍由本文件的脚本执行。

## 红线（违反即崩溃）

1. 绝不修改 chunk hash 数组 —— 引擎对其做有序二分查找，条目无序/缺失会触发延迟致命崩溃，且报错的 chunk 永远不是元凶
2. 绝不对稀疏 VPK（如 pak01_462.vpk 带 NTFS SparseFile 属性）补零对齐追加 —— 稀疏洞被引擎读到全零，哈希校验必炸
3. 只允许原地编辑已有树条目的 16 字节指针字段并重算 other_md5；禁止重建元数据区
4. 进官方对局前先 --revert 还原；单机、离线与社区服无此顾虑

## 标准流程

工具在 scripts/knife_mod.py（已内化全部安全约束，基于原始备份构建）：

```
python scripts/knife_mod.py --init            # 首次使用: 探测游戏路径 + 建原始备份 + 依赖检查
python scripts/knife_mod.py --list            # 列出 19 种可用刀型，标主图槽/检视槽类型
python scripts/knife_mod.py --knife bayonet   # 变体体系刀型: 模型 2 + 主图 2 + 检视 2 = 6 条
python scripts/knife_mod.py --knife karambit  # 独立完整图刀型: 模型 2 + 主图 2 = 4 条（检视槽自动留空）
python scripts/knife_mod.py --knife karambit --no-inspect      # 显式留空检视槽（完整图型已是默认，一般不用写）
python scripts/knife_mod.py --knife karambit --no-main         # 排查用: 主图槽不动
python scripts/knife_mod.py --knife karambit --force-inspect   # 强行让检视变体接管(完整图型会丢收尾动作)
python scripts/knife_mod.py --revert          # 还原默认刀
python scripts/knife_mod.py --audit           # 审计当前状态（可带刀型名）
```

1. 新机器/首次使用先跑 --init（自动经注册表 + libraryfolders.vdf 探测 Steam 库；失败时用 `--init --csgo "<路径>"` 手动指定）。它会把 pak01_dir.vpk 复制为 pak01_dir.vpk.bak_v6 作为原始基准——所有修改与回滚都以此为基准
2. --list 选刀 → `--rebuild <刀型>` 应用（同时重放换肤补丁）→ 让用户进离线机器人局验证。**只有第一次、还没配任何皮肤时才用 `--knife <刀型>`**；已有皮肤时一律走 `--rebuild`，否则皮肤补丁会被抹掉
3. 每次汇报附带提醒：官方局先还原；Steam「验证完整性」会把 pak01_dir.vpk 还原成官方原版（.bak_v6 备份不受影响仍有效），之后重跑 --knife 即可

## 换肤流程 A：整材质换肤（`--swap`，拥有皮肤时首选）

前提：你**真拥有**该武器上的任意一款皮肤（服务端下发 paintindex）。此时引擎本来就会跑完整合成管线（蒙版/磨损/污渍/paintseed），我们只把"已拥有皮肤"的材质条目重指向"想显示皮肤"的——**1~2 个条目，官方级效果**。

```
python scripts/skin_mod.py --weapons                                     # 列出可换肤武器 (34, 含电击枪)
python scripts/skin_mod.py --list ak47                                   # 列出皮肤，带 [legacy]/[composite] 标记
python scripts/skin_mod.py --family doppler                              # 按名字查同族皮肤及其形态（多普勒/宝石/渐变/手套）
python scripts/skin_mod.py --swap ak47 cu_ak47_mastery cu_ak_island_floral          # 精英之作 → 野荷
python scripts/skin_mod.py --swap awp awp_tempered awp_queens_gambit --stack        # 叠加（保留已有补丁）
python scripts/skin_mod.py --patches                                     # 查看补丁清单
python scripts/skin_mod.py --rebuild karambit                            # 换刀 + 按清单重放全部补丁（一条命令）
python scripts/skin_mod.py --rebuild butterfly --no-main                 # 同上，主图槽不动
python scripts/skin_mod.py --rebuild karambit --force-inspect            # 检视变体强行接管（非默认，会丢收尾）
python scripts/skin_mod.py --swap mp9 mp9_nexus am_sapphire_marbleized --force --stack  # 跨武器+跨形态（只有入口 vcompmat 一条）
python scripts/skin_mod.py --revert                                      # 还原（与换刀共用备份）
python scripts/skin_mod.py --audit                                       # 审计
```

- **配对分三档，越往下越不保证效果**：
  1. **同武器 + 同形态** —— 官方级效果，1~2 条条目，无需额外参数
  2. **同武器 + 跨形态** —— 需 `--force`。结构上是合法的（legacy 的 vcompmat 就是 `CCompositeMaterialEditorDoc` 的单节点图，和 composite 图同一个文档类），但**结果不稳定**：战鹰→咆哮 ✗、中枢→多普勒 ✓，只能逐例试
  3. **跨武器** —— 需 `--force`。图案按**目标武器**的 UV 重新展开，刀→枪（MP9 中枢→多普勒/蓝宝石/黑珍珠）已验可出效果，但不保证是原皮肤的构图
- 两种形态：
  - `legacy` = 有独立 `vmats/<kit>.vmat`；vcompmat 是一个 `SPECIFIC_MATERIAL` 单节点图，把材质转交给该 vmat（约 4.2KB + 1.5KB 两条）
  - `composite` = 只有 vcompmat 完整节点图（albedo/ao/mask/normal/rough 全在图里），无 vmat（约 5.8KB 一条，2023 年后新版工作室皮肤）
  - 判形态只看有没有 `vmats/<kit>.vmat`，不看名字也不看 style：`cu_glitter_deagle` 星尘拱廊名字带 `cu_`、style 7，但无 vmat，是 composite
  - **style 是无关变量**（它只决定图案在 UV 上的铺法：hydrographic/阳极/喷绘/枪匠），别拿它当判据
- **入口永远是 vcompmat 那一条**（`items_game` 的 `composite_material_path` 指向它）。整换时两侧都有 vmat 才配对 vmat，只有一侧有就只动 vcompmat——目标文档内部用绝对路径引自己的 vmat/贴图，不需要代劳
- `--force` 越过"同武器 / 同形态"两道校验，`swap_targets()` 会把风险逐条打印出来
- 一条入口皮肤 = 一个可显示槽位。想同时看多个皮肤，需拥有多个入口（各自打补丁，`--stack` 叠加）；同一槽位换第二款是覆盖，不是并列
- 实测成功：legacy→legacy（AK 火蛇/野荷、AWP 巨龙传说、沙鹰 沙漠之狐、M4A4 咆哮、M4A1-S 夜无眠→冒险家乐园）、composite→composite（镀铬大炮→后翼弃兵、战鹰→吞天巨蛇、书法涂鸦→星尘拱廊）、手套（大型猎物→潘多拉之盒）
- **style 已正交验证为无关变量**：变频器(2)→咆哮(7)、青铜装饰(5)→沙漠之狐(9)、书法涂鸦(9)→星尘拱廊(7)、夜无眠(9)→冒险家乐园(7) 全部成功。无需收紧成"形态+style 双匹配"
- 图标不变：背包/检视 UI 是预烘焙 panorama png

### 多普勒 / 宝石系（最常用的跨武器试验场）

武器侧 26 个 kit，全部 legacy + style 5，只有一张 `anodized_multi` 程序化底图 + 一堆色相参数，不依赖 paintmask，所以最适合往别的枪上挂。

- **换阶段编号不会变色**：`am_doppler_phase1`~`4` 的 vmat 逐字节只差 355~411 字节（几乎全是材质名），刀上的"第几阶段"色相来自 paintseed 区间（服务端数据），本地拿不到
- **想要确定颜色只能走宝石系**：`am_sapphire_marbleized` 蓝、`am_ruby_marbleized` 红、`am_emerald_marbleized` 绿、`am_blackpearl_marbleized` 黑（底图换成 `smoke_psd`，纹路更细、最暗最亮彩）
- 伽玛多普勒（`am_gamma_doppler_phase1`~`4`）是绿系，和普通多普勒差 2808 字节；`_glock` / `_widow` 是按特定武器 UV 调过构图密度的变体，可以对比着试
- 查同族：`--family doppler`、`--family "sapphire|ruby|emerald|blackpearl"`

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
- **composite 皮肤走不了这条流程**（`--list` 里标 `(composite, 仅 --swap)` 的就是）：`--skin` 要求 kit 有 `vmats/<kit>.vmat` 这份**已烘焙的静态材质**，composite 只有 vcompmat 节点图。合成器只在"服务端下发了 paintindex 的物品槽位"上启动，默认涂装槽没有 paintindex，把节点图塞进去没人计算 → 拿不到画面。要用 composite 皮肤，必须有一个**已拥有的皮肤槽位**，走 `--swap` 把配方换过去
- **效果上限是"图案平铺全枪"**：无 paintmask 蒙版分色、无磨损合成，质感仍是默认涂装
- **选皮规则**：`tga` 单层满铺成品图（血竞/皇后/破晓等大图）图案完整；`psd` 图案元素层（火蛇/咆哮等）只是合成管线输入，直接平铺必然残缺。`tex_targets` 已内置 tga 优先+大图优先，`batch_random.py` 只从满铺池挑选
- 诊断工具：`python scripts/diagnose_skin.py --weapons` 列出每个皮肤的完整度评级（FULL/BROKEN）
- `--stack`：叠加补丁（多武器同时换装），带大小保护（文件被 Steam 还原则拒绝）；不带时从原始备份重建，覆盖此前补丁
- **补丁清单 `patches.json`**：每成功应用一条 `--swap`/`--glove` 就自动记一条（同 `类型+武器+owned` 覆盖，不会重复）。`--patches` 查看
- **`--rebuild <刀型>`**：换刀会从原始备份整体重建文件、抹掉全部换肤补丁，所以换刀后必须重放。这条命令把「换刀 + 按清单逐条 `--stack` 重放 + 审计」一次做完，是换刀的正确姿势（不要手动逐条补，容易漏）
  - 换刀前先进 `--rebuild`，避免忘了补肤；清单跨换刀、跨 `--revert` 都会保留（个人库存配置，已 gitignore）
- M4A4 特例已处理：panorama 里叫 `m4a1`、检视材质目录 `rif_m4a1`（消音版 `rif_m4a1_s` 专属），由 ALIAS/VIEW_ALIAS 表自动映射
- 刀皮肤：整 vmat 重指向刀全透明；贴图模式只能平铺共享小图案（fade/大马士革/大理石纹），无预烘焙成品图，效果有限

## 关键机制

- VPK v2：28 字节头；树从偏移 28 起；archiveMD5SectionSize 是字节数（÷28 = 条目数）；文件尾部 = 48B other_md5 + 1082B 签名块；other_md5[0:16] = md5(tree)、[16:32] = md5(哈希数组)，其余 16B 不动
- 切换 = 原地改 **三个槽位**（条目 18B 结构 `<IHHIIH>`：crc、preload、archiveIndex、offset、length、0xFFFF；只重写前 16B，preload 置 0）：
  | 槽位 | 条目 | 管什么 | 不换的症状 |
  |---|---|---|---|
  | 模型槽 | `vmdl_c:.../knife_default_t\|ct` | 外观几何 | 看不见目标刀 |
  | **主图槽** | `viewmodel_knife.vnmgraph+default_t\|ct` | **idle / 拔刀 / 攻击 / 手模姿势** | **拔刀和手臂还是匕首的** |
  | 检视槽 | `viewmodel_inspects.vnmgraph+knife_default_t\|ct` | 按 F 的检视玩法 | 播默认刀的检视 |
  变体体系刀型 6 条（模型 2 + 主图 2 + 检视 2）；独立完整图刀型 4 条（模型 2 + 主图 2，检视槽留空）
- **为什么主图槽必须直接改**：顶层 `vnmgraph_c:.../viewmodel`（20.8KB）是总调度表，用 `referencedGraphSlot` + `m_variationID` 选子图，而 variationID 来自物品数据——换指针改不了它，永远是 `+default_ct` 被选中。所以只能改这个槽位里的指针，指望"换模型自动带动作"是不成立的
- **主图槽填什么**：19 把刀里 16 把走"变体体系"，填同名变体 `viewmodel_knife.vnmgraph+<刀名>`；**只有 karambit / butterfly / talon 三把是独立完整图** `viewmodel_knife_<刀名>`（8.2~8.3KB），填完整图。`main_var_for()` 自动判定
- **检视槽填法分两类，取决于主图槽填的哪类图**（`build_targets()` 已自动判定）：
  - **变体体系（16 把）**：检视槽填同名**检视变体** `viewmodel_inspects.vnmgraph+knife_<刀名>`（约 4.9KB，与 default 变体 97.7% 同构）。不填就播匕首的检视
  - **独立完整图（karambit / butterfly / talon）**：检视槽**留空**。完整图自带整套检视状态机，自己接管检视
- **为什么完整图型要留空**：两份资源的检视流程不同——
  | | 完整图 `viewmodel_knife_<刀名>` | 检视变体 `+knife_<刀名>` |
  |---|---|---|
  | 状态 | `INSPECT_LOOP` + **`OUTRO`** + `USE_FIXUP_VERSION` | `INSPECT_USE_DRAW_VERSION` + `CANCEL` |
  | 流程 | 进检视 → 循环 → **收尾** → 回待机 | 播一次 → 直接取消 |
  让变体接管，就只剩"播一次"，**丢掉循环与 OUTRO 收尾**——爪子刀实测表现为"少一个检视动作"；留空交给完整图，流程完整（已实测确认）
- **绝不能把完整图塞进检视槽**：4.9KB 的槽装 8.3KB 状态机，进 `INSPECT_LOOP` 又收不到 `INSPECTCANCEL`，会播完不停、连续重复触发（`--force-inspect` 就是这个错误配置）
- 检视段数由资源决定，改不了：butterfly 3 段、css 7 段、talon/skeleton/stiletto/ursus 等 2 段、**karambit 只有 1 段 `lookat01_karambit`**（官方本就如此，不是改丢了）
- 检视动画：段数/循环逻辑在 vnmgraph_c 而非 clip；检视图按完整内容路径引用动画条目（原生直接加载，骨架天然匹配）
- 退避开关：`--no-inspect` 显式留空检视槽（完整图型已是默认）；`--no-main` 只换模型与检视（主图槽不动，用于排查完整图端口契约不兼容）；`--force-inspect` 让检视变体强行接管（完整图型会丢收尾）
- 已知限制：换刀只能用各刀原色外观；换肤效果取决于走哪条流程——`--swap`（拥有皮肤）是官方级，`--skin --tex`（无皮肤）只能是图案平铺（见 references/vpk-technique.md）
- 模型来源仅限官方 pak01 内 19 种原生刀：创意工坊地图无武器模型资产（实测 12 图 6505 模型 0 命中，全是环境资产）；外置/自制/创意工坊 VPK 挂载被签名链密码学锁死（详见 references/vpk-technique.md）

## 审计要点

- 当前文件大小必须与原始备份一致（只改树条目指针，树大小不变）；不一致说明磁盘是其他补丁状态，先 --revert 或重 apply
- 字节差异必须全部落在被改条目的 16B 字段范围 + other_md5 的 32B 内（换刀 4~6 条、整材质换肤 1~2 条/入口，字节差异随改动条数线性变化）
- 哈希数组区与签名块逐字节不变
- 涉及的 pak 数据包全窗口按条目类型重哈希（BLAKE3-128 / MD5）

崩溃取证、v6→v9 方案演进、图与动画系统细节见 references/vpk-technique.md。

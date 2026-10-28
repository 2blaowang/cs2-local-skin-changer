# CS2 VPK 替换技术深潜

本文沉淀本次刀模型替换全过程的技术结论，供调试与扩展（如替换其他资源类型）时参考。

## 引擎校验机制（崩溃取证结论）

- **VerifySingleChunk（窗口存在性检查）**：引擎对读取触及的每 1MB 窗口做二分查找，只验证条目"存在性"；未命中置 dirty 标志，在下一次读取时 fatal "corrupt (Chunk: pak01_XXX.vpk)"。**报错的 chunk 从来不是元凶**，定位时要看是哪个操作引入了缺失/乱序条目
- **窗口哈希校验**：ChunkHashFraction_t 第二个 u16 是 EHashType（0=MD5，1=BLAKE3，0x8000=目录特殊）。每次 chunk 读取后引擎（filesystem_stdio 内 FUN_18012be30）用条目类型算法重哈希**整个 1MB 窗口**并比对；签名 VPK 上不匹配 fatal "Content file %s is corrupt."（无 Chunk 后缀）
- **v2/v4 闪退根因**：转储中提取的引擎摘要 488de202f73bd976de4e7048f4e1f39a = 标准 blake3(1MB 全零 buffer)。旧补丁在稀疏的 pak01_462.vpk 上补零对齐追加，NTFS 把窗口 95 变成稀疏洞（逻辑全零）→ 引擎读到零 → 哈希不匹配。教训：**绝不对稀疏 VPK 补零/追加**；优先树条目重指向（不碰数据包）
- 若必须向编号 VPK 追加数据：对齐到 1MB 窗口边界、在哈希数组按序插入新条目（用正确类型的全窗口哈希）、header archiveMD5SectionSize += 28、重算 other_md5[0:32]；[32:48] 不动
- pak01_dir.vpk 尾部 = 48B other_md5 + 1082B 签名块（magic 55AA1234 + DER 证书）；头部 signatureSectionSize 字段（20）不可靠；引擎只检查签名**存在性**不验有效性
- "300 个过期哈希"是误诊：那些是 BLAKE3 类型条目，用 MD5 比对当然不一致，磁盘数据没问题
- Steam「验证完整性」会还原所有 VPK 补丁

## VPK v2 格式速查

- 头 28 字节 = 7 × u32：sig / ver / treeSize / fileDataSectionSize / archiveMD5SectionSize / otherMD5SectionSize / signatureSectionSize；树从偏移 28 开始
- archiveMD5SectionSize 是**字节数**（÷28 = 条目数，如 1428280B = 51010 条）
- 树条目 18B `<IHHIIH>`：crc(u32)、preload(u16)、archiveIndex(u16)、offset(u32)、length(u32)、terminator 0xFFFF；三层字典 ext → path → filename，字符串 \0 结尾
- 树终止符（自建树必读）：每个 path 块的名字列表末尾必须有**独立** \0，然后 \0 结束 path 列表，最后 \0 结束 ext 列表——漏掉任何一个，解析器就在字符串中间错位（表现为 "bad terminator 0x7561" 类错误，字符值是字符串内容切片）
- preload 字段 u16 上限 65535B——模型类资源无法内嵌树，preload 路线格式级判死
- other_md5 位于 filesize − 1082 − 48：[0:16] = md5(tree)，[16:32] = md5(hash array)，[32:48] 不动

## 方案演进史

| 版本 | 改动 | 结果 |
|---|---|---|
| v1-v4 | 补零追加 + 重建/插入哈希条目 | 稀疏洞 → 闪退 |
| v6 | 原地改 2 个模型条目指向 462 内蝴蝶数据 | 模型生效，无检视 |
| v7 | +13 个 vnmclip_c 指针换到蝴蝶 clip | 单段检视生效 |
| v8 | +插入 2 个新 clip 条目（lookat02/03） | 无变化（逻辑不在 clip） |
| v9 | +2 个检视图条目重指向蝴蝶专属图 | 三段检视生效（19 条目） |
| knife_mod | 最小 4 条目（模型 T/CT + 检视图 T/CT） | 最终方案，树大小不变 |

- v7 原因：检视动画从 default_t clip 集加载，默认 clip 骨架与蝴蝶不匹配；CT 刀没有自己的 viewmodel clips（与 T 共用一套）
- v8 教训：检视段数/循环逻辑在**检视图 vnmgraph_c** 里，不在 clip
- v9 机制：普通武器用 viewmodel_inspects.vnmgraph+武器名（~4.9KB 单段，被 15020B 基础图查找表引用）；蝴蝶有专属图 viewmodel_knife_butterfly（8335B）按**完整内容路径**引用全部 16 个蝴蝶 clip（含 LOOP/OUTRO 状态机）。图引用的原生条目直接加载，骨架天然匹配，所以 4 条目方案不需要换 clip
- 图的 m_variationID=knife_butterfly 未因武器名不匹配而被校验拦截（实测）

## 关键数据位置

游戏根：`c:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\`

- 蝴蝶模型 vmdl_c：462:100734688，179961B，crc 0x96d25bc6
- 蝴蝶 clips（pak01_473）：17821584（draw）~18052096（lookat03，48174B crc 0xD56FB694）
- 蝴蝶专属检视图：373:2297760，8335B
- 默认检视图：386:93050032（knife_default_t）、386:93045104（knife_default_ct）
- 默认刀原位置：T = 36:71214832（48588B）、CT = 315:98456176（100125B）
- 窗口审计基线：462 = 116 窗口、473 = 100 窗口、373 = 104 窗口（全部验证通过）

## 自定义 VPK 挂载实验（终审：密码学不可行）

三轮实验 + filesystem_stdio.dll 逆向，结论：**任何无 Valve 签名的 VPK 都无法在 CS2 加载**，与树格式正确与否无关。

| 轮次 | 做法 | 结果 | 根因 |
|---|---|---|---|
| mymod | 自建树条目指向 pak01 内蝴蝶刀数据偏移 | 静默无效 | 无签名块 → FUN_1801264c0 返回 0 → 静默丢弃 |
| pak99 | 标准 pak## 命名 + 整 1MB 数据包 | fatal "(pakxx=off)" | pak## 未注册守卫直接 fatal |
| zzmod | 改名绕守卫 + 完全合法的自建树 | 静默无效 | 签名链不过 → 静默丢弃 |

### 逆向细节（filesystem_stdio.dll）

- **pak## 守卫（FUN_180051d20）**：`pak+两位数字` 命名且未在注册表中的 VPK 直接 fatal；"(pakxx=off)" 是死字符串标签不是占位符。`game\bin\win64\vpk.signatures`（KeyValues 文本）里 `"pakxx" "off"` 开关可关闭该守卫，但只解除第一道门
- **签名链（FUN_1801264c0）**：所有树 ≥2 字节的 VPK 必须通过验证——① 内嵌公钥逐字节等于 Valve 钉扎公钥；② 钉扎签名字节 memcmp；③ RSA-SHA256 验证签名 payload（dir+0x3e8 处 16B = other_md5[32:48]）。任一失败**静默跳过**（不报错，VPK 不生效）。伪造需要 Valve 私钥，密码学不可满足
- **注册表 MD5 匹配**被同一条 RSA 链锁定，改注册表无效
- **唯一理论出路**：补丁 DLL 跳过 FUN_180129480（树空判定）/ FUN_1801264c0（签名验证）——修改引擎二进制 VAC 风险极高，否决

### 自建 VPK 格式要点（仅供研究；游戏不会加载）

- 编号数据包必须填充到整 1MB 倍数（所有窗口满尺寸），哈希条目 sz = 完整窗口大小；不满 1MB 启动即 "Failed to load file" fatal
- 无签名块时 header 7×u32 按实际 section 大小写，signatureSectionSize = 0
- 树终止符三层结构见上文格式速查
- 第一人称手臂/手套不走 pak 树条目加载（weapon_arms 无资源引用，经服务端库存/经济系统下发）——手套路线同样判死

### 创意工坊模型侦察（素材层判死）

- 扫描方法：复用 knife_mod.parse_tree 解析 `steamapps\workshop\content\730\<id>\*_dir.vpk`（标准 VPK v2，编号包同构，直接可读）
- 实测：12 张订阅地图共 **6505 个 vmdl_c，0 个武器模型**——duels 对决系列烘焙网格 5963、de_cache_s2 重制 474、其余为靶子/飞艇/装饰
- 泛武器词（gun/sword/katana/hammer/awp…）仅 6 命中且全为误报：soviet_icon_hammer（锤子镰刀装饰）、guncabinet×3（枪柜家具）、awp_miss_button（UI 面板）
- 机制解释：第一人称武器由客户端从 pak01 加载，地图无需也不内置武器模型；CS2 工坊只收录地图类条目，"含刀模型的地图"这个素材类别不存在
- **三层判死闭环**：素材层（工坊无素材，本节）+ 格式层（签名链，上文）→ 模型来源仅限官方 pak01 内原生刀型

### 结论

可用路线只有一条：**pak01_dir.vpk 树条目重指向**（本 skill 方案）。GitHub/Gitee 上的"编译好 VPK mod"同样过不了签名链，拿来挂载没有意义。

## 武器皮肤本地替换 · 贴图模式（`--tex`，默认武器的降级方案）

> **适用范围**：手上一把皮肤都没有、只能改默认武器时用这条路。效果上限是"图案平铺全枪"。
> 若你**拥有**该武器上任意皮肤，请直接看后面的「整材质换肤」——那是官方级效果且改动更少。

换肤与换刀同源：CS2 皮肤映射虽在服务端（items_game.txt 已移除明文），但**全部皮肤渲染资产都在本地 pak01**。把武器默认涂装贴图的树条目重指向皮肤贴图数据即可，`skin_mod.py` 已实现。

### 皮肤资产结构（树内路径）

| 资产 | 路径模式 | 说明 |
|---|---|---|
| 皮肤材质 | `vmat_c:materials/models/weapons/customization/paints/vmats/<kit>` | 每皮肤一个，约 4.5-5KB，preload=0，全在 pak01_501 |
| 皮肤贴图 | `…/paints/custom/workshop/<名>_tga_<hash>`、`…/paints/gunsmith/workshop/…`、`items/assets/paintkits/…` | vmat 内按路径引用，无需单独重指向 |
| 武器基础材质 | `vmat_c:weapons/models/<武器目录>/materials/weapon_*` | 36 个武器统一模式，vmdl 按路径引用 |
| 第一人称检视材质 | `vmat_c:materials/models/weapons/v_models/<目录>/<名>` | 与世界模型材质平行，需一并替换 |
| UI 检视图 | `panorama/images/econ/default_generated/weapon_<武器>_<kit>_<heavy\|light\|medium>_png` | 6264 个，可反推完整 武器×皮肤 映射表（skin_mod 用它自动发现皮肤） |
| legacy 复合材质 | `vcompmat_c:weapons/paints/legacy/<kit>` | 皮肤合成文档，引用 vmats |

皮肤命名前缀 = 合成类型：cu_/gs_/am_/aa_/hy_/sp_/aq_。**皮肤贴图按武器 UV 生成，只能用于对应武器**（AK 的贴图贴不上 AWP）。

### 实验记录（AK47 → 血竞）

| 版本 | 做法 | 结果 |
|---|---|---|
| v1 整 vmat 重指向 | 武器基础材质+检视材质条目 → 皮肤 vmat 数据 | **武器完全透明**（不崩溃、无黑紫）。根因：皮肤 vmat 走运行时合成管线专用 shader（F_PAINT_STYLE 等参数），直接喂给武器渲染输出 alpha=0 |
| v2 贴图级重指向 ✓ | 保持武器原生 vmat/shader 不动，把 `_color` 贴图条目 → 皮肤主贴图条目数据 | **成功**：血竞图案完整铺上枪身，世界模型+第一人称都生效，不透明不崩溃 |

v2 机制：引擎按路径加载 `ak47_default_color_psd_*` 时拿到的是血竞贴图数据；shader 未变所以不透明。皮肤贴图是按武器 UV1 的图案层，直接替换即整体上色。

### 已知局限（v2 贴图模式）

- 图案**平铺全枪**：没有 paintmask 蒙版控制分布，与官方皮肤的分色效果不同（血竞的白底红纹变成整枪图案平铺）
- **皮肤分两类，效果天差地别**：
  - `tga` 单层满铺成品图（如血竞 3.8MB）→ 图案完整 ✓
  - `psd` 图案元素层（如火蛇/咆哮）→ 只有局部贴片，底色靠引擎合成补 → 直接平铺必然不完整 ✗
  - 全池统计：tga 542 个 / psd 491 个；`tex_targets` 已做智能选源（tga 优先 + 大图优先）
- 磨损/质感不变：metalness/roughness/normal 仍是默认涂装
- 检视 UI 大图不变（panorama png，可另行重指向对应皮肤 png）
- 纯视觉：客户端本地渲染层，与服务端库存无交互

### skin_mod.py 用法

```
python skin_mod.py --weapons                  # 列出可换肤武器 (36)
python skin_mod.py --list ak47                # 列出该武器皮肤 (AK47 有 45)
python skin_mod.py --skin ak47 gs_ak47_bloodsport --tex   # 血竞 (贴图模式)
python skin_mod.py --skin m4a4 am_kimono_sunrise --tex --stack   # 叠加第二把
python skin_mod.py --revert                   # 还原全部
python skin_mod.py --audit                    # 审计
```

- `--stack`：叠加到当前补丁之上（多武器同时换装）。带大小保护：当前文件与备份大小不符（被 Steam 还原过）时拒绝执行
- 不带 `--stack` 时从原始备份重建（覆盖此前所有补丁）
- M4A4 特例已修复：panorama 检视图里 M4A4 叫 `m4a1`（老内部名），检视材质目录为 `rif_m4a1`（消音版 `rif_m4a1_s` 专属，不可混用），由 ALIAS / VIEW_ALIAS 表处理
- `batch_random.py`：批量随机换装（只从 tga 满铺成品图池挑选，效果完整）

与 knife_mod 共用同一份 pak01_dir.vpk 与原始备份；不带 `--stack` 的补丁从备份重建（互不叠加），`--revert` 同时还原刀和皮肤。

## 刀皮肤本地替换（实验：效果有限）

刀与枪同源尝试，结论：

| 方案 | 结果 |
|---|---|
| 整 vmat 重指向（刀身材质 → 皮肤 vmat 如 am_marble_fade） | **刀完全透明**——与枪 v1 同根因，F_PAINT_STYLE shader 是合成管线中间材质，喂任何模型都 alpha=0 |
| 贴图模式（karam_color → 共享图案贴图） | 可见但不完整。水转印图集=涂鸦花块；大马士革钢纹=全刀统一花纹；fade 渐变=重复色带（小模板平铺感） |

刀皮肤无预烘焙成品图可用：panorama 检视图是 3D 渲染预览而非 UV 图；皮肤图案全是共享小图（fade 67KB / 大理石纹 264KB / 大马士革 843KB），供引擎按刀 composite_inputs（pos 位置贴图 3.3MB + masks）运行时合成。**刀换肤实用上限 = 纹理平铺，效果远逊枪的 tga 满铺皮肤。**

## 引擎皮肤系统逆向（client.dll，paintseed 机制）

对 `game/csgo/bin/win64/client.dll` (37MB) 的字符串符号逆向，皮肤应用全链路：

**1. 物品数据（服务端 GC 下发）**：`CEconItemPreviewDataBlock` 字段 `paintindex`（皮肤ID）/ `paintwear`（磨损 0~1）/ `paintseed`（图案种子）——即"皮肤种子"，纯服务端数据。

**2. 合成管线 CompositeMaterialSystem**：每皮肤一个 `CCompositeMaterialKit`，含装配程序列表 `m_vecCompositeMaterialAssemblyProcedures`，每个程序三段式：
- `MatchFilters`：匹配哪些模型/部位
- `CompositeInputContainers`：合成输入（pos 位置贴图 + masks 蒙版，即树内 `composite_inputs` vmat）
- `PropertyMutators`（属性变异器，`m_nMutatorCommandType` 枚举）：
  - `RandomRollInputVars`：`SeedInputVar`=paintseed → `InputVarsToRoll`（pattern_offset_x/y、pattern_rotate）在数据定义的 start~end 区间掷随机值
  - `GenerateTexture`：生成贴图写入目标参数；另有 CopyProperty / 条件变异 / DrawText（贴名）等
- 多 pass 渲染到 Render Target 烘焙成品贴图再绑定武器材质；`materials/dev/compositematerials_prewarm/custom_weapon_prewarm.vmat` 预热常用皮肤

**3. paintseed 的本质**：种子 → 掷 pattern_offset_x/y + pattern_rotate → 同皮肤不同种子图案位置不同。这就是官方皮肤"分色/图案位置随机"的来源。

**4. 对本地换肤的边界定论**：
- 皮肤贴图分两类是合成管线的直接后果：`tga` 单层满铺成品（可完整平铺）/ `psd` 合成输入元素（图案层，底色靠蒙版+变异器烘焙补全，绕过管线必不完整）
- ~~官方级效果必须让引擎跑合成管线，本地伪造物品数据此路不通~~ ——**此结论已被推翻，见下节「整材质换肤」**：伪造物品数据确实不可行，但如果你**真拥有**该武器上的任意皮肤，服务端已下发 paintindex，引擎本来就会跑完整管线；此时只把"已拥有皮肤"的材质条目重指向"想显示皮肤"，即得官方级效果（蒙版/磨损/paintseed 全部保留）
- 引擎含调试命令痕迹 `set item texture seed`（工具模式用，游戏内不可用）
- 想预览某皮肤官方效果：直接看树内 `panorama/images/econ/default_generated/weapon_<武器>_<kit>_heavy_png`（烘焙成品预览图）

## 整材质换肤（拥有皮肤 → 引擎跑完整合成管线）★ 最终方案

上一节"此路不通"的前提是**默认武器没有皮肤 kit**。只要你真拥有该武器上的任意皮肤，
服务端就下发 paintindex，客户端按 kit 名找到材质资源，引擎照常跑
CompositeMaterialSystem（蒙版裁剪/磨损/污渍/法线/paintseed 随机全部生效）。
我们只把**已拥有皮肤的材质条目**重指向**想显示皮肤的材质条目**——配方换了，管线一行没动。

查找链：`paintindex` → kit 名 → 材质资源条目 →（vmat 或 vcompmat）→ 贴图绝对路径

因此整份换肤只需重指向 **1~2 个**树条目，比贴图模式少一个数量级，效果却是官方级。

### v1 全透明与本次成功的根本区别

| | v1 整 vmat 重指向（武器全透明） | 整材质换肤（成功） |
|---|---|---|
| 目标条目 | 武器渲染材质 `weapon_*` | 皮肤材质 kit 自身 |
| 源数据 | 皮肤 vmat（合成管线中间产物） | 皮肤 vmat / vcompmat |
| 角色关系 | **跨角色**（皮肤 → 武器 shader） | **同角色**（皮肤 → 皮肤） |
| 结果 | shader 不吃，输出 alpha=0 | shader 同名同构，正常渲染 |

### 两种资源形态（legacy / composite）

| 形态 | 判据 | 树内资源 | 内容 |
|---|---|---|---|
| **legacy** | 有 `vmats/<kit>.vmat` | vmat + vcompmat 两条 | vmat 4.2~4.9KB 完整材质（贴图绝对路径）；vcompmat 1.4~1.7KB，是 `CCompositeMaterialEditorDoc` 的**单节点图**（一个 `SPECIFIC_MATERIAL` 节点，`m_strSpecificMaterial` 转交给该 vmat） |
| **composite** | items_game 带 `composite_material_path`，**无 vmat** | 仅 vcompmat 一条 | 5.2~8.1KB 完整合成节点图（`AssemblyProcedure` + 贴图引用 + `MatIncludes` 模板） |

全池 1387 个 kit 的 style × 形态交叉统计：

| style | legacy | composite |
|---|---|---|
| 7 | 343 | 45 |
| 9 | 187 | 117 |
| 1 / 2 | — | 有（如 `soe_bw_the_end_awp` / `hy_varicamo_simple_yellow`） |

**style 不是分界线，资源形态才是**——style 7 里有 45 个 composite，composite 里还有 style 1/2。

形态不一致、跨武器这两类配对，不加 `--force` 时会被 `skin_mod.form_of()` / `swap_targets()` 拦下：
它们已经不是"同 UV 同角色"的安全组合。但**跨形态并非绝对不可行**，实测见下节。

### 实测记录

| 入口（拥有） | 目标（显示） | 形态 | 结果 |
|---|---|---|---|
| `cu_ak47_mastery` 精英之作 | `cu_fireserpent_ak47_bravo` 火蛇 | legacy→legacy（style 7→7） | ✓ 蛇纹+底色+磨损，构图正确，与官方检视一致 |
| `cu_ak47_mastery` | `cu_ak_island_floral` 野荷 | legacy→legacy（style 7→7） | ✓ |
| `cu_awp_vein` 毛细血管 | `cu_medieval_dragon_awp` 巨龙传说 | legacy→legacy（style 7→7） | ✓ |
| `hy_red_hex` 变频器 | `cu_m4a1_howling` 咆哮 | legacy→legacy（**style 2→7**） | ✓ |
| **`am_bronze_sparkle` 青铜装饰** | **`gs_deagle_fennec` 沙漠之狐** | legacy→legacy（**style 5→9**） | ✓ |
| `m4a4_green_camo` 战鹰 | `cu_m4a1_howling` 咆哮 | **composite→legacy**（style 9→7） | ✗ 模板错乱（跨形态，见下节） |
| `awp_tempered` 镀铬大炮 | `awp_queens_gambit` 后翼弃兵 | composite→composite（style 9→9） | ✓ |
| `m4a4_green_camo` 战鹰 | `m4a4_falak` 吞天巨蛇 | composite→composite（style 9→9） | ✓ |
| **`deagle_calligraff` 书法涂鸦** | **`cu_glitter_deagle` 星尘拱廊** | composite→composite（**style 9→7**） | ✓ |
| `gs_m4a1s_insomnia` 夜无眠 | `cu_m4a1_snake` 冒险家乐园 | legacy→legacy（**style 9→7**） | ✓ 蛇鳞+grunge+磨损 |
| `sporty_hunter` 大型猎物 | `sporty_purple` 潘多拉之盒（手套） | legacy→legacy | ✓ |

结论：**同形态即互通，与 style 无关、与"皮肤新旧"无关。**

这一点已被正交实验坐实——同一批样本里 style 相同和不同都成功，唯一失败的样本（战鹰→咆哮）是跨形态：

| 实验 | 形态一致 | style 一致 | 结果 |
|---|---|---|---|
| 精英之作 → 火蛇 | ✓ | ✓ | ✓ |
| 变频器 → 咆哮 | ✓ | ✗（2→7） | **✓** |
| 青铜装饰 → 沙漠之狐 | ✓ | ✗（5→9） | **✓** |
| 书法涂鸦 → 星尘拱廊 | ✓ | ✗（9→7） | **✓** |
| 战鹰 → 咆哮 | **✗** | ✗ | **✗** |

也就是说 style 只有 1、2、3、5、7、9、10 共同出现过在成功样本里，它决定的是**图案在 UV 上的铺法**（hydrographic/阳极/喷绘/枪匠），但材质条目的装载方式与它无关。工具无需收紧到"形态 + style 双匹配"，`form_of()` 单条拦截已经足够。

### 跨形态 / 跨武器（`--force`）★ 后续实测推翻了"跨形态必崩"

关键事实：**legacy 的 vcompmat 不是"空壳声明"，而是 `CCompositeMaterialEditorDoc` 的合法最小图**——
一个 `SPECIFIC_MATERIAL` 节点把材质转交给 `vmats/<kit>.vmat`。它和 composite 的节点图**同一个文档类、同一个版本号**，
只是少画了几十个节点。所以把 composite 槽位指向 legacy 文档，喂进合成器的是**合法文档**而不是损坏文档。

第二个前提：**入口永远是 vcompmat 那一条**（`items_game` 的 `composite_material_path` 指向它）。
文档内部用绝对路径引自己的 vmat 与贴图，因此跨形态时**只改 1 条**，不需要搬 vmat、也不需要搬贴图。

| 实验 | 关系 | 结果 |
|---|---|---|
| `m4a4_green_camo` 战鹰 → `cu_m4a1_howling` 咆哮 | composite→legacy，同武器 | ✗ 图案错乱 |
| `mp9_nexus` 中枢 → `am_doppler_phase2` 多普勒 | **composite→legacy，跨武器（刀→冲锋枪）** | ✓ 粉红大理石，构图完整 |
| `mp9_nexus` → `am_sapphire_marbleized` 蓝宝石 | 同上 | ✓ 蓝色 |
| `mp9_nexus` → `am_blackpearl_marbleized` 黑珍珠 | 同上 | ✓ 深底彩光 |
| `gs_m4a1s_insomnia` 夜无眠 → `cu_m4a1_snake` 冒险家乐园 | legacy→legacy，同武器同形态 | ✓ |

结论：**跨形态不是硬墙，但也不保证**——同样是 composite→legacy，战鹰→咆哮 失败而 中枢→多普勒 成功。
尚未隔离出根因，两个候选（都未证实）：

1. 目标 legacy 的 style：咆哮是 style 7（hydrographic，图案靠 paintmask 分色），多普勒/宝石是 style 5（阳极，程序化渐变）。composite 槽位没有自己的 paintmask，跑分色逻辑可能取到空图
2. 跨武器反而更"干净"：中枢本身没有图案可错乱，一切是外来材质整体覆盖

按**逐例实测**处理：文档只记录已验样本，`cmd_swap` 会把风险逐条打印出来再要 `--force`。

### composite 图谱为什么能整份移植

- 图谱内所有引用都是**绝对路径**（`items/assets/paintkits/<系列>/<kit>_albedo_texture_*.vtex` 等），自带完整 PBR 图（albedo / normal / roughness / AO / material_mask，最大单张法线 13MB）。图**数量不固定**：千瓦收藏品那批是 5 张齐全，而 `set_graphic_design` 系列的 `cu_glitter_deagle` 星尘拱廊只有 albedo(11.3MB) + roughness(7.5MB) + sfx_mask(3.3MB) 三张，AO/metal 借用 `materials/default/` 共享图
- **名字带 `cu_` 不等于 legacy**：星尘拱廊 style 7、名字老派，但无 vmat、贴图在 `items/assets/paintkits/set_graphic_design/` 下、走节点图装配，`form_of()` 判定为 composite。判形态只能看有没有 `vmats/<kit>.vmat`
- 两份不同 kit 的图谱**逐字节级同构**：尾部节点字节几乎完全相同，只有数值参数与贴图路径不同
- `Identifier` 字段只是节点 KV3 键名，不绑定 kit 名，不会被校验
- 这类皮肤由画师交付成品图，没有 paintseed 程序化铺贴，因此**不存在**贴图模式那种"图案平铺、构图散掉"问题，效果天生与官方一致
- 目录不按 kit 名走：`weapons/paints/community/community_NN/<kit>`（按收藏品编号）与 `weapons/paints/set_arabesque/<kit>`（按系列）混用（吞天巨蛇与无上之焰同属 `set_arabesque`），配对必须按 kit 名末端匹配，不能用固定前缀

### 贴图引用的解析陷阱（曾长期误报"缺图"）

拿正则 `[\x20-\x7e]{6,}\.vtex` 在 vmat/vcompmat 原始字节里扫引用，会**从被长度字节切碎的残留片段起头**，产出 `ao_tga_9627e701`、`_psd_25c027da`、`_tga_b0d8345c` 这类伪路径。

全量统计：23540 个材质条目共 208671 条引用，其中 **75235 条（36%）是碎片**。表现就是校验时稳定报"缺 1~2 张图"，每次都要人工排查一遍。

正确做法是**从树里 `vtex_c:` 条目自动推导顶层目录白名单**，只保留以真实根开头的完整路径：

```
agents/ characters/ compmatcache/ dev/ gloves/ items/ materials/
models/ panorama/ particles/ patches/ stickers/ textures/ weapons/ workshop/
```

`skin_mod.vtex_refs()` 已按此实现，修完后所有目标 kit 的"缺图"归零。

顺带一个相关坑：新版 kit 的贴图在 `items/assets/paintkits/` 下（不是 `materials/`），所以任何按 `materials/` 或 `paints/` 过滤的逻辑都会把它们筛空——`tex_targets()` 的源筛选必须同时认 `paints/` 与 `paintkits/`。

### 局限

- 必须**真拥有**该武器上的皮肤（服务端下发 paintindex），否则引擎不进合成流程
- 默认只在同一把武器内换（贴图按武器 UV 生成）。跨武器必须 `--force`：图案按目标武器的 UV 重新展开，能不能看只能实测（刀→枪已验证）
- 跨形态同样必须 `--force`，且**结果不稳定**（同一组合有成功也有失败样本），只能逐例试
- 一个入口皮肤 = 一个可显示槽位。想同时看多个皮肤，需拥有多个入口（每个入口单独打补丁，互不冲突，`--stack` 叠加）；同一槽位换第二款是覆盖，不是并列
- 背包/检视 UI 图标不变（预烘焙 panorama png）

## 程序化材质族：多普勒与宝石系（`am_*_marbleized`）

刀具皮肤里有一族公用 `csgo_paint` + `anodized_multi` 的材质，**全部 legacy、style 5**，武器侧共 26 个 kit。
它们不依赖 paintmask 分色，只有一张程序化底图 + 一组色相参数，所以是"跨武器试探"最好的试验场。

| 族 | kit | 视觉 |
|---|---|---|
| 多普勒（原版） | `am_doppler_phase1`~`phase4`，变体 `_widow`×4、`phase2_b` | 四个阶段的 vmat **逐字节只差 355~411 字节**（绝大部分是材质名字符串），挂到枪上几乎同色 |
| 伽玛多普勒 | `am_gamma_doppler_phase1`~`phase4`，每个另有 `_glock` 版 | 与多普勒差 2808 字节，绿系 |
| 宝石系 | `am_sapphire_marbleized`(蓝) `_b`、`am_ruby_marbleized`(红)、`am_emerald_marbleized`(绿) `_glock`、`am_blackpearl_marbleized`(黑) `_b` | 彼此差 2500~2700 字节，颜色烘死在参数里 |
| 渐变大理石 | `am_marble_fade` `_widow` | 同 shader 家族，但严格说不属多普勒 |

**换阶段编号不会变色**：刀上的"第几阶段"色相来自 paintseed 落在哪个区间（服务端物品数据），四个阶段的材质本身同构。
想要确定的颜色只能走宝石系——`sapphire` 蓝、`ruby` 红、`emerald` 绿、`blackpearl` 黑。

`blackpearl` 的底图是 `anodized_multi/smoke_psd_779d5513`（多普勒/蓝绿宝石用 `smoke2_psd_cdf5ba83`），
纹路更细，同一套 shader 下彩光最强、整体最暗。

`_glock` / `_widow` 后缀是按特定武器 UV 调过构图密度的变体，换到别的枪上可以对比着看，但同样不保证对位。

随时用 `--family <正则>` 查同族（`--family doppler`、`--family "sapphire|ruby"`、`--family emerald` 会连手套的 `specialist_emerald_web` 一起列出）。

## 手套整换材质（--glove）

手套是独立体系（`gloves/paints/`），但资源形态比武器**更规整**：

- **72 个 kit / 7 家族**：bloodhound 8、brokenfang 4、handwrap 12、motorcycle 12、slick 12、specialist 12、sporty 12
- **全部 legacy 形态**：每 kit 恒定 2 条（`vmat_c:gloves/paints/<kit>` 约 7.8KB + `vcompmat_c:gloves/paints/<kit>` 约 1.6KB 声明），**没有 composite 变体** → 不存在武器那条形态陷阱
- 家族从 vmat 内引用的 `characters/models/shared/arms/glove_<family>/` 路径解析
- **同家族 UV 同源**：实测大型猎物与潘多拉之盒的 AO（`eb5235b4`）与法线（`78a7ad1a`）**指向同一张贴图**，只有 mask 不同（`3685129a` vs `953141db`）
- **跨家族不行**：kit 自带的 mask/normal 按该家族手部 UV 绘制，而模型仍是本家族的 → 花纹错位。要跨家族必须连 `glove_<family>` 模型一起换（未验证，且会连带影响库存里所有同家族手套）
- 手套 kit 的 `vmt_path` 字段写作 `materials/models/weapons/customization/paints_gloves/<kit>.vmat`，但树内实存条目是 `gloves/paints/<kit>`，**两者不一致**，实际可操作的是后者

### 命名陷阱（手套 kit 名与中文名完全不对应）

| 中文名 | kit |
|---|---|
| 潘多拉之盒 | `sporty_purple`（**不是** `sporty_pandoras_box`） |
| 树篱迷宫 | `sporty_green` |
| 双栖 | `sporty_poison_frog_blue_white` |
| 大型猎物 | `sporty_hunter` |
| 超导体 | `sporty_light_blue` |
| 迈阿密风云 | `sporty_blue_pink` |

中文名必须查 `resource/csgo_schinese` 的 `PaintKit_<kit>_tag`（`skin_mod.cn_names()` 已内化，武器与手套共用），不能按字面猜。

### 数据里的废弃条目

- `am_tiger_silver`、`cu_whiteout_awp`、`hy_varicamo_red_awp`：只在 panorama 检视图里残留图标，`items_game` 无定义、树内无材质 → 永远加载不到，不可作为目标
- `awp_ice_coaled`：`description_string` 被错误指向 `#PaintKit_cu_ak47_cogthings`（Valve 数据 bug），游戏中显示名是错的
- `sporty_jaguar`：`items_game` 有完整定义（带 vmt_path），但树内无任何资源

### 命令

```
python scripts/skin_mod.py --gloves                        # 72 个手套皮肤按家族分组列出
python scripts/skin_mod.py --glove sporty_hunter sporty_purple --stack   # 大型猎物 → 潘多拉之盒
python scripts/skin_mod.py --swap ak47 cu_ak47_mastery cu_ak_island_floral --stack
python scripts/skin_mod.py --list m4a4                     # 带 [legacy]/[composite] 标记
python scripts/skin_mod.py --revert                        # 一步还原（刀 + 皮肤 + 手套）
python scripts/skin_mod.py --audit                         # 审计
```




## 风险边界

- 引擎完整性检查（哈希自洽）可绕过 ≠ VAC 不检测；VAC 逻辑不公开、封禁延迟执行，无法经验性证伪
- CS:GO 时代纯本地视觉替换无公开确认的 VAC 封禁案例，但这是经验不是保证
- 实操守则：VAC 官方局先 --revert（1 秒），离线/社区服随意

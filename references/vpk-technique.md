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

## 武器皮肤本地替换（paint kit 贴图重指向，已验证）

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
- 磨损/质感不变：metalness/roughness/normal 仍是默认涂装
- 检视 UI 大图不变（panorama png，可另行重指向对应皮肤 png）
- 纯视觉：客户端本地渲染层，与服务端库存无交互

### skin_mod.py 用法

```
python skin_mod.py --weapons                  # 列出可换肤武器 (36)
python skin_mod.py --list ak47                # 列出该武器皮肤 (AK47 有 45)
python skin_mod.py --skin ak47 gs_ak47_bloodsport --tex   # 血竞 (贴图模式)
python skin_mod.py --revert                   # 还原
python skin_mod.py --audit                    # 审计
```

与 knife_mod 共用同一份 pak01_dir.vpk 与原始备份，补丁均从备份出发互不叠加；`--revert` 同时还原刀和皮肤。



## 风险边界

- 引擎完整性检查（哈希自洽）可绕过 ≠ VAC 不检测；VAC 逻辑不公开、封禁延迟执行，无法经验性证伪
- CS:GO 时代纯本地视觉替换无公开确认的 VAC 封禁案例，但这是经验不是保证
- 实操守则：VAC 官方局先 --revert（1 秒），离线/社区服随意

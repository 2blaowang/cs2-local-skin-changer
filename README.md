# CS2 默认刀换蝴蝶刀（VPK 覆盖法）——原理、踩坑与边界

> 把 CS2 的默认刀（CT/T）换成蝴蝶刀模型 + 完整检视动画，**不修改任何官方游戏文件**。
> 本仓库记录完整的实现脚本、踩过的每一个坑、以及"哪些能换、哪些换不了"的最终结论。
> 仅供学习研究与离线个人使用，请先读[免责声明](#免责声明)。

## 效果

- 默认刀（CT/T 双方）显示为蝴蝶刀模型；
- 出刀 / 轻重击 / 背刺 / **检视转刀动画全部为蝴蝶刀行为**；
- 官方游戏文件（pak01 等）一个字节都不动，Steam"验证文件完整性"前始终保持可回滚。

## 原理

CS2 的 Source 2 文件系统按 `gameinfo.gi` 的 `SearchPaths` 顺序加载内容，**先挂载的路径优先**。本方案把一个自制的未签名 VPK 挂在官方 `pak01` 之前：

```
game/csgo/gameinfo.gi:
    SearchPaths
    {
        Game_LowViolence  csgo_lv
        Game  csgo/custom/butterfly_knife.vpk   ← 插入这一行（优先级高于 csgo）
        Game  csgo                              ← pak01 在这里
        ...
    }
```

VPK 内含 5 条**路径覆盖**（同名路径命中时优先返回我们的数据）：

| # | 覆盖路径 | 内容 |
|---|---|---|
| 1 | `weapons/models/knife/knife_default_ct/weapon_knife_default_ct.vmdl_c` | 蝴蝶刀模型（179,961 字节，从 pak01_462 提取） |
| 2 | `weapons/models/knife/knife_default_t/weapon_knife_default_t.vmdl_c` | 同上 |
| 3 | `animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_ct.vnmgraph_c` | 蝴蝶刀完整动画图（8,335 字节） |
| 4 | `animation/graphs/viewmodel/viewmodel_knife.vnmgraph+default_t.vnmgraph_c` | 同上 |
| 5 | `cfg/butterfly_check.cfg` | 挂载自检标记（`exec butterfly_check` 用） |

**为什么必须连动画图一起换**：CS2 每把刀的动画由独立的动画图（`vnmgraph`）驱动。默认刀的动画图只会请求默认刀的动画数据，而蝴蝶刀招牌的检视转刀（lookat01/02/03 三段）内嵌在它**专属**的动画图 `viewmodel_knife_butterfly.vnmgraph_c` 里——只换模型不换图，检视就等于没有。Source 2 的 `+variant` 文件是**完整编译图**（不是差分补丁），把默认刀的两个变体文件内容整体替换为蝴蝶刀图即可，图中引用的 16 个蝴蝶刀动画片段（vnmclip）全部原生存在于 pak01_473，零数据改动。

**为什么不能直改 pak01**：官方 pak01 带签名，且引擎运行时对每次读取的 1MB 窗口做 BLAKE3/MD5 哈希校验（tier0.dll 的 `CBlake3HashContext::ProcessSingleBuffer`），不匹配直接 fatal 崩溃。本文的教训之一（详见踩坑 #1）。

## 仓库内容

```
├── README.md                       本文档
├── LICENSE                         MIT
├── scripts/
│   ├── build_butterfly_vpk.py      构建 VPK（含格式回读自检，从你本机 pak01 提取蝴蝶刀资产）
│   ├── install_butterfly.py        安装（复制 VPK + 修改 gameinfo.gi，幂等，自动备份）
│   ├── rollback_butterfly.py       一键回滚（还原 gameinfo + 删除 VPK）
│   ├── vpk_inspect_min.py          极简 VPK 检查器（解析/校验任意 Source 2 VPK）
│   └── unlock_pet.py               解锁 Workshop Tools 的 Particle Editor（附加成果）
└── reference/
    └── graph_offsets.json          pak01_373 中全部刀动画图文件的偏移表（调研数据）
```

脚本默认硬编码了 Steam 标准安装路径 `c:\Program Files (x86)\Steam\...`，装在别处请改文件头部的 `GAME` 常量。脚本只从**你本机的游戏安装**提取数据，仓库本身不包含、也不分发任何 Valve 游戏资产。

## 快速开始

1. 关闭 CS2；
2. `python scripts/build_butterfly_vpk.py` —— 从本机 pak01 提取蝴蝶刀模型并构建 VPK（内置回读自检：树解析对齐、三段哈希、全部条目 CRC）；
3. `python scripts/install_butterfly.py` —— 安装（自动备份 `gameinfo.gi` → `gameinfo.gi.bak_butterfly`，幂等可重复运行）；
4. 启动 CS2，离线/人机进图，按 `3` 切刀，按检视键看转刀；
5. 想还原：`python scripts/rollback_butterfly.py`。

## 踩坑记录（时间线，每条：现象 → 原因 → 解法）

### #1 直接修改 pak01 必崩
- **现象**：直接改 pak01_dir.vpk 的树/数据（哪怕重算全部 MD5），进图秒崩，minidump 指向 filesystem_stdio.dll。
- **原因**：引擎运行时对每次读取的 1MB 窗口按哈希条目类型（type 0=MD5，type 1=BLAKE3-128）计算并比对，签名包不匹配即 fatal。
- **解法**：放弃直改，改用 SearchPaths 覆盖挂载——这才是本仓库的方案。

### #2 VPK 树格式：每个目录都要独立的空文件名终结符
- **现象**：自制 VPK 被独立解析器读出乱码条目（`len=1717920863` 之类），树解析字节数超限。
- **原因**：VPK 目录树是三层嵌套：`扩展名\0 { 目录\0 { 文件名\0 条目 } 空文件名\0 } 空目录名\0` **空扩展名\0**。**每个目录的文件列表结束后必须有一个空文件名（`\x00`）终结符**，漏写后解析器会把下一个目录名当文件名读，全盘错位。
- **解法**：构建器在目录循环内补 `\x00`；用 169 字节的官方 karambit.vpk 树逐字节反推验证了结构。

### #3 other_md5 三段哈希公式（逆向自官方文件）
V2 VPK 的 other_md5 区（48 字节）三段依次为：
1. `md5(tree)`；
2. `md5(archive_md5 区)`——无该区时即 `md5(b"")`；
3. `md5(文件头 + tree + 数据区 + archive_md5 区 + 前两段哈希)`——即"到前两个校验和为止的全部内容"。
验证方法：拿官方社区 VPK（karambit.vpk，omd5=48）算三个候选命中第三段。手搓 VPK 时按此公式填，引擎加载即认可。

### #4 gameinfo.gi 编辑：少一个换行符 = 基础内容全丢
- **现象**：插入挂载行后游戏启动即异常。
- **原因**：替换串漏了行尾换行，挂载行和 `Game csgo` 挤到同一行——**挂载行尾的 `//` 注释把后面的 `Game csgo` 一起吞成了注释**，基础内容路径整个消失。
- **解法**：编辑后必须字节级复核（锚点行独立成行、出现次数、与备份的长度差 = 插入行长度）。Valve 配置文件是 CRLF，编辑时保持。

### #5 挂载优先级：SearchPaths 先到先得
自定义条目必须放在 `Game csgo` **之前**（`Game_LowViolence csgo_lv` 排第一就是官方自己的覆盖先例）。放后面等于没挂。

### #6 如何证明"挂载生效"：NTFS LastAccessTime 及其坑
- 启动游戏 30 秒后查 VPK 的 `LastAccessTime`，跳变即引擎读取过（需 `fsutil behavior query disablelastaccess` 显示 ENABLED）；
- **坑**：NTFS 对"近期访问过"的文件会抑制访问时间更新（同一文件短时间内二次访问可能不刷新），所以"没变"不能证明"没挂"——最终以游戏内效果为准。

### #7 检视动画缺失：动画图架构（本项目最大的知识收获）
CS2 武器动画架构（从 pak01 实测反推）：
- **共享骨架**：`animation/skeletons/characters/viewmodel.vnmskel`（第一人称手臂+武器装配体）；
- **动画片段**：`animation/anims/viewmodel/knife/<刀名>/*.vnmclip_c`（draw / heavy_* / light_* / idle / **lookat01-03 = 检视转刀**）；
- **刀动画图**：`animation/graphs/viewmodel/viewmodel_knife.vnmgraph_c` 为基础图，内含全部变体路径表；每把普通刀一个变体 `viewmodel_knife.vnmgraph+<刀名>.vnmgraph_c`（**完整编译图**，不是差分），引用该刀自己的片段；检视系统另有一套 `viewmodel_inspects.vnmgraph+<武器>`（如 `+knife_default_ct` 只引用一个 `lookat01` 片段）；
- **特殊刀**：蝴蝶刀 / 爪刀 / 阔剑没有 `+变体`，而是**独立完整动画图**（`viewmodel_knife_butterfly.vnmgraph_c` 等）——检视转刀内嵌其中，不经 inspects 系统。
- **推论**：换刀模型必须把默认刀的两个变体图替换为目标刀的图；`graph_offsets.json` 是 pak01_373 里全部相关文件的偏移表。

### #8 Workshop Tools 的粒子编辑器默认被 Valve 禁用
- **现象**：装了 Workshop Tools（Steam DLC，appid 2678630 是原声集，Tools 在 CS2 属性→DLC 里勾选）也找不到粒子编辑器。
- **原因**：`game/bin/sdkenginetools.txt` 里 pet 工具带 `m_ExcludeFromMods = ["csgo"]`；`game/bin/assettypes_common.txt` 里 `particle_asset` 带 `m_HideForRetailMods = ["csgo"]`——工具本体（pet.dll）其实随 DLC 安装了。
- **解法**：各注释一处（`scripts/unlock_pet.py` 自动完成，备份 *.bak_pet），粒子编辑器 + `CompileParticle` 资产编译通道立即可用。附带发现 animgraph_editor 也被同样排除（但 DLL 未随 CS2 分发，解锁无效）。

### #9 Tools 的内容树：源文件必须放 `content\`，不是 `game\`
- **现象**：粒子编辑器 File→Open 提示 "outside of the directory required for game content: ...\content\csgo\"。
- **原因**：Source 2 工具链是双树布局——`content\` 放**源文件**（KV3 文本），`game\` 放**编译产物**。addon 的源在 `content\csgo_addons\<addon>\`，编译输出自动落到 `game\csgo_addons\<addon>\`。
- **另**：启动参数带 `-retail` 时疑似禁用源文件加载（Asset Browser 搜不到文本资产），去掉即可。

### #10 Tools 的 `-addon` 参数决定当前 Mod
`cs2.exe -addon <名字> -tools` 启动，Asset Browser 只索引该 addon。搜不到文件先检查启动的是哪个 addon（进程命令行 `Get-WmiObject Win32_Process` 可查）。文本源文件在工具启动后才放进 content 树的，需要重启工具重建索引。

### #11 地图文件（vmap）是二进制 DMX
不能文本手改，实体编辑只能走 Hammer。模板地图可直接复制到 addon 的 `maps\` 后在 Hammer 里打开改。

### #12 默认手套换不了：手臂烘焙在角色模型里（本仓库另一个"无效结论"的完整证据链）
- **尝试**：覆盖 items_game 里默认手部物品（5028 `t_gloves` / 5029 `ct_gloves`）的 `model_player` 指向文件（`agents/models/shared/arms/glove_fingerless/hardknuckle.vmdl_c`）→ VPK 挂载确认读取（NTFS 访问时间），**游戏内仍是默认手套**。
- **反编译揭示真相**：这两个手套模型内嵌 `icon_pose` / `inspect_loop` 网格组——它们只用于**库存图标与检视展示**；
- **真正的默认第一人称手臂**：烘焙在**每个角色模型**内部——`agents/models/ctm_fbi/ctm_fbi.vmdl_c` 含 `ctm_fbi_firstperson_default_gloves_arms2.dmx`（931KB）等网格组，30+ 个角色各自一套（items_game 里 `hands` prefab 的 `player_bodygroups { gloves 0 }` 即此机制）。
- **结论**：改默认手套 = 重建全部角色模型，不可行。想看别的手套 = 游戏内获得真实手套饰品（装备后走 `model_player` 通道，机制已验证可用）。

### #13 第一人称粒子/拖尾：四路验证全部无通道
想给第一人称的刀挂粒子（拖尾），以下路径逐一验证均不通：
1. `items_game.txt`（8.4MB 全文查证）：无通用粒子挂载键；仅有的 `muzzle_flash_effect / tracer_effect / heat_effect / eject_brass_effect / rumble_effect` 是**枪械代码消费的语义槽**，刀永不触发；
2. **脚本 API**（cs_script/point_script，255 个方法逐个过）：无粒子生成/附着接口（有 Glow/SetParent/Teleport/SetThink/OnKnifeAttack，唯独没有粒子）；
3. **模型内嵌**：CS2 模型不内嵌粒子引用（角色/武器模型字符串扫描零命中）；
4. **地图实体**（env_particle_glow + cs_script 动态绑定玩家武器，实测可跑）：粒子只能世界空间，实际效果是**人物拖尾**而非第一人称刀拖尾。
- 附加成果：粒子本体可自制——Workshop Tools 粒子编辑器按 #8 解锁后，手写 KV3（`C_OP_ContinuousEmitter` + `C_OP_RenderRopes` 绳带渲染器即拖尾）可编译出 `vpcf_c`；测试 addon（env_particle_glow 引用自制粒子 + point_script 每回合把玩家武器重命名以绑定 CP0）可玩。

### #14 VAC"无签名文件"警告：不是封禁
自定义 VPK 无签名（签名字段只有 Valve 能生成，私钥不出官方；复制官方签名块也会因内容哈希不符而无效——**不要尝试**；改引擎跳过校验更是账号级风险）。后果仅为：**无法加入 VAC 安全服务器**（官方匹配/竞技/休闲），离线、人机、第三方平台不受影响。要打官匹先 `rollback_butterfly.py`，打完再装回。pak01 等官方文件全程未动，MD5 可随时比对验证。

### #15 杂项坑
- Valve 配置文件是 CRLF，脚本编辑必须保真（universal newline 会吃 `\r`）；
- PowerShell 内联 Python 的引号地狱：含 `\"` 的多行 python -c 必炸，一律写成脚本文件跑；
- 自制 VPK 的挂载验证别只信 NTFS 访问时间（见 #6），进游戏看效果才是终审；
- Valve 的 `gameinfo.gi` 用三段式注释 `//`，追加行保持原缩进风格（Tab）。

## 能换 / 不能换 清单（VPK 覆盖法边界）

### ✅ 已验证可行
- **武器模型替换**：任意"结构同构"的 `vmdl_c` 路径覆盖（默认刀 → 蝴蝶刀）；
- **武器动画图变体替换**：`viewmodel_knife.vnmgraph+<变体>` 整文件替换为目标刀的图（换模型必配套）；
- 同机制可推广到一切"按路径加载的资产"——规则只有一条：**路径命中即优先返回，格式合法即接受**。

### ❌ 已验证无效
- **默认手套**（烘焙在 30+ 角色模型，见 #12）；
- **第一人称粒子/拖尾**（无挂载通道，见 #13）;
- **直接修改 pak01 / 伪造签名**（哈希校验 + 私钥不可得，见 #1/#14）。

### ⚠️ 理论可行、未在本项目验证
- 声音事件覆盖（`vsnd_c` 路径覆盖）；
- 材质覆盖（`vmat_c` 路径覆盖——注意纹理依赖与 UV 一致性）；
- 枪械模型互换（同结构枪之间应同理成立）；
- 需要 Workshop Tools 的：粒子自制（已验证可编译）、模型重建（DMX 导入 ModelDoc，工程量大）。

## 技术参考

### VPK v2 格式速查（Source 2 实测）
```
头(28B):  u32 sig=0x55AA1234 | u32 ver=2 | u32 tree_size |
          u32 file_data_size | u32 archive_md5_size | u32 other_md5_size | u32 signature_size
树:       ext\0 { dir\0 { name\0 + 条目18B + preload } 空文件名\0 } 空目录名\0   … 空扩展名\0
条目18B:  <IHHIIH> = crc32 | preload_len | archive_idx(0x7FFF=内联) | data_off | data_len | 0xFFFF
数据区:   紧跟树之后，内联条目 offset 相对数据区起点
布局:     头 + 树 + 数据区 + archive_md5区 + other_md5区 + 签名区
```
other_md5（48B）三段：`md5(tree)` ‖ `md5(archive_md5区)` ‖ `md5(头+树+数据区+archive_md5区+前两段哈希)`。

### 关键文件位置（本机 pak01 实测，版本 2026-10 前后）
| 资产 | 位置 |
|---|---|
| 蝴蝶刀模型 `weapon_knife_butterfly.vmdl_c` | pak01_462 @ 100,734,688（179,961 B，CRC32 0x96D25BC6） |
| 刀动画图基础 + 17 变体 | pak01_373 @ 2,137,040 起（base 8504B；+default_ct 8038B / +default_t 8075B） |
| 蝴蝶刀独立动画图 | pak01_373 @ 2,297,760（8,335B） |
| 检视动画图系统 | pak01_386 @ 92,914,464 起（base 15,020B；+knife_default_ct 4,916B） |
| 刀动画片段（含 lookat01-03） | pak01_473 @ 17,807,648 起 |
| 共享 viewmodel 骨架 | `animation/skeletons/characters/viewmodel.vnmskel`（各动画图引用） |
| 蝴蝶刀材质 | pak01_45/27/166/177（color 4.1MB / rough / AO / masks） |
| items_game.txt（纯文本 8.4MB） | pak01_502 |

### 挂载与验证
- gameinfo.gi 的 SearchPaths 顺序即优先级（先挂者优先）；
- 挂载证据：NTFS LastAccessTime（注意节流，见 #6）+ 游戏内效果终审；
- 自检：`vpk_inspect_min.py` 可解析/校验任意 Source 2 VPK（含无哈希区手搓包）。

## 免责声明与许可

- 本项目**不分发任何 Valve 游戏资产**——所有脚本从使用者本机的 CS2 安装中提取数据；请勿把生成的 VPK、导出的模型/贴图、反编译产物提交到本仓库或任何公开渠道（Valve 版权物）。
- 仅供个人学习研究与离线使用。修改游戏文件违反 Valve 订阅者协议的风险由使用者自行承担；自定义 VPK 为无签名文件，加入 VAC 安全服务器会被拒绝（见踩坑 #14，这不是封禁但请如实知悉）。
- 与 Valve、Perfect World 及任何第三方平台无关。
- 代码以 MIT 许可发布，见 [LICENSE](LICENSE)。

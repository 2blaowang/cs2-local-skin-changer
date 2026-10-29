# CS2 本地视觉替换工具（换刀 + 换肤 + 换手套）

四个功能，同一套 VPK 树条目重指向技术：

1. **换刀**：把默认刀（T/CT 双阵营）本地替换为任意 19 种原生刀型（蝴蝶刀、爪子刀、M9 刺刀等，原色外观）
2. **换肤（整材质）**：真拥有任意一款皮肤时，把它整份换成另一款——引擎照常跑完整合成管线（蒙版裁剪/磨损/污渍/法线/paintseed），**官方级效果，只改 1~2 个条目**
3. **换手套**：72 个手套皮肤按 7 个家族分组，同家族内互换
4. **跨武器试探**（`--force`）：把刀的材质挂到枪上，比如 MP9 中枢 → 多普勒 / 蓝宝石 / 黑珍珠

纯本地视觉修改，无网络行为，不分发任何游戏资产。

- 一条命令切换 / 一键回滚 / 全量审计自检
- 只重写 VPK 目录树条目指针：不碰 pak 数据包、不碰哈希数组、文件大小不变
- 换刀**三层齐换**：模型（外观）+ 主图（拔刀/待机/攻击/手模）+ 检视（按 F），4~6 个条目指针
- 换肤世界模型+第一人称同时生效

## 图形界面（原型）

不想敲命令的话有个控制台，皮肤、贴图、刀型都能点着看：

```powershell
python gui/serve.py            # 零依赖，自动打开 http://127.0.0.1:8765
python gui/setup_vrf.py        # 可选但强烈建议：装缩略图引擎（约 53MB），皮肤网格才有真图
python gui/app.py              # 桌面版，需先 pip install pyside6-essentials
```

- **皮肤页**：33 把武器 × 1100+ kit。左选枪 → 中间网格看检视图（游戏里库存那张）→ 右侧看图案本体原图，选入口皮肤一键换
- **刀型页**：19 把原生刀，标明主图槽/检视槽类型，换刀自动重放皮肤补丁
- 界面层不碰二进制：所有写操作仍由 `scripts/` 执行，每次操作后自动审计

分层是刻意的：`gui/service.py` 不认识 Qt/浏览器，套一层 HTTP 就能换 Electron / Tauri / WPF 当外壳。详见 [gui/README.md](gui/README.md)。

## 快速上手

需要 Python 3.8+（推荐安装 `blake3` 包以启用全窗口校验）。

```powershell
# 换刀
python scripts/knife_mod.py --init              # 首次使用：自动探测游戏路径 + 建原始备份
python scripts/knife_mod.py --list              # 列出 19 种可用刀型
python scripts/knife_mod.py --knife karambit    # 换成爪子刀（仅换刀，会抹掉换肤补丁）
python scripts/skin_mod.py --patches            # 查看补丁清单（每次 --swap/--glove 自动记录）
python scripts/skin_mod.py --rebuild karambit   # 换刀 + 自动重放全部换肤补丁（推荐，一条命令）
python scripts/knife_mod.py --revert            # 还原默认刀

# 换肤（首次使用共用 knife_mod --init 建的备份）
python scripts/skin_mod.py --weapons                                  # 列出可换肤武器 (36)
python scripts/skin_mod.py --list ak47                                # 列出 AK47 可用皮肤（含 [legacy]/[composite] 标记）
python scripts/skin_mod.py --family doppler                           # 按名字查同族皮肤（多普勒 / 宝石系 / 渐变 / 手套）
python scripts/skin_mod.py --swap ak47 cu_ak47_mastery cu_ak_island_floral   # 精英之作 → 野荷（官方级）
python scripts/skin_mod.py --swap awp awp_tempered awp_queens_gambit --stack # 叠加，保留已有补丁

# 手套（同家族）
python scripts/skin_mod.py --gloves                                   # 72 个皮肤按 7 家族分组
python scripts/skin_mod.py --glove sporty_hunter sporty_purple --stack # 大型猎物 → 潘多拉之盒

# 跨武器试探：把刀的宝石系材质挂到枪上
python scripts/skin_mod.py --swap mp9 mp9_nexus am_sapphire_marbleized --force --stack

# 没有皮肤时的降级方案（图案平铺）
python scripts/skin_mod.py --skin ak47 gs_ak47_bloodsport --tex        # AK47 换血竞（必须带 --tex）

python scripts/knife_mod.py --audit             # 审计当前状态
```

`--init` 通过注册表 + `libraryfolders.vdf` 自动定位 Steam 库；探测失败时手动指定：

```powershell
python scripts/knife_mod.py --init --csgo "D:\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo"
```

## 换刀的三层槽位（为什么有时"拔刀还是匕首动作"）

换刀不是换模型就完事。第一人称的全部行为由三个互相独立的槽位决定：

| 层 | 条目 | 管什么 | 不换的症状 |
|---|---|---|---|
| 模型槽 | `vmdl_c:.../knife_default_t\|ct` | 外观几何 | 看不见目标刀 |
| **主图槽** | `viewmodel_knife.vnmgraph+default_t\|ct` | **idle / 拔刀 / 攻击 / 手模姿势** | **拔刀动作和手臂还是匕首的** |
| 检视槽 | `viewmodel_inspects.vnmgraph+knife_default_t\|ct` | 按 F 的检视 | 播默认刀的检视 |

主图槽必须直接改：顶层 `viewmodel` 按 `m_variationID` 选子图，而 variationID 来自物品数据，重指向改不了它，所以永远命中 `+default_ct` 那个装着匕首状态机的变体。

- 16 把中小刀型：主图槽填同名变体 `viewmodel_knife.vnmgraph+<刀名>`，检视槽填 `viewmodel_inspects.vnmgraph+knife_<刀名>`（共 6 条）
- **karambit / butterfly / talon**：主图槽填独立完整图 `viewmodel_knife_<刀名>`，**检视槽留空**（共 4 条）。完整图自带整套检视状态机（`INSPECT_LOOP` + `OUTRO` 收尾），自己接管检视；交给检视变体接管就只剩"播一次"，会**少一个收尾动作**（爪子刀实测）
- 检视槽**绝不能**塞完整图：4.9KB 的槽装 8.3KB 状态机，会进 `INSPECT_LOOP` 且收不到 `INSPECTCANCEL`，表现为"播完不停、连续重复触发"。`--force-inspect` 就是这个错误配置
- 检视段数由官方资源决定：butterfly 3 段、talon 2 段、**karambit 只有 1 段**（不是改丢了）
- `--no-inspect`：显式留空检视槽（完整图型已是默认，一般不用写）；`--no-main`：只换模型与检视，用于排查完整图端口契约不兼容（视角模型消失/T-pose）

### 换刀后记得补肤：`--rebuild`

换刀是从原始备份**整体重建**文件，会把所有换肤补丁抹掉。每成功应用一条 `--swap`/`--glove` 会自动记进 `patches.json`（同一槽位覆盖、不重复），所以换刀用一条命令就够：

```powershell
python scripts/skin_mod.py --patches            # 先看清单
python scripts/skin_mod.py --rebuild karambit   # 换刀 + 逐条重放 + 审计
```

清单是个人库存配置，已加入 `.gitignore`；跨 `--revert` 保留，Steam 还原后直接 `--rebuild` 即可恢复全部状态。

## 两种换肤流程怎么选

| 情况 | 命令 | 效果 |
|---|---|---|
| **真拥有**该武器上的任意皮肤 | `--swap <武器> <拥有的kit> <想显示的kit>` | **官方级**：蒙版分色、磨损、污渍、法线、paintseed 全保留；只改 1~2 个树条目 |
| 没有皮肤 | `--skin <武器> <kit> --tex` | 图案平铺全枪，无蒙版分色，质感仍是默认涂装 |
| 想把刀的材质（多普勒/宝石系/渐变大理石）挂到枪上 | `--swap ... --force` | 图案按**枪的 UV** 重新展开，已验证能出效果，但不保证是原皮肤的构图 |
| 想让 composite 入口挂 legacy 材质（或反向） | `--swap ... --force` | 结构上合法，但**结果不稳定**，同一组合有成功也有失败样本，只能逐例试 |

三条硬规则：

- **入口是"你拥有的皮肤"，不是武器**：一套皮肤占一个可显示槽位，同一槽位换第二款是覆盖而不是并列
- **入口永远是 `vcompmat` 那一条**（`items_game` 的 `composite_material_path` 指向它）。目标文档内部用绝对路径引自己的 vmat 与贴图，所以跨形态时只改 1 条
- **图标不变**：背包/检视 UI 是预烘焙的 panorama png，材质换了图标不会换

## 风险须知（必读）

- **修改后的文件不要带入 VAC 官方对局**，进官方局前先 `--revert`（1 秒）。离线/社区服随意
- Steam「验证完整性」会把 `pak01_dir.vpk` 还原成官方原版，重跑 `--knife` / `--swap` 即可恢复，`.bak_v6` 备份不受影响
- 引擎哈希校验可以保持自洽 ≠ VAC 一定不检测。VAC 逻辑不公开，封禁延迟执行，无法经验性证伪
- 本工具只做本地渲染层替换，库存/稀有度/磨损值等服务端数据不受影响

## 为什么不能用自制/外置 VPK？

我们做过完整的三轮挂载实验并逆向了 `filesystem_stdio.dll`，结论：**任何无 Valve 签名的 VPK 都无法在 CS2 加载**，与格式正确与否无关：

| 尝试 | 结果 | 根因 |
|---|---|---|
| 自建 VPK（合法树结构） | 静默无效 | 签名链不过，引擎静默丢弃 |
| 命名 `pak99.vpk` | 启动 fatal | `pak##` 未注册守卫直接拦截 |
| 改名绕过守卫 | 静默无效 | 仍过不了签名链 |

### 创意工坊模型同样不可用

实测扫描 12 张订阅创意工坊地图的全部 6505 个模型：**0 个武器模型**。工坊只收录地图，地图里全是环境资产（烘焙网格、门窗、道具、装饰）——第一人称武器由客户端从官方 pak01 加载，地图作者不需要也不会内置武器模型。所以"从创意工坊提取刀模型"这条路在素材层面就不存在。

签名链要求：内嵌公钥逐字节等于 Valve 钉扎公钥 + RSA-SHA256 验证签名 payload——伪造需要 Valve 私钥，密码学不可满足。GitHub/Gitee 上的"编译好 VPK mod"同样过不了这条链。

所以唯一可行路线就是本工具的做法：**在已签名的 `pak01_dir.vpk` 内部做树条目指针重指向**。完整逆向细节见 [references/vpk-technique.md](references/vpk-technique.md)。

## 目录结构

```
├── README.md                     # 本文件
├── SKILL.md                      # AI Agent 技能入口（ Trae/Claude 等 skill 规范）
├── cs2-knife-skin-mod.zip        # 分发包（由 scripts/pack_release.py 按固定清单生成，勿手工改）
├── scripts/
│   ├── knife_mod.py              # 换刀主工具（切换/审计/回滚/init）
│   ├── skin_mod.py               # 换肤工具（整材质换肤 / 贴图模式 / 手套 / 同族查询）
│   ├── diagnose_skin.py          # 皮肤资产完整度诊断（FULL / BROKEN 评级）
│   ├── batch_random.py           # 批量随机换装（只从满铺贴图池挑选）
│   ├── pack_release.py           # 生成/校验分发包（--check 逐字节比对源码）
│   └── scan_workshop.py          # 创意工坊资产侦察（扫描订阅地图 VPK 模型清单）
├── gui/
│   ├── serve.py                  # 本地 Web 界面服务端（标准库，零依赖）
│   ├── app.py                    # PySide6 桌面版界面
│   ├── service.py                # 纯 Python 服务层（界面与 CLI 之间的唯一桥梁）
│   ├── thumbs.py                 # 缩略图：VRF 导出 vtex_c → PNG + 缓存
│   ├── setup_vrf.py              # 下载/解压 Source2Viewer-CLI
│   └── web/index.html            # Web 界面
└── references/
    └── vpk-technique.md          # VPK 格式、引擎校验机制、换肤形态规则、踩坑记录与逆向结论
```

## License

[MIT](LICENSE)。本项目不分发任何游戏资产，所有脚本仅在运行时读取用户本地的 CS2 安装。Counter-Strike 2 及其资产归 Valve Corporation 所有，本项目与 Valve 无关。

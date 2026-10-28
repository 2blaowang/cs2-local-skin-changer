# CS2 本地视觉替换工具（换刀 + 换肤 + 换手套）

四个功能，同一套 VPK 树条目重指向技术：

1. **换刀**：把默认刀（T/CT 双阵营）本地替换为任意 19 种原生刀型（蝴蝶刀、爪子刀、M9 刺刀等，原色外观）
2. **换肤（整材质）**：真拥有任意一款皮肤时，把它整份换成另一款——引擎照常跑完整合成管线（蒙版裁剪/磨损/污渍/法线/paintseed），**官方级效果，只改 1~2 个条目**
3. **换手套**：72 个手套皮肤按 7 个家族分组，同家族内互换
4. **跨武器试探**（`--force`）：把刀的材质挂到枪上，比如 MP9 中枢 → 多普勒 / 蓝宝石 / 黑珍珠

纯本地视觉修改，无网络行为，不分发任何游戏资产。

- 一条命令切换 / 一键回滚 / 全量审计自检
- 只重写 VPK 目录树条目指针：不碰 pak 数据包、不碰哈希数组、文件大小不变
- 换刀含检视动画切换（含 CT 方正反握修复），换肤世界模型+第一人称同时生效

## 快速上手

需要 Python 3.8+（推荐安装 `blake3` 包以启用全窗口校验）。

```powershell
# 换刀
python scripts/knife_mod.py --init              # 首次使用：自动探测游戏路径 + 建原始备份
python scripts/knife_mod.py --list              # 列出 19 种可用刀型
python scripts/knife_mod.py --knife karambit    # 换成爪子刀（自动审计）
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
└── references/
    └── vpk-technique.md          # VPK 格式、引擎校验机制、换肤形态规则、踩坑记录与逆向结论
```

## License

[MIT](LICENSE)。本项目不分发任何游戏资产，所有脚本仅在运行时读取用户本地的 CS2 安装。Counter-Strike 2 及其资产归 Valve Corporation 所有，本项目与 Valve 无关。

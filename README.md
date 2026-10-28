# CS2 本地视觉替换工具（换刀 + 换肤）

两个功能，同一套 VPK 树条目重指向技术：

1. **换刀**：把默认刀（T/CT 双阵营）本地替换为任意 19 种原生刀型（蝴蝶刀、爪子刀、M9 刺刀等，原色外观）
2. **换肤**：把 36 种武器的默认涂装本地替换为任意原生皮肤（paint kit 贴图级重指向，图案平铺效果）

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
python scripts/skin_mod.py --weapons                       # 列出可换肤武器 (36)
python scripts/skin_mod.py --list ak47                     # 列出 AK47 可用皮肤
python scripts/skin_mod.py --skin ak47 gs_ak47_bloodsport --tex   # AK47 换血竞（必须带 --tex）

python scripts/knife_mod.py --audit             # 审计当前状态
```

`--init` 通过注册表 + `libraryfolders.vdf` 自动定位 Steam 库；探测失败时手动指定：

```powershell
python scripts/knife_mod.py --init --csgo "D:\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo"
```

## 风险须知（必读）

- **修改后的文件不要带入 VAC 官方对局**，进官方局前先 `--revert`（1 秒）。离线/社区服随意
- Steam「验证完整性」会把 `pak01_dir.vpk` 还原成官方原版，重跑 `--knife` 即可恢复，`.bak_v6` 备份不受影响
- 引擎哈希校验可以保持自洽 ≠ VAC 一定不检测。VAC 逻辑不公开，封禁延迟执行，无法经验性证伪
- 本工具只做本地渲染层替换：换肤图案为平铺效果（无官方蒙版分色），磨损质感保持默认涂装；库存/稀有度等服务端数据不受影响

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
├── scripts/
│   ├── knife_mod.py              # 换刀主工具（切换/审计/回滚/init）
│   ├── skin_mod.py               # 换肤工具（paint kit 贴图重指向，36 武器 × 原生皮肤）
│   └── scan_workshop.py          # 创意工坊资产侦察（扫描订阅地图 VPK 模型清单）
└── references/
    └── vpk-technique.md          # VPK 格式、引擎校验机制、踩坑记录与逆向结论
```

## License

[MIT](LICENSE)。本项目不分发任何游戏资产，所有脚本仅在运行时读取用户本地的 CS2 安装。Counter-Strike 2 及其资产归 Valve Corporation 所有，本项目与 Valve 无关。

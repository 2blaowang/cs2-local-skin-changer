# CS2 默认刀本地替换工具

把 CS2 的默认刀（T/CT 双阵营）本地替换为任意 19 种原生刀型（蝴蝶刀、爪子刀、M9 刺刀等，原色外观）。纯本地视觉修改，无网络行为，不分发任何游戏资产。

- 一条命令切换 / 一键回滚 / 全量审计自检
- 只重写 VPK 目录树里的 4 个指针条目：不碰 pak 数据包、不碰哈希数组、文件大小不变
- 检视动画一并切换（含 CT 方正反握修复），进游戏即生效

## 快速上手

需要 Python 3.8+（推荐安装 `blake3` 包以启用全窗口校验）。

```powershell
python scripts/knife_mod.py --init              # 首次使用：自动探测游戏路径 + 建原始备份
python scripts/knife_mod.py --list              # 列出 19 种可用刀型
python scripts/knife_mod.py --knife karambit    # 换成爪子刀（自动审计）
python scripts/knife_mod.py --knife butterfly   # 换成蝴蝶刀
python scripts/knife_mod.py --revert            # 还原默认刀
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
- 本工具只改模型与检视动画（原色）。皮肤涂装属于服务端物品系统，本地文件无法修改

## 为什么不能用自制/外置 VPK？

我们做过完整的三轮挂载实验并逆向了 `filesystem_stdio.dll`，结论：**任何无 Valve 签名的 VPK 都无法在 CS2 加载**，与格式正确与否无关：

| 尝试 | 结果 | 根因 |
|---|---|---|
| 自建 VPK（合法树结构） | 静默无效 | 签名链不过，引擎静默丢弃 |
| 命名 `pak99.vpk` | 启动 fatal | `pak##` 未注册守卫直接拦截 |
| 改名绕过守卫 | 静默无效 | 仍过不了签名链 |

签名链要求：内嵌公钥逐字节等于 Valve 钉扎公钥 + RSA-SHA256 验证签名 payload——伪造需要 Valve 私钥，密码学不可满足。GitHub/Gitee 上的"编译好 VPK mod"同样过不了这条链。

所以唯一可行路线就是本工具的做法：**在已签名的 `pak01_dir.vpk` 内部做树条目指针重指向**。完整逆向细节见 [references/vpk-technique.md](references/vpk-technique.md)。

## 目录结构

```
├── README.md                     # 本文件
├── SKILL.md                      # AI Agent 技能入口（ Trae/Claude 等 skill 规范）
├── scripts/
│   └── knife_mod.py              # 主工具（切换/审计/回滚/init）
└── references/
    └── vpk-technique.md          # VPK 格式、引擎校验机制、踩坑记录与逆向结论
```

## License

[MIT](LICENSE)。本项目不分发任何游戏资产，所有脚本仅在运行时读取用户本地的 CS2 安装。Counter-Strike 2 及其资产归 Valve Corporation 所有，本项目与 Valve 无关。

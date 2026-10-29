# 图形界面（原型）

给 `scripts/` 下的 VPK 补丁工具套一层控制台。**界面不碰二进制**，所有写盘操作
仍然由已经验证过的 CLI 逻辑执行，每次操作后自动跑审计。

## 目录

```
gui/
├── service.py       纯 Python 服务层（无 GUI 依赖）—— 换前端时唯一需要复用的东西
├── thumbs.py        缩略图：VRF 导出 vtex_c → PNG + 缓存
├── serve.py         本地 Web 界面服务端（标准库 http.server，零依赖）
├── web/index.html   Web 界面（单文件，原生 JS，无构建步骤）
├── app.py           PySide6 桌面版界面
├── setup_vrf.py     一键下载/解压 Source2Viewer-CLI
└── run_gui.bat      桌面版双击启动
```

两个前端共用同一个 `service.py`，所以不是二选一的重写，而是同一份逻辑的两个壳：

```
web/index.html ──┐
                 ├── service.py ── scripts/knife_mod.py + skin_mod.py
app.py (Qt) ─────┘      （唯一写盘者，逻辑零改动）
```

`service.py` 不认识 Qt 也不认识浏览器，把它套 HTTP 就能换 Electron / Tauri / WPF
当外壳，业务逻辑一行不用改。

## 运行

```bash
# ① Web 版：零依赖，装不了框架也能跑
python gui/serve.py                # 自动打开 http://127.0.0.1:8765

# ② 桌面版：原生窗口
python -m pip install pyside6-essentials
python gui/app.py                  # 或双击 gui/run_gui.bat

# 缩略图引擎（两版都需要，可选但强烈建议）
python gui/setup_vrf.py            # 约 53MB
```

前提：已跑过 `python scripts/knife_mod.py --init`（要有 `pak01_dir.vpk.bak_v6` 备份）。

## 界面

| 页 | 内容 |
|---|---|
| 皮肤 | 左选武器（33 把）→ 中间 kit 网格（带检视图缩略图，可搜索）→ 右侧图案本体大图 + 入口选择 + 一键换肤 |
| 刀型 | 19 把原生刀，标主图槽/检视槽类型，换刀自动按补丁清单重放 |
| 底栏 | 实时操作日志 + 补丁清单（点条目可移除） |

## 缩略图怎么来

- **网格小图** = 游戏里库存那张成品图（`panorama/images/econ/default_generated/*`），
  按武器整批导出，一次进程调用出几十到上百张（AK-47 的 61 款约 2.7s）
- **右侧大图** = kit 的图案本体（`paints/**/xxx_tga_xxxx`），选中时才导出，
  单张 1~5MB，原分辨率显示
- 缓存落在 `.cache/thumbs/`，目录结构与 VPK 内一致，导出过的永不重复导出
- 没有 VRF 时自动降级为占位色块，界面仍可用

## 关键实现点（踩过的坑）

- **一次进程导一整套，不要逐张调**：VRF 启动开销约 1s，逐张调用等于白扔时间；
  `-f <前缀>` 批量导出后按路径映射回 kit
- **导出文件名 = VPK 路径 + `.png`**，所以缓存路径可以完全由 vtex 路径推出，
  不需要额外索引文件
- **中文名有三种脏数据**：空、`PaintKit_xxx`（值是另一个键）、`#Token`，
  必须清洗后回落到内置常用表，否则界面上会出现 `PaintKit_cu_bizon_citizen`
- **检视图路径不能拼**：M4A4 在 panorama 里叫 `m4a1`，拼 `weapon_m4a4` 会 0 命中；
  必须按"最长 UI 名前缀"从树里反解（`service._icon_index()`），且**绝不整目录兜底**
  —— `default_generated` 有 6000+ 张几百 MB，误触发就是几分钟白等
- **默认选中要挑"能当入口"的 kit**：composite-only 的 kit 没有材质条目，
  一进页面落在它上面会让人以为工具坏了

## 已知限制

- 网格图是 light 尺寸的检视图，不是真 3D 预览；3D 要复刻 Source2 合成管线
  （baseColor × mask1 × mask2 × 磨损），不在原型范围
- composite 类 kit 的图案本体是**合成输入**（psd 元素层），直接看会显得"缺色"，
  真实效果要引擎把 mask/ao 也算进去
- **库存读取（"我拥有哪些皮肤"）还没接**：入口下拉目前是全量候选。
  下一步接 `steamcommunity.com/inventory/<steamid>/730/2`（要求库存公开），
  用 `market_hash_name` 的中文名反查 kit —— `service._name()` 已有映射能力；
  注意该接口不含多普勒阶段号，要精确 paintindex 得走 inspect link
- 未做打包（PyInstaller）

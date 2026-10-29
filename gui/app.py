"""CS2本地换肤器 · 图形化控制台

界面只负责展示与输入; 一切写盘操作都走 service.py -> scripts/ 里
已验证的 CLI 逻辑, 每个动作结束后自动审计。

启动: python gui/app.py      (或双击 gui/run_gui.bat)
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    from PySide6.QtCore import QSize, Qt, QThread, Signal
    from PySide6.QtGui import QColor, QIcon, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
        QListWidget, QListWidgetItem, QListView, QMainWindow, QMessageBox,
        QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QTabWidget,
        QVBoxLayout, QWidget,
    )
except ImportError:
    # 最常见的坑: pip 装进了 A 解释器, 运行时用 B 解释器, 报的是一行看不懂的 traceback。
    # 这里直接说清楚"是谁缺、该往哪装"。
    print("[缺少依赖] 当前解释器没有 PySide6:\n    " + sys.executable)
    print("\n装到同一个解释器里:")
    print('    "' + sys.executable + '" -m pip install '
          "-i https://mirrors.aliyun.com/pypi/simple/ pyside6-essentials pillow")
    print("\n或者双击 gui/setup_env.bat 建本地 .venv（推荐，不污染全局）。")
    print("只想先用网页版：双击 gui/run_web.bat（零依赖，不需要 PySide6）。")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import service  # noqa: E402
import thumbs  # noqa: E402

QSS = """
* { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; }
QMainWindow, QWidget { background: #16181d; color: #d8dbe2; }
QTabWidget::pane { border: 1px solid #2a2e37; border-radius: 6px; }
QTabBar::tab { background: #1c1f26; color: #8f97a6; padding: 7px 18px; border: 0; }
QTabBar::tab:selected { color: #ffffff; background: #262b34; }
QListWidget { background: #1a1d23; border: 1px solid #262b34; border-radius: 6px; outline: 0; }
QListWidget::item { border-radius: 5px; padding: 6px 8px; margin: 2px 4px; color: #c9cedb; }
QListWidget::item:selected { background: #2f6ee0; color: #ffffff; }
QListWidget::item:hover:!selected { background: #232830; }
QLabel#title { font-size: 15px; font-weight: 600; color: #ffffff; }
QLabel#sub { color: #7f8798; font-size: 11px; }
QLabel#tag { color: #9fb0c8; background: #222833; border-radius: 4px; padding: 2px 7px; font-size: 11px; }
QLabel#warn { color: #f0b429; font-size: 11px; }
QPushButton { background: #262b34; border: 1px solid #333a46; color: #d8dbe2;
              padding: 7px 14px; border-radius: 5px; }
QPushButton:hover { background: #2f3540; }
QPushButton:disabled { color: #5b6270; background: #1e222a; }
QPushButton#primary { background: #2f6ee0; border: 1px solid #3f7ceb; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: #3b7cef; }
QPushButton#primary:disabled { background: #26354f; color: #6d7a91; border-color: #2b3a54; }
QComboBox { background: #1a1d23; border: 1px solid #333a46; border-radius: 5px; padding: 6px 8px; }
QComboBox QAbstractItemView { background: #1a1d23; selection-background-color: #2f6ee0; }
QPlainTextEdit { background: #0f1115; border: 1px solid #262b34; border-radius: 6px;
                 color: #9aa3b2; font-family: Consolas, "Cascadia Mono", monospace; font-size: 11px; }
QCheckBox { color: #9aa3b2; font-size: 11px; }
QSplitter::handle { background: #20242c; width: 3px; }
QScrollBar:vertical { background: #16181d; width: 10px; }
QScrollBar::handle:vertical { background: #333a46; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


class Job(QThread):
    """把一个阻塞调用丢到后台线程, 结果通过信号回主线程"""
    done = Signal(object)

    def __init__(self, fn, *args):
        super().__init__()
        self._fn, self._args = fn, args

    def run(self):
        try:
            self.done.emit(self._fn(*self._args))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.done.emit((False, f"{type(e).__name__}: {e}"))


def badge(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("tag")
    lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
    return lbl


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CS2本地换肤器")
        self.resize(1180, 780)
        self._jobs: list[Job] = []
        self._weapon = None
        self._kit = None
        self._icon_ticket = 0
        self._paint_ticket = 0

        self._build_ui()
        self._boot()

    # ------------------------------------------------------------ UI 骨架
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(8)

        # 顶栏
        bar = QHBoxLayout()
        self.lbl_path = QLabel("…")
        self.lbl_path.setObjectName("sub")
        self.lbl_state = QLabel("")
        self.lbl_state.setObjectName("tag")
        btn_audit = QPushButton("审计")
        btn_audit.clicked.connect(self.on_audit)
        btn_revert = QPushButton("还原原版")
        btn_revert.clicked.connect(self.on_revert)
        bar.addWidget(QLabel("游戏目录"))
        bar.addWidget(self.lbl_path, 1)
        bar.addWidget(self.lbl_state)
        bar.addWidget(btn_audit)
        bar.addWidget(btn_revert)
        lay.addLayout(bar)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_skins(), "皮肤")
        self.tabs.addTab(self._tab_knives(), "刀型")
        self.tabs.addTab(self._tab_patches(), "补丁与日志")
        lay.addWidget(self.tabs, 1)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(118)
        lay.addWidget(self.log_box)

    def _tab_skins(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 8, 8, 8)

        self.wp_list = QListWidget()
        self.wp_list.setFixedWidth(196)
        self.wp_list.currentItemChanged.connect(self.on_weapon)

        self.kit_list = QListWidget()
        self.kit_list.setViewMode(QListView.IconMode)
        self.kit_list.setResizeMode(QListView.Adjust)
        self.kit_list.setMovement(QListView.Static)
        self.kit_list.setIconSize(QSize(104, 104))
        self.kit_list.setGridSize(QSize(126, 152))
        self.kit_list.setUniformItemSizes(True)
        self.kit_list.setWordWrap(True)
        self.kit_list.currentItemChanged.connect(self.on_kit)

        split = QSplitter()
        split.addWidget(self.wp_list)
        split.addWidget(self.kit_list)
        split.addWidget(self._skin_detail())
        split.setSizes([196, 620, 330])
        split.setStretchFactor(1, 1)
        h.addWidget(split)
        return w

    def _skin_detail(self) -> QWidget:
        box = QWidget()
        box.setMinimumWidth(320)
        box.setMaximumWidth(420)
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 0, 0, 0)
        v.setSpacing(8)

        self.preview = QLabel("选择一款皮肤")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(190)
        self.preview.setStyleSheet(
            "background:#171b21; border:1px solid #262b34; border-radius:8px; color:#5b6270;")
        v.addWidget(self.preview)

        self.k_title = QLabel("—")
        self.k_title.setObjectName("title")
        v.addWidget(self.k_title)
        self.k_sub = QLabel("")
        self.k_sub.setObjectName("sub")
        v.addWidget(self.k_sub)

        row = QHBoxLayout()
        self.k_form = badge("")
        self.k_style = badge("")
        self.k_size = badge("")
        row.addWidget(self.k_form)
        row.addWidget(self.k_style)
        row.addWidget(self.k_size)
        row.addStretch(1)
        v.addLayout(row)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#262b34;")
        v.addWidget(line)

        v.addWidget(QLabel("我拥有的入口皮肤（服务端要下发它的 paintindex）"))
        self.owned = QComboBox()
        v.addWidget(self.owned)

        self.force = QCheckBox("允许跨形态 / 跨武器（结果不保证）")
        v.addWidget(self.force)

        self.btn_apply = QPushButton("应用换肤")
        self.btn_apply.setObjectName("primary")
        self.btn_apply.clicked.connect(self.on_apply_skin)
        v.addWidget(self.btn_apply)

        self.k_hint = QLabel("")
        self.k_hint.setObjectName("warn")
        self.k_hint.setWordWrap(True)
        v.addWidget(self.k_hint)
        v.addStretch(1)
        return box

    def _tab_knives(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 8, 8, 8)
        self.knife_list = QListWidget()
        self.knife_list.currentItemChanged.connect(self.on_knife_sel)
        h.addWidget(self.knife_list, 1)

        right = QWidget()
        right.setMaximumWidth(330)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.addWidget(QLabel("换成这把刀"))
        self.kn_desc = QLabel("选一把刀")
        self.kn_desc.setObjectName("sub")
        self.kn_desc.setWordWrap(True)
        rv.addWidget(self.kn_desc)
        self.btn_knife = QPushButton("应用刀型")
        self.btn_knife.setObjectName("primary")
        self.btn_knife.setEnabled(False)
        self.btn_knife.clicked.connect(self.on_apply_knife)
        rv.addWidget(self.btn_knife)
        tip = QLabel("换刀会从原始备份整体重建文件，皮肤补丁会被抹掉；\n"
                     "本操作会自动按补丁清单逐条重放，无需手工补。")
        tip.setObjectName("warn")
        tip.setWordWrap(True)
        rv.addWidget(tip)
        rv.addStretch(1)
        h.addWidget(right)
        return w

    def _tab_patches(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        row = QHBoxLayout()
        b1 = QPushButton("刷新清单")
        b1.clicked.connect(self.refresh_patches)
        b2 = QPushButton("移除选中项")
        b2.clicked.connect(self.on_remove_patch)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch(1)
        v.addLayout(row)
        self.patch_box = QPlainTextEdit()
        self.patch_box.setReadOnly(True)
        v.addWidget(self.patch_box, 1)
        return w

    # ------------------------------------------------------------ 启动
    def _boot(self):
        try:
            st = service.bootstrap()
        except service.ServiceError as e:
            QMessageBox.critical(self, "初始化失败", str(e))
            raise SystemExit(1)
        self.lbl_path.setText(st["csgo"])
        self._reflect_state(st)
        self.fill_weapons()
        self.fill_knives()
        self.refresh_patches()
        if not st["backup"]:
            QMessageBox.warning(self, "缺少原始备份",
                                "未找到 pak01_dir.vpk.bak_v6。\n"
                                "请先跑：python scripts/knife_mod.py --init")
        if not thumbs.vrf_exe():
            self.log("未找到 Source2Viewer-CLI, 缩略图将显示占位图。安装方法见 gui/README.md")
        else:
            self.log(f"缩略图引擎就绪: {thumbs.vrf_exe()}")

    def _reflect_state(self, st: dict | None = None):
        st = st or service.state()
        bits = [f"{st['entries']} 条目"]
        if not st["backup"]:
            bits.append("无备份")
        elif st["steam_updated"]:
            bits.append("⚠ 文件大小与备份不符（Steam 更新过？）")
        else:
            bits.append("已打补丁" if st["patched"] else "原版未修改")
        self.lbl_state.setText(" · ".join(bits))

    # ------------------------------------------------------------ 皮肤页
    def fill_weapons(self):
        self.wp_list.blockSignals(True)
        self.wp_list.clear()
        for w in service.weapons():
            it = QListWidgetItem(f"{w['id']}    {w['kits']}")
            it.setData(Qt.UserRole, w["id"])
            self.wp_list.addItem(it)
        self.wp_list.blockSignals(False)
        if self.wp_list.count():
            self.wp_list.setCurrentRow(0)

    def on_weapon(self, cur, _prev):
        if not cur:
            return
        w = cur.data(Qt.UserRole)
        self._weapon = w
        self._kit = None
        kits = service.kits(w)
        self.kit_list.blockSignals(True)
        self.kit_list.clear()
        for k in kits:
            it = QListWidgetItem(self._kit_text(k))
            it.setData(Qt.UserRole, k)
            it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            ph = thumbs.placeholder(k["cn"] or k["kit"])
            if ph:
                it.setIcon(QIcon(ph))
            self.kit_list.addItem(it)
        self.kit_list.blockSignals(False)
        self.log(f"{w}: {len(kits)} 款皮肤")
        # 默认落到第一款"能当入口"的皮肤上 (composite-only 的 kit 没有材质条目,
        # 一进来停在它上面会让人以为工具坏了)
        if self.kit_list.count():
            pick = next((i for i in range(self.kit_list.count())
                         if self.kit_list.item(i).data(Qt.UserRole)["entry"]), 0)
            self.kit_list.setCurrentRow(pick)
        self._attach_pending_icons(w)

    @staticmethod
    def _kit_text(k: dict) -> str:
        name = k["cn"] or k["kit"]
        return f"{name}\n{'composite' if k['form'] == 'composite' else 'legacy'}"

    def _attach_pending_icons(self, weapon: str):
        """先用缓存里的图, 缺的整批导一次 (一次进程调用出一整套, 不要逐张调)"""
        self._apply_cached_icons(weapon)
        if not thumbs.vrf_exe():
            return
        missing = [self.kit_list.item(i).data(Qt.UserRole)["kit"]
                   for i in range(self.kit_list.count())
                   if not _cached_icon(weapon, self.kit_list.item(i).data(Qt.UserRole)["kit"])]
        if not missing:
            return
        self._icon_ticket += 1
        ticket = self._icon_ticket
        self.log(f"{weapon}: 导出 {len(missing)} 张检视图…")
        job = Job(thumbs.ensure_icons, service.icon_prefixes(weapon), _dir_vpk())

        def done(_res):
            if ticket != self._icon_ticket or weapon != self._weapon:
                return
            n = self._apply_cached_icons(weapon)
            self.log(f"{weapon}: 检视图就绪 ({n} 张)")

        job.done.connect(done)
        self._spawn(job)

    def _apply_cached_icons(self, weapon: str) -> int:
        n = 0
        for i in range(self.kit_list.count()):
            it = self.kit_list.item(i)
            k = it.data(Qt.UserRole)
            f = _cached_icon(weapon, k["kit"])
            if f:
                it.setIcon(QIcon(f))
                n += 1
        return n

    def on_kit(self, cur, _prev):
        if not cur:
            return
        k = cur.data(Qt.UserRole)
        self._kit = k
        d = service.kit_detail(k["kit"])
        self.k_title.setText(k["cn"] or k["kit"])
        self.k_sub.setText(k["kit"])
        self.k_form.setText(d.get("form", "?"))
        self.k_style.setText(f"style {d.get('style', '?')}")
        self.k_size.setText(f"{d.get('material_size', 0) // 1024} KB")
        self._fill_owned(k)
        self.k_hint.setText("")
        self.preview.setPixmap(QPixmap())
        self.preview.setText("加载贴图中…")
        self._load_paint(k)

    def _fill_owned(self, k: dict):
        """入口候选: 同武器里有材质条目的 kit, 同形态优先, 当前项排除"""
        self.owned.blockSignals(True)
        self.owned.clear()
        cands = [x for x in service.kits(self._weapon) if x["entry"] and x["kit"] != k["kit"]]
        cands.sort(key=lambda x: (x["form"] != k["form"], x["cn"] or x["kit"]))
        for x in cands:
            tag = "同形态" if x["form"] == k["form"] else x["form"]
            self.owned.addItem(f"{x['cn'] or x['kit']}  [{tag}]  {x['kit']}", x["kit"])
        self.owned.blockSignals(False)
        if not cands:
            self.k_hint.setText("这把武器没有可作为入口的皮肤：你需要至少拥有一款它的皮肤。")
            self.btn_apply.setEnabled(False)
        else:
            self.btn_apply.setEnabled(k["entry"])
            if not k["entry"]:
                self.k_hint.setText("当前皮肤没有材质资源条目，不能作为显示目标。")

    def _load_paint(self, k: dict):
        tex = service.paint_tex(k["kit"])
        if not tex:
            self.preview.setText("该皮肤没有独立图案贴图\n(使用共享底图)")
            return
        f = thumbs.png_path(tex)
        if os.path.exists(f):
            self._show_pixmap(f)
            return
        if not thumbs.vrf_exe():
            self.preview.setText("缺 Source2Viewer-CLI\n无法导出贴图")
            return
        self._paint_ticket += 1
        ticket = self._paint_ticket
        job = Job(thumbs.ensure_texture, tex, _dir_vpk())

        def done(res):
            if ticket != self._paint_ticket:
                return
            ok = res[0] if isinstance(res, tuple) else bool(res)
            if ok and os.path.exists(f):
                self._show_pixmap(f)
                self.log(f"贴图就绪: {tex.split('/')[-1]}")
            else:
                self.preview.setText("贴图导出失败\n见日志")

        job.done.connect(done)
        self._spawn(job)

    def _show_pixmap(self, path: str):
        pm = QPixmap(path)
        if pm.isNull():
            self.preview.setText("图片读取失败")
            return
        box = self.preview.size()
        target = QSize(int(box.width() * 0.96), int(box.height() * 0.96))
        self.preview.setPixmap(pm.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def on_apply_skin(self):
        if not (self._kit and self.owned.currentData()):
            return
        owned, want = self.owned.currentData(), self._kit["kit"]
        force = self.force.isChecked()
        if not self._confirm(f"把 {owned} 显示为 {want}？"):
            return
        self.btn_apply.setEnabled(False)
        self.log(f"换肤: {self._weapon} {owned} -> {want}{' [force]' if force else ''}")
        job = Job(service.apply_swap, self._weapon, owned, want, force)

        def done(res):
            self.btn_apply.setEnabled(True)
            self._after_write(res, "换肤")

        job.done.connect(done)
        self._spawn(job)

    # ------------------------------------------------------------ 刀型页
    def fill_knives(self):
        self.knife_list.clear()
        for k in service.knives():
            it = QListWidgetItem(f"{k['name']}   ({k['id']})\n"
                                 f"    主图槽 {k['main']} · 检视槽 {k['inspect']}")
            it.setData(Qt.UserRole, k)
            self.knife_list.addItem(it)

    def on_knife_sel(self, cur, _prev):
        if not cur:
            return
        k = cur.data(Qt.UserRole)
        self.kn_desc.setText(f"{k['name']} / {k['id']}\n主图槽: {k['main']}\n检视槽: {k['inspect']}")
        self.btn_knife.setEnabled(True)
        self.btn_knife.setProperty("kid", k["id"])

    def on_apply_knife(self):
        kid = self.btn_knife.property("kid")
        if not kid:
            return
        if not self._confirm(f"把默认刀换成 {kid}？\n（会重放全部 {len(service.patches())} 条补丁）"):
            return
        self.btn_knife.setEnabled(False)
        self.log(f"换刀: {kid}")
        job = Job(service.apply_knife, kid)

        def done(res):
            self.btn_knife.setEnabled(True)
            self._after_write(res, "换刀")
            self.refresh_patches()
            self.fill_weapons()

        job.done.connect(done)
        self._spawn(job)

    # ------------------------------------------------------------ 补丁 / 审计
    def refresh_patches(self):
        try:
            self.patch_box.setPlainText(service.patch_text())
        except Exception as e:  # noqa: BLE001
            self.patch_box.setPlainText(str(e))

    def on_remove_patch(self):
        idx = self._selected_patch_index()
        if idx is None:
            return
        res = service.remove_patch(idx)
        self.log(res["log"])
        self.refresh_patches()

    def _selected_patch_index(self) -> int | None:
        txt = self.patch_box.textCursor().block().text().strip()
        head = txt.split(".", 1)[0].strip()
        return int(head) - 1 if head.isdigit() else None

    def on_audit(self):
        job = Job(service.audit)
        job.done.connect(lambda r: (self.log(r["log"]), self._reflect_state()))
        self._spawn(job)

    def on_revert(self):
        if not self._confirm("把所有补丁还原为官方原版？"):
            return
        job = Job(service.revert)
        job.done.connect(lambda r: (self._after_write(r, "还原"), self.fill_weapons(),
                                    self.refresh_patches()))
        self._spawn(job)

    # ------------------------------------------------------------ 通用
    def _after_write(self, res, what: str):
        if isinstance(res, dict) and res.get("log"):
            self.log(res["log"])
        ok = bool(res.get("ok")) if isinstance(res, dict) else bool(res)
        self.log(f"{what}{'成功' if ok else '失败'}")
        self._reflect_state()

    def _confirm(self, text: str) -> bool:
        return QMessageBox.question(self, "确认", text) == QMessageBox.Yes

    def log(self, text: str):
        for line in str(text).rstrip().splitlines():
            self.log_box.appendPlainText(line)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())

    def _spawn(self, job: Job):
        self._jobs = [j for j in self._jobs if j.isRunning()]
        self._jobs.append(job)
        job.start()


def _cached_icon(weapon: str, kit: str) -> str | None:
    """检视图按 UI 名反解 (M4A4→m4a1), 路径由 service 给, 这里只判断有没有"""
    rel = service.icon_rel(weapon, kit)
    if not rel:
        return None
    f = thumbs.png_path(rel)
    return f if os.path.exists(f) else None


def _dir_vpk() -> str:
    import knife_mod as km
    return km.DIR_PATH


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = Main()
    win.show()
    # --shot <路径>: 自检用。等首屏异步加载完再截窗口, 然后退出
    if "--shot" in sys.argv:
        from PySide6.QtCore import QTimer
        out = sys.argv[sys.argv.index("--shot") + 1]

        def grab():
            win.grab().save(out)
            print(f"[+] 已保存 {out}")
            app.quit()

        QTimer.singleShot(6000, grab)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

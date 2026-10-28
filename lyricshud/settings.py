import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRectF, QEvent, QAbstractAnimation, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QPen, QFontMetrics, QGuiApplication
from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QSizeGrip,
    QButtonGroup,
    QLabel,
    QSpinBox,
    QComboBox,
    QLineEdit,
    QFileDialog,
    QListWidgetItem,
    QStackedWidget,
    QScrollArea,
    QGraphicsOpacityEffect,
)

from lyricshud.assets import AUDIO_FILTER, IMG_FILTER
from lyricshud.clock import CLOCK_MODES
from lyricshud.credit import CreditBadge
from lyricshud.defaults import DEFAULTS, POS_KEYS, POS_LABELS
from lyricshud.dialogs import PicCropDialog, TextAreaDialog
from lyricshud.fonts import FontCombo, FontNet, cover_thumb, dark_titlebar, list_font_files
from lyricshud.hotkeys import HOTKEY_ACTIONS, KeyCapture
from lyricshud.panel import Panel
from lyricshud.paths import APP_DIR, APP_VERSION, CACHE_DIR, FONT_DIR
from lyricshud.preview import Preview
from lyricshud.theme import apply_qss
from lyricshud.themes import (
    ADAPTIVE_MODES,
    CARD_SIZE_ITEMS,
    CARD_STYLES,
    DRIFT_ITEMS,
    ENTER_ITEMS,
    EXIT_ITEMS,
    IDLE_ITEMS,
    LYRIC_FILL_ITEMS,
    PRESETS,
    THEMES,
    THEME_HINTS,
    THEME_LABELS,
)
from lyricshud.titlebar import TitleBar
from lyricshud.utils import OPTIMIZE_ITEMS, clamp, clear_lyrics_cache, mix, open_path, with_alpha
from lyricshud.widgets import MENU_STYLES, MENU_STYLE_ITEMS, NavList, PAGE_ICONS, PageLay
from lyricshud.winutil import list_profiles, profile_path


class SettingsDialog(Panel):
    PAGES = (
        "Themes",
        "Colors",
        "Card",
        "Typography",
        "Lyrics",
        "Animations",
        "Overlay",
        "Widgets",
        "Menu",
        "Player",
        "Config",
        "About",
    )

    def __init__(self, ctl, page=0):
        super().__init__(ctl)
        self.pos_buttons = {}
        self.reset_armed = False
        self.setWindowTitle("Lyrics HUD")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, self.cfg["bar_mode"] != "native")
        self.resize(820, 680)
        self.setMinimumSize(700, 500)
        apply_qss(self, self.state.pal_target, self.ctl.theme.family)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.outer = outer
        self.titlebar = TitleBar(self)
        self.titlebar.setVisible(self.cfg["bar_mode"] == "custom")
        self.bar_pos_applied = "top"
        outer.addWidget(self.titlebar)
        root = QHBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        outer.addLayout(root, 1)

        style = self.cfg["menu_style"] if self.cfg["menu_style"] in MENU_STYLES else "standard"
        self.mstyle = style
        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(MENU_STYLES[style])
        self.side_w = side
        side.installEventFilter(self)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 10)
        sl.setSpacing(0)
        if style != "minimal":
            sl.addWidget(CreditBadge(self, True))
        self.nav = NavList(self.state, style)
        self.nav.setObjectName("nav")
        self.nav.setCursor(Qt.CursorShape.PointingHandCursor)
        for name in self.PAGES:
            icon = PAGE_ICONS.get(name, "•")
            item = QListWidgetItem(icon if style == "minimal" else icon + "  " + name)
            item.setToolTip(name)
            if style == "minimal":
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.nav.addItem(item)
        if style == "modern":
            sl.addStretch(1)
        else:
            sl.addWidget(self.nav, 1)
        self.np = QWidget()
        self.np.setObjectName("npcard")
        npl = QHBoxLayout(self.np)
        npl.setContentsMargins(8, 8, 8, 8)
        self.np_cover = QLabel()
        self.np_cover.setFixedSize(38, 38)
        npl.addWidget(self.np_cover)
        npt = QVBoxLayout()
        npt.setSpacing(1)
        self.np_title = QLabel()
        self.np_title.setObjectName("nptitle")
        self.np_artist = QLabel()
        self.np_artist.setObjectName("npartist")
        npt.addStretch(1)
        npt.addWidget(self.np_title)
        npt.addWidget(self.np_artist)
        npt.addStretch(1)
        npl.addLayout(npt, 1)
        npw = QHBoxLayout()
        npw.setContentsMargins(10, 0, 10, 0)
        npw.addWidget(self.np)
        sl.addLayout(npw)
        if style == "minimal":
            self.np.hide()
        root.addWidget(side)

        main = QWidget()
        main.setObjectName("main")
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        if style == "modern":
            ml.addWidget(self.nav)
        self.header = QLabel("Themes")
        self.header.setObjectName("title")
        ml.addWidget(self.header)
        self.preview = Preview(ctl)
        pw = QHBoxLayout()
        pw.setContentsMargins(24, 2, 24, 4)
        pw.addWidget(self.preview)
        ml.addLayout(pw)
        self.stack = QStackedWidget()
        ml.addWidget(self.stack, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(24, 8, 24, 14)
        close = QPushButton("Done")
        close.setObjectName("primary")
        close.clicked.connect(self.close)
        foot.addStretch(1)
        foot.addWidget(close)
        self.grip = QSizeGrip(self)
        self.grip.setVisible(self.cfg["bar_mode"] != "native")
        foot.addWidget(self.grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        ml.addLayout(foot)
        root.addWidget(main, 1)

        self.build_themes()
        self.build_colors()
        self.build_card()
        self.build_typography()
        self.build_lyrics()
        self.build_animations()
        self.build_overlay()
        self.build_widgets()
        self.build_menu_page()
        self.build_player()
        self.build_config()
        self.build_about()
        self.nav.currentRowChanged.connect(self.on_nav)
        self.nav.setCurrentRow(clamp(int(page), 0, len(self.PAGES) - 1))
        self.state.track_changed.connect(self.np_update)
        self.state.track_changed.connect(self.song_off_update)
        self.state.offset_changed.connect(self.song_off_update)
        self.state.palette_changed.connect(self.on_palette)
        self.np_update()
        self.sync_manual()
        self.place_bar()

    def eventFilter(self, obj, ev):
        if (
            obj is self.side_w
            and self.cfg["bar_mode"] == "hidden"
            and ev.type() == QEvent.Type.MouseButtonPress
            and ev.button() == Qt.MouseButton.LeftButton
        ):
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemMove()
            return True
        return super().eventFilter(obj, ev)

    def place_bar(self):
        pos = self.cfg["bar_pos"]
        if pos != self.bar_pos_applied:
            self.outer.removeWidget(self.titlebar)
            self.outer.insertWidget(0 if pos == "top" else self.outer.count(), self.titlebar)
            self.bar_pos_applied = pos
        self.titlebar.sync()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        pal = self.state.pal_target
        p.setPen(QPen(with_alpha(mix(pal.text, pal.accent, 0.5), 110), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()

    def on_nav(self, i):
        i = max(0, i)
        self.stack.setCurrentIndex(i)
        self.header.setText(self.PAGES[i])
        self.titlebar.set_page(self.PAGES[i])
        self.preview.setVisible(self.PAGES[i] not in ("Config", "About", "Menu"))
        self.animate_in(self.stack.currentWidget())

    def animate_in(self, w):
        if not self.cfg["menu_anim"] or not self.isVisible():
            return
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        a = QPropertyAnimation(eff, b"opacity", self)
        a.setDuration(360)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.finished.connect(lambda: w.setGraphicsEffect(None))
        a.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def on_palette(self):
        apply_qss(self, self.state.pal_target, self.ctl.theme.family)
        self.place_bar()
        for s in self.switches:
            s.update()
        self.np_update()
        dark_titlebar(self, self.state.pal_target)

    def np_update(self):
        st = self.state
        self.np_cover.setPixmap(cover_thumb(st, 46))
        fm = QFontMetrics(self.np_title.font())
        self.np_title.setText(fm.elidedText(st.title if st.active else "Nothing playing", Qt.TextElideMode.ElideRight, 110))
        self.np_artist.setText(fm.elidedText(st.artist if st.active else "", Qt.TextElideMode.ElideRight, 110))

    def new_page(self):
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 0, 24, 16)
        lay.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)
        self.stack.addWidget(scroll)
        return PageLay(self, lay)

    def sync_manual(self):
        for w in self.manual:
            w.setEnabled(not self.cfg["adaptive"])

    def reopen(self):
        page = self.nav.currentRow()
        self.close()
        QTimer.singleShot(0, lambda: self.ctl.open_settings(page))

    def apply_many(self, values):
        for k, v in values.items():
            self.cfg[k] = list(v) if isinstance(v, list) else v
        self.ctl.refresh()
        self.reopen()

    def apply_theme(self, name):
        values = THEMES.get(name)
        if values is None:
            self.set_val("theme", name)
            return
        self.apply_many(dict(values, theme=name))

    def theme_grid(self):
        box = QWidget()
        gl = QGridLayout(box)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        group = QButtonGroup(box)
        group.setExclusive(True)
        for n, (label, val) in enumerate(THEME_LABELS):
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setFixedHeight(54)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(self.cfg["theme"] == val)
            b.clicked.connect(lambda _=False, v=val: self.apply_theme(v))
            group.addButton(b)
            gl.addWidget(b, n // 3, n % 3)
        return box

    def preset_grid(self):
        box = QWidget()
        gl = QGridLayout(box)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        for n, (name, a, s, t) in enumerate(PRESETS):
            b = QPushButton(name)
            b.setFixedSize(112, 40)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            fg = "#000" if QColor(a).lightness() > 150 else "#fff"
            b.setStyleSheet(
                f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {a},stop:1 {s});color:{fg};"
                f"border:1px solid rgba(255,255,255,50);border-radius:9px;font-weight:700;font-size:11px;padding:0;}}"
                "QPushButton:hover{border:2px solid #fff;}"
            )
            b.clicked.connect(
                lambda _=False, a=a, s=s, t=t: self.apply_many({"accent": a, "secondary": s, "text": t, "adaptive": False})
            )
            gl.addWidget(b, n // 4, n % 4)
        return box

    def build_themes(self):
        lay = self.new_page()
        self.sec(lay, "Theme")
        lay.addWidget(self.theme_grid())
        hint = QLabel(THEME_HINTS.get(self.cfg["theme"], ""))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        hint.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(hint)
        self.sec(lay, "Display")
        self.row(
            lay,
            "Display mode",
            self.segmented("mode", (("Player", "hud"), ("Floating lyrics", "holo"), ("Both", "both"))),
            "Player card, fullscreen floating lyrics, or the compact card plus overlay",
        )
        lay.addStretch(1)

    def build_colors(self):
        lay = self.new_page()
        self.sec(lay, "Album art")
        self.row(
            lay,
            "Match album art colors",
            self.switch("adaptive", self.sync_manual),
            "One switch that makes the card, menus, settings, clock and lyrics all use the colors of the current cover",
        )
        self.row(
            lay,
            "Color style",
            self.combo("adaptive_mode", ADAPTIVE_MODES),
            "How the colors taken from the cover are reshaped",
        )
        self.sec(lay, "Presets")
        lay.addWidget(self.preset_grid())
        self.sec(lay, "Custom colors")
        self.row(lay, "Accent", self.color("accent"), "Used when album art colors are off")
        self.row(lay, "Secondary", self.color("secondary"))
        self.row(lay, "Text", self.color("text"))
        self.row(lay, "Custom background", self.switch("custom_bg"), "Replaces the generated dark background of the card")
        self.row(lay, "Background color", self.color("bg_color"))
        lay.addStretch(1)

    def build_card(self):
        lay = self.new_page()
        self.sec(lay, "Size")
        size = QComboBox()
        size.setFixedWidth(200)
        for label, val in CARD_SIZE_ITEMS:
            size.addItem(label, val)
        size.setCurrentIndex(max(0, size.findData(self.cfg["card_size"])))
        size.currentIndexChanged.connect(lambda _: self.ctl.set_card_size(size.currentData()))
        self.row(lay, "Card size", size, "Drag the bottom right corner for any size in between")
        self.row(lay, "HUD scale", self.slider("hud_scale", 60, 180, "%"), "Scales everything on the card. Ctrl and mouse wheel works too")
        self.row(lay, "Card text size", self.slider("ui_font", 80, 140, "%"))
        self.sec(lay, "Glass")
        self.row(lay, "Overall opacity", self.slider("opacity", 30, 100, "%"), "Fades the whole card, content included. Shift and mouse wheel works too")
        self.row(lay, "Glass opacity", self.slider("glass", 10, 100, "%"), "Lower values let more of the desktop show through the card")
        self.row(lay, "Background blur", self.switch("blur"), "Blurs whatever is behind the glass, needs Windows 10 or newer")
        self.row(lay, "Card style", self.combo("card_style", CARD_STYLES))
        self.row(lay, "Corner roundness", self.slider("card_radius", 8, 32, " px"))
        self.row(lay, "Cover tint", self.slider("backdrop", 0, 100, "%"), "How strongly the album art colors the card background")
        self.row(lay, "Frost strength", self.slider("frost", 0, 100, "%"), "Grain, top light and the gliding sheen of the Frosted glass style")
        self.sec(lay, "Borders and glow")
        self.row(lay, "Border strength", self.slider("border_alpha", 0, 200, "%"))
        self.row(lay, "Border thickness", self.slider("border_width", 1, 4, " px"))
        self.row(lay, "Animated border glow", self.slider("card_glow", 0, 100, "%"), "Light that travels around the card edge while music plays")
        self.row(lay, "Soft shadow", self.slider("card_shadow", 0, 100, "%"))
        self.sec(lay, "Background image")
        self.row(lay, "Image", self.file_box("bg_image", "Choose background image", IMG_FILTER), ".png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Image opacity", self.slider("bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Image blur", self.slider("bg_image_blur", 0, 100, "%"))
        self.sec(lay, "Content")
        self.row(lay, "Equalizer bars", self.switch("show_eq"), "Replaces the status dot with live bars")
        self.row(lay, "Show sync buttons", self.switch("show_sync"), "Quick offset buttons on the card for the current song. Turn off to remove them completely")
        self.row(lay, "Show sync offset value", self.switch("show_sync_val"), "The number between the sync buttons, like +100 ms")
        self.row(lay, "Show cover art", self.switch("show_cover"))
        self.row(lay, "Show album name", self.switch("show_album"))
        self.row(lay, "Show status line", self.switch("show_status"))
        lay.addStretch(1)

    def build_typography(self):
        lay = self.new_page()
        self.sec(lay, "Font")
        self.fnet = FontNet()
        self.fnet.index_ready.connect(self.on_index_ready)
        self.fnet.index_failed.connect(self.on_index_failed)
        self.fnet.downloaded.connect(self.on_downloaded)
        self.fnet.failed.connect(self.on_download_failed)
        self.font_combo = FontCombo()
        self.font_combo.setFixedWidth(200)
        self.fill_font_combo()
        self.font_combo.about_to_open.connect(self.fill_font_combo)
        self.font_combo.currentIndexChanged.connect(self.on_font_combo)
        self.row(lay, "Font", self.font_combo, f"Every font file inside {FONT_DIR} shows up here")
        self.font_query = QLineEdit()
        self.font_query.setPlaceholderText("Search Google Fonts")
        self.font_query.setFixedWidth(120)
        self.font_query.returnPressed.connect(self.search_fonts)
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.search_fonts)
        qbox = QWidget()
        ql = QHBoxLayout(qbox)
        ql.setContentsMargins(0, 0, 0, 0)
        ql.addWidget(self.font_query)
        ql.addWidget(search_btn)
        self.row(lay, "Download fonts", qbox, "Downloaded fonts are saved into the Font folder")
        self.result_combo = QComboBox()
        self.result_combo.setFixedWidth(200)
        self.dl_button = QPushButton("Download")
        self.dl_button.setEnabled(False)
        self.dl_button.clicked.connect(self.download_font)
        rbox = QWidget()
        rl = QHBoxLayout(rbox)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.result_combo)
        rl.addWidget(self.dl_button)
        self.row(lay, "Search results", rbox)
        self.dl_info = QLabel()
        self.dl_info.setObjectName("hint")
        self.dl_info.setWordWrap(True)
        lay.addWidget(self.dl_info)
        self.font_edit = QLineEdit(self.cfg["font_path"])
        self.font_edit.setReadOnly(True)
        self.font_edit.setPlaceholderText("Default (Segoe UI)")
        self.font_edit.setFixedWidth(170)
        browse = QPushButton("Browse")
        clear = QPushButton("Clear")
        folder = QPushButton("Open folder")
        browse.clicked.connect(self.pick_font)
        clear.clicked.connect(self.clear_font)
        folder.clicked.connect(self.open_font_folder)
        fbox = QWidget()
        fl = QHBoxLayout(fbox)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.font_edit)
        fl.addWidget(browse)
        fl.addWidget(clear)
        fl.addWidget(folder)
        self.font_info = QLabel()
        self.font_info.setObjectName("hint")
        self.row(lay, "Custom font file", fbox, ".ttf, .otf or .ttc")
        lay.addWidget(self.font_info)
        self.update_font_info()
        self.sec(lay, "Lyric text")
        self.row(lay, "Lyric size", self.slider("font_size", 14, 72, " px"))
        self.row(
            lay,
            "Lyric weight",
            self.combo("lyric_weight", [("Medium", 500), ("Semi-bold", 600), ("Bold", 700), ("Black", 900)]),
        )
        self.row(lay, "Letter spacing", self.slider("lyric_spacing", 0, 12, " px"))
        self.row(lay, "Line spacing", self.slider("lyric_gap", 80, 160, "%"), "Space between wrapped lines")
        self.row(
            lay,
            "Text case",
            self.combo("lyric_case", [("As written", "none"), ("UPPERCASE", "upper"), ("lowercase", "lower")]),
        )
        self.sec(lay, "Text image")
        self.row(lay, "Image over text", self.switch("text_image_on"), "The letters are filled with your image instead of a color")
        self.row(lay, "Image", self.file_box("text_image", "Choose text image", IMG_FILTER), "GIFs play inside the letters")
        adj = QPushButton("Adjust area")
        adj.clicked.connect(self.open_text_area)
        self.row(lay, "Image area", adj, "Pick which part of the image shows inside the letters")
        self.sec(lay, "Lyric style")
        self.row(
            lay,
            "Text fill",
            self.combo("lyric_fill", LYRIC_FILL_ITEMS),
            "Gradients fade across each line. Fixed color fills switch to the album art colors while Match album art colors is on",
        )
        self.row(lay, "Custom lyric color", self.color("lyric_color"), "Used by the Custom colors fill")
        self.row(lay, "Custom lyric color 2", self.color("lyric_color2"), "The line fades from the first color into this one")
        self.row(lay, "Glow", self.slider("glow", 0, 100, "%"))
        self.row(
            lay,
            "Glow color",
            self.combo("glow_color", [("Accent", "accent"), ("Secondary", "secondary"), ("Text", "text")]),
        )
        self.row(lay, "Lyric opacity", self.slider("lyric_opacity", 10, 100, "%"))
        self.row(lay, "Outline", self.slider("lyric_outline", 0, 6, " px"), "Dark edge that keeps text readable on bright backgrounds")
        self.row(lay, "Shadow", self.slider("lyric_shadow", 0, 100, "%"))
        lay.addStretch(1)

    def build_lyrics(self):
        lay = self.new_page()
        self.sec(lay, "Timing")
        self.row(
            lay,
            "Auto sync",
            self.switch("auto_sync"),
            "Picks the lyric version closest to the track length, follows playback speed and remembers your nudges for each song",
        )
        self.song_off = QLabel()
        song_reset = QPushButton("Reset")
        song_reset.clicked.connect(lambda: self.state.set_track_ms(0))
        song_box = QWidget()
        sbl = QHBoxLayout(song_box)
        sbl.setContentsMargins(0, 0, 0, 0)
        sbl.addWidget(self.song_off)
        sbl.addWidget(song_reset)
        self.row(lay, "This song's offset", song_box, "Saved per song and applied automatically. Nudge it from the tray menu while the song plays")
        self.song_off_update()
        self.row(lay, "Anticipation", self.slider("anticipation", 0, 600, " ms"), "Shows each line slightly before it is sung so the fade-in finishes right on the beat")
        snap_box = QWidget()
        snl = QHBoxLayout(snap_box)
        snl.setContentsMargins(0, 0, 0, 0)
        snap_cur = QPushButton("Current line starts now")
        snap_next = QPushButton("Next line starts now")
        snap_cur.clicked.connect(lambda: self.ctl.snap(0))
        snap_next.clicked.connect(lambda: self.ctl.snap(1))
        snl.addWidget(snap_cur)
        snl.addWidget(snap_next)
        self.row(lay, "Tap sync", snap_box, "Press when you hear a line begin to lock the lyrics to the song. The result is saved for this song")
        self.row(lay, "Global hotkeys", self.switch("hotkeys"), "Turns the keyboard shortcuts on or off. You can change each shortcut on the Player page")
        off = QSpinBox()
        off.setRange(-5000, 5000)
        off.setSingleStep(50)
        off.setSuffix(" ms")
        off.setFixedWidth(120)
        off.setValue(int(self.cfg["offset_ms"]))
        off.valueChanged.connect(lambda v: self.set_val("offset_ms", v, False))
        self.row(lay, "Sync offset", off, "Positive shows lyrics earlier, negative later")
        self.sec(lay, "Cache")
        self.cache_info = QLabel()
        self.cache_info.setObjectName("hint")
        clear_btn = QPushButton("Clear lyrics cache")
        clear_btn.clicked.connect(self.clear_cache)
        self.row(lay, "Lyrics cache", clear_btn, "Deletes every saved lyric file so lyrics are downloaded fresh")
        lay.addWidget(self.cache_info)
        self.cache_update()
        self.sec(lay, "Placement")
        items = [("Random", "random")] + [(POS_LABELS[k], k) for k in POS_KEYS]
        self.row(lay, "Position", self.combo("placement", items), "Random picks a new spot for every line")
        grid_host = QWidget()
        gl = QGridLayout(grid_host)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(6)
        layout_map = {"tl": (0, 0), "tr": (0, 2), "ml": (1, 0), "m": (1, 1), "mr": (1, 2), "bl": (2, 0), "br": (2, 2)}
        short = {"tl": "TL", "tr": "TR", "m": "MID", "ml": "ML", "mr": "MR", "bl": "BL", "br": "BR"}
        for k, (r, c) in layout_map.items():
            b = QPushButton(short[k])
            b.setObjectName("pos")
            b.setCheckable(True)
            b.setFixedSize(64, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(k in self.cfg["positions"])
            b.toggled.connect(lambda v, key=k: self.toggle_pos(key, v))
            gl.addWidget(b, r, c)
            self.pos_buttons[k] = b
        self.row(lay, "Random spots", grid_host, "Pick which screen positions random placement may use")
        lay.addStretch(1)

    def build_animations(self):
        lay = self.new_page()
        self.sec(lay, "Lyric animation")
        self.row(lay, "Line entrance", self.combo("enter_style", ENTER_ITEMS), "How each lyric line arrives")
        self.row(lay, "Line exit", self.combo("exit_style", EXIT_ITEMS), "How each lyric line leaves")
        self.row(lay, "Idle motion", self.combo("idle_anim", IDLE_ITEMS), "Gentle movement while a line is on screen")
        self.row(
            lay,
            "Lyric drift",
            self.combo("lyric_drift", DRIFT_ITEMS),
            "The line slowly moves up or down the whole time it is shown, then fades away when it is done",
        )
        self.row(lay, "Drift distance", self.slider("lyric_drift_px", 10, 150, " px"), "How far a line travels from start to end")
        self.row(lay, "Motion", self.slider("motion", 0, 200, "%"), "How far lines slide, drift and zoom. 0 is a plain fade")
        self.row(lay, "Fade time", self.slider("fade_ms", 150, 1200, " ms"))
        self.row(lay, "Line hold", self.slider("hold", 50, 200, "%"), "How long a line stays up before fading, relative to the estimate")
        self.row(
            lay,
            "Lyrics only while sung",
            self.switch("karaoke"),
            "Karaoke fill: the line lights up word by word as it is sung. Lines always fade away once they end",
        )
        self.row(lay, "Unsung brightness", self.slider("dim_level", 10, 80, "%"), "How bright the part of the line that has not been sung yet stays")
        self.sec(lay, "Effects")
        self.row(lay, "3D tilt", self.switch("tilt"), "Lines swing in with a perspective tilt toward the screen center")
        self.row(lay, "Scanlines", self.switch("scanlines"))
        self.row(lay, "Scanline strength", self.slider("scan_strength", 5, 100, "%"))
        self.row(lay, "Scanline spacing", self.slider("scan_gap", 2, 8, " px"))
        self.row(lay, "Glitch and chroma ghost", self.switch("glitch"))
        self.row(lay, "Glitch intensity", self.slider("glitch_amount", 20, 250, "%"))
        self.row(lay, "Chroma ghost strength", self.slider("ghost", 0, 200, "%"))
        self.row(lay, "Light flicker", self.slider("flicker", 0, 300, "%"))
        self.sec(lay, "Interface")
        self.row(lay, "Interface animations", self.switch("ui_anim"), "Hover effects, entrance animation and track change transitions")
        self.row(
            lay,
            "Animation rate",
            self.combo(
                "fps",
                [("24 fps", 24), ("30 fps", 30), ("45 fps", 45), ("60 fps", 60), ("90 fps", 90), ("120 fps", 120), ("144 fps", 144)],
            ),
            "Higher values look smoother and use more CPU and GPU",
        )
        self.row(
            lay,
            "Optimization",
            self.combo("optimize", OPTIMIZE_ITEMS),
            "Balanced caps animation at 45 fps. Performance caps it at 30 fps and turns off the animated menu glow",
        )
        lay.addStretch(1)

    def build_overlay(self):
        lay = self.new_page()
        self.sec(lay, "Layer")
        self.row(
            lay,
            "Lyrics layer",
            self.combo("layer", [("Above everything", "top"), ("Wallpaper (desktop)", "wall")]),
            "Wallpaper paints the lyrics into your desktop background, so windows and icons always stay on top of them",
        )
        self.row(lay, "Wallpaper dimming", self.slider("wall_dim", 0, 80, "%"), "Darkens the wallpaper layer so lyrics stay readable")
        self.row(
            lay,
            "Wallpaper blend",
            self.combo(
                "wall_blend",
                [("Normal", "normal"), ("Screen", "screen"), ("Overlay", "overlay"), ("Soft light", "soft"), ("Additive", "add")],
            ),
            "How the lyrics mix with the wallpaper colors",
        )
        self.sec(lay, "Screen")
        mon = QSpinBox()
        mon.setRange(1, max(1, len(QGuiApplication.screens())))
        mon.setValue(int(self.cfg["holo_screen"]) + 1)
        mon.setFixedWidth(100)
        mon.valueChanged.connect(lambda v: self.set_val("holo_screen", v - 1))
        self.row(lay, "Overlay monitor", mon)
        self.row(lay, "Overlay lyric size", self.slider("holo_scale", 50, 220, "%"))
        self.row(lay, "Line width", self.slider("holo_width", 25, 70, "%"), "Maximum width of a lyric line as a share of the screen")
        self.row(lay, "Always on top", self.switch("always_on_top"), "Keeps the player card and the clock above other windows")
        self.row(lay, "Hide in fullscreen apps", self.switch("autohide_fullscreen"), "Hides the card, clock and lyrics while a game or video is fullscreen and shows them again afterwards")
        self.row(lay, "Lyrics over card and widgets", self.switch("lyrics_over_ui"), "On lets lyrics appear on top of the card and the clock. Off moves them to another free spot")
        self.row(lay, "Distance from card", self.slider("card_gap", 0, 80, " px"), "When lyrics stay clear, they keep at least this much space from the card and widgets")
        self.sec(lay, "Toast")
        self.row(lay, "Now playing toast", self.switch("show_toast"), "Shows the title and artist at the top of the screen when a song starts")
        self.row(lay, "Toast duration", self.slider("toast_secs", 2, 12, " s"))
        lay.addStretch(1)

    def build_widgets(self):
        lay = self.new_page()
        self.sec(lay, "Welcome screen")
        self.row(lay, "Show on startup", self.switch("show_welcome"), "Greets you by name when the app starts")
        play = QPushButton("Preview")
        play.clicked.connect(lambda: self.ctl.welcome.play(False))
        self.row(lay, "Preview welcome", play, "The welcome card is docked to the player card and follows it")
        self.sec(lay, "Welcome profile")
        self.row(lay, "Profile picture", self.file_box("welcome_pic", "Choose profile picture", IMG_FILTER), "Shown in the circle. .png, .jpg, .webp or .gif")
        self.row(lay, "Picture size", self.slider("welcome_pic_size", 48, 140, " px"), "Makes the profile picture bigger or smaller. The welcome card grows with it")
        crop = QPushButton("Crop picture")
        crop.clicked.connect(self.open_pic_crop)
        self.row(lay, "Crop picture", crop, "Choose exactly which part of the picture is shown")
        self.row(lay, "Picture shape", self.combo("welcome_pic_shape", [("Circle", "circle"), ("Rounded square", "rounded")]))
        self.row(lay, "Animated ring", self.switch("welcome_ring"), "The spinning color ring around the picture")
        self.sec(lay, "Welcome wallpaper")
        self.row(
            lay,
            "Image",
            self.file_box("welcome_bg_image", "Choose welcome wallpaper", IMG_FILTER),
            "Shown behind the welcome card. .png, .jpg, .bmp, .webp or .gif. Empty uses the player card background image",
        )
        self.row(lay, "Wallpaper opacity", self.slider("welcome_bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Wallpaper blur", self.slider("welcome_bg_image_blur", 0, 100, "%"))
        self.sec(lay, "Welcome text")
        self.row(lay, "Name", self.text_box("welcome_name", "Uses your Windows name"), "Leave empty to use your Windows name")
        self.row(lay, "First start title", self.text_box("welcome_title", "WELCOME"))
        self.row(lay, "Returning title", self.text_box("welcome_title_back", "WELCOME BACK"))
        self.row(lay, "Subtitle", self.text_box("welcome_sub", "Automatic"), "Replaces the line under the name. Use {name} and {pc} to insert them")
        self.row(lay, "Show greeting", self.switch("welcome_greeting"), "Good morning, afternoon or evening")
        self.row(lay, "Show computer name", self.switch("welcome_pc"))
        self.row(lay, "Show date", self.switch("welcome_date"))
        self.row(lay, "Name size", self.slider("welcome_name_size", 24, 44, " px"))
        self.row(lay, "Duration", self.slider("welcome_duration", 3, 12, " s"))
        self.sec(lay, "Launch audio")
        self.row(lay, "Play on launch", self.switch("launch_audio_on"), "Plays your own sound every time the app starts")
        self.row(lay, "Audio file", self.file_box("launch_audio", "Choose launch audio", AUDIO_FILTER), ".mp3, .wav, .ogg, .flac, .m4a or .wma")
        self.row(lay, "Launch volume", self.slider("launch_audio_volume", 0, 100, "%"))
        test = QPushButton("Play")
        test.clicked.connect(lambda: self.ctl.play_launch(True))
        self.row(lay, "Test sound", test)
        self.sec(lay, "Live clock")
        self.row(lay, "Show clock", self.switch("show_clock"), "A draggable glass clock that follows your theme")
        self.row(lay, "Clock mode", self.combo("clock_mode", CLOCK_MODES), "Digital, Minimal, Stacked, Date focus or a round Analog face")
        self.row(lay, "24 hour time", self.switch("clock_24h"))
        self.row(lay, "Show seconds", self.switch("clock_seconds"))
        self.row(lay, "Show date", self.switch("clock_date"))
        self.row(lay, "Clock size", self.slider("clock_scale", 60, 200, "%"))
        self.row(lay, "Clock opacity", self.slider("clock_opacity", 30, 100, "%"))
        self.row(lay, "Clock background image", self.file_box("clock_bg_image", "Choose clock background", IMG_FILTER), "Separate from the player card background. .png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Clock image opacity", self.slider("clock_bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Clock image blur", self.slider("clock_bg_image_blur", 0, 100, "%"))
        self.row(lay, "Date format", self.combo("clock_date_fmt", [("Long", "long"), ("Short", "short"), ("Numeric", "numeric"), ("Weekday only", "weekday")]))
        self.row(lay, "Time color", self.combo("clock_color", [("Text", "text"), ("Accent", "accent"), ("Gradient", "gradient")]))
        self.row(lay, "Blinking colon", self.switch("clock_blink"), "Digital, Minimal, Stacked and Date focus")
        self.row(lay, "Time offset", self.slider("clock_tz", -12, 14, " h"), "Shows the time in another time zone, relative to this computer")
        self.row(lay, "Label", self.text_box("clock_label", "For example Tokyo"), "A small title above the time")
        self.row(lay, "Analog numbers", self.switch("clock_face_nums"))
        self.row(lay, "Analog tick marks", self.switch("clock_face_ticks"))
        self.row(lay, "Smooth second hand", self.switch("clock_smooth"))
        reset = QPushButton("Reset clock position")
        reset.clicked.connect(self.ctl.reset_clock)
        self.row(lay, "Clock position", reset)
        self.sec(lay, "System monitor")
        self.row(lay, "Show monitor", self.switch("monitor_on"), "Off by default. A draggable widget with CPU, memory, FPS, render time and the busiest programs")
        self.row(lay, "CPU usage", self.switch("monitor_cpu"))
        self.row(lay, "Memory usage", self.switch("monitor_ram"))
        self.row(lay, "Overlay FPS", self.switch("monitor_fps"))
        self.row(lay, "Render time", self.switch("monitor_render"))
        self.row(lay, "Top programs", self.switch("monitor_procs"), "Needs psutil, which installs on the next start")
        self.row(lay, "Monitor scale", self.slider("monitor_scale", 60, 180, "%"))
        self.row(lay, "Monitor opacity", self.slider("monitor_opacity", 30, 100, "%"))
        self.row(lay, "Refresh every", self.slider("monitor_interval", 500, 3000, " ms"))
        self.row(lay, "Monitor background image", self.file_box("monitor_bg_image", "Choose monitor background", IMG_FILTER), ".png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Monitor image opacity", self.slider("monitor_bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Monitor image blur", self.slider("monitor_bg_image_blur", 0, 100, "%"))
        mreset = QPushButton("Reset")
        mreset.clicked.connect(lambda: self.ctl.monitor.reset_pos())
        self.row(lay, "Monitor position", mreset)
        self.sec(lay, "Stats")
        self.row(lay, "Show stats", self.switch("stats_on"), "A draggable widget with how many songs were played and how long the app has been running. Turn it off here")
        self.row(lay, "Songs played", self.switch("stats_songs"))
        self.row(lay, "Songs counter", self.combo("stats_scope", [("This session", "session"), ("All time", "total")]), "Session counts since the app started. All time is saved between runs")
        self.row(lay, "App running time", self.switch("stats_uptime"), "How long the app has been running")
        self.row(lay, "Stats scale", self.slider("stats_scale", 60, 180, "%"))
        self.row(lay, "Stats opacity", self.slider("stats_opacity", 30, 100, "%"))
        self.row(lay, "Stats background image", self.file_box("stats_bg_image", "Choose stats background", IMG_FILTER), ".png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Stats image opacity", self.slider("stats_bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Stats image blur", self.slider("stats_bg_image_blur", 0, 100, "%"))
        sreset = QPushButton("Reset")
        sreset.clicked.connect(lambda: self.ctl.stats.reset_pos())
        self.row(lay, "Stats position", sreset)
        self.sec(lay, "Equalizer")
        self.row(lay, "Show equalizer", self.switch("eq_on"), "A draggable widget with animated bars that move with your music. Turn it off here")
        self.row(lay, "Equalizer style", self.combo("eq_style", [("Bars", "bars"), ("Wave", "wave")]))
        self.row(lay, "Equalizer color", self.combo("eq_color", [("Accent to secondary", "gradient"), ("Accent", "accent"), ("Text", "text")]))
        self.row(lay, "Equalizer bars", self.slider("eq_bars", 6, 40))
        self.row(lay, "Equalizer scale", self.slider("eq_scale", 60, 200, "%"))
        self.row(lay, "Equalizer opacity", self.slider("eq_opacity", 30, 100, "%"))
        self.row(lay, "Equalizer background image", self.file_box("eq_bg_image", "Choose equalizer background", IMG_FILTER), ".png, .jpg, .bmp, .webp or .gif")
        self.row(lay, "Equalizer image opacity", self.slider("eq_bg_image_opacity", 0, 100, "%"))
        self.row(lay, "Equalizer image blur", self.slider("eq_bg_image_blur", 0, 100, "%"))
        ereset = QPushButton("Reset")
        ereset.clicked.connect(lambda: self.ctl.equalizer.reset_pos())
        self.row(lay, "Equalizer position", ereset)
        lay.addStretch(1)

    def build_menu_page(self):
        lay = self.new_page()
        self.sec(lay, "Wallpaper")
        self.row(
            lay,
            "Image",
            self.file_box("menu_image", "Choose menu wallpaper", IMG_FILTER),
            "Shown behind this window, quick customize and the tray menu",
        )
        self.row(lay, "Wallpaper opacity", self.slider("menu_image_opacity", 0, 100, "%"))
        self.row(lay, "Wallpaper blur", self.slider("menu_blur", 0, 100, "%"))
        self.row(lay, "Wallpaper dimming", self.slider("menu_dim", 0, 100, "%"), "Darkens the wallpaper so text stays readable")
        self.sec(lay, "Menu style")
        mstyle = self.combo("menu_style", MENU_STYLE_ITEMS)
        mstyle.currentIndexChanged.connect(lambda _: self.reopen())
        self.row(
            lay,
            "Settings layout",
            mstyle,
            "Standard, compact, icons only, top tabs or fancy. Every tab has an icon. The window reopens to apply it",
        )
        self.sec(lay, "Orbital menu")
        self.row(lay, "Orbital menu size", self.slider("orbit_scale", 60, 160, "%"), "Quick circular menu: middle-click the card, use its hotkey (changeable on the Player page) or the tray menu")
        opener = QPushButton("Open orbital menu")
        opener.clicked.connect(lambda: self.ctl.open_orbital())
        self.row(lay, "Try it", opener)
        self.sec(lay, "Animation")
        self.row(
            lay,
            "Animated menus",
            self.switch("menu_anim"),
            "Fade-ins, page transitions, sliding switches, the gliding sidebar and the drifting glow",
        )
        self.sec(lay, "Title bar")
        mode = self.combo("bar_mode", [("Custom", "custom"), ("Windows", "native"), ("Hidden", "hidden")])
        mode.currentIndexChanged.connect(lambda _: self.reopen())
        self.row(lay, "Style", mode, "Custom is the themed bar. Windows uses the system title bar. Hidden removes it and lets you drag the window by the sidebar")
        self.row(lay, "Position", self.combo("bar_pos", [("Top", "top"), ("Bottom", "bottom")]))
        self.row(lay, "Alignment", self.combo("bar_align", [("Left", "left"), ("Center", "center")]))
        self.row(lay, "Window buttons", self.combo("bar_btn_pos", [("Right", "right"), ("Left", "left")]))
        self.row(lay, "Height", self.slider("bar_height", 36, 64, " px"))
        self.row(lay, "Show name", self.switch("bar_brand"))
        self.row(lay, "Show page", self.switch("bar_page"))
        self.sec(lay, "Equalizer")
        self.row(lay, "Equalizer waves", self.switch("bar_eq"), "Animated bars in the title bar that move with your music")
        self.row(lay, "Style", self.combo("bar_eq_style", [("Bars", "bars"), ("Wave", "wave")]))
        self.row(lay, "Color", self.combo("bar_eq_color", [("Accent to secondary", "gradient"), ("Accent", "accent"), ("Text", "text")]))
        self.row(lay, "Bars", self.slider("bar_eq_bars", 6, 40))
        lay.addStretch(1)

    def build_player(self):
        lay = self.new_page()
        self.sec(lay, "Controls")
        self.row(lay, "Show volume bar", self.switch("show_volume"), "Scroll over the card to change it too")
        self.row(lay, "Volume of playing app only", self.switch("app_volume"), "The volume bar changes only the app that plays the song. Uses system volume if that app is not found")
        self.sec(lay, "Window")
        self.row(
            lay,
            "Lock card in place",
            self.switch("click_through"),
            "The card can't be moved or resized, clicks pass through it everywhere except the controls. Unlock again from the tray menu",
        )
        reset = QPushButton("Reset card position")
        reset.clicked.connect(self.ctl.reset_hud)
        self.row(lay, "Card position", reset)
        self.sec(lay, "Startup")
        self.row(lay, "Launch at startup", self.switch("startup", self.ctl.apply_startup), "Starts Lyrics Screen automatically when you sign in")
        self.sec(lay, "Hotkeys")
        self.hk_buttons = {}
        for name, label, key in HOTKEY_ACTIONS:
            btn = KeyCapture(self.cfg[key], lambda t, k=key: any(self.cfg[o] == t for _, _, o in HOTKEY_ACTIONS if o != k))
            btn.changed.connect(lambda t, k=key: self.set_hotkey(k, t))
            self.hk_buttons[key] = btn
            self.row(lay, label, btn, "Click, then press the new keys. Needs Ctrl, Alt or Shift. Windows only")
        hreset = QPushButton("Reset hotkeys")
        hreset.clicked.connect(self.reset_hotkeys)
        self.row(lay, "Defaults", hreset, "Restores Ctrl+Alt+Shift with J, K, H, N, V and O. A combination that another program already uses will not work")
        lay.addStretch(1)

    def build_config(self):
        lay = self.new_page()
        self.cfg_info = QLabel()
        self.cfg_info.setObjectName("hint")
        self.cfg_info.setWordWrap(True)
        lay.addWidget(self.cfg_info)
        self.sec(lay, "Profiles")
        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Profile name")
        self.profile_name.setFixedWidth(170)
        save = QPushButton("Save")
        save.clicked.connect(self.save_profile)
        sbox = QWidget()
        sbl = QHBoxLayout(sbox)
        sbl.setContentsMargins(0, 0, 0, 0)
        sbl.addWidget(self.profile_name)
        sbl.addWidget(save)
        self.row(lay, "Save current settings", sbox, "Stores every look and lyric setting under a name")
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedWidth(170)
        load = QPushButton("Load")
        delete = QPushButton("Delete")
        load.clicked.connect(self.load_profile)
        delete.clicked.connect(self.delete_profile)
        lbox = QWidget()
        lbl = QHBoxLayout(lbox)
        lbl.setContentsMargins(0, 0, 0, 0)
        lbl.addWidget(self.profile_combo)
        lbl.addWidget(load)
        lbl.addWidget(delete)
        self.row(lay, "Saved profiles", lbox, "Window and clock positions are not part of a profile")
        self.fill_profiles()
        self.sec(lay, "Export")
        export = QPushButton("Export config")
        imp = QPushButton("Import config")
        folder = QPushButton("Open folder")
        export.clicked.connect(self.export_cfg)
        imp.clicked.connect(self.import_cfg)
        folder.clicked.connect(self.open_folder)
        bbox = QWidget()
        bbl = QHBoxLayout(bbox)
        bbl.setContentsMargins(0, 0, 0, 0)
        bbl.addWidget(export)
        bbl.addWidget(imp)
        bbl.addWidget(folder)
        self.row(lay, "Config file", bbox, "Export saves your settings with wallpapers, gifs, profile picture and fonts into one file to share or back up. Import loads it back. Launch audio is not included")
        self.sec(lay, "Reset")
        self.reset_btn = QPushButton("Reset all settings to default")
        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.disarm_reset)
        self.reset_btn.clicked.connect(self.arm_reset)
        self.row(lay, "Defaults", self.reset_btn, "Restores every setting. Window positions are kept")
        lay.addStretch(1)

    def build_about(self):
        lay = self.new_page()
        self.sec(lay, "How it works")
        for t in (
            "Reads the system media session (the Windows media session, or MPRIS on Linux), so Spotify, YouTube Music in a browser and other players work with no client ID.",
            "Synced lyrics come from LRCLIB and are cached on disk.",
            "Click the progress bar to seek. Scroll over the card for volume, hold Ctrl to scale the card or Shift to change its opacity. Right-click the card for the quick menu or middle-click it for the orbital menu.",
            "Browsers need hardware media control enabled, which is on by default in Chrome, Brave and Edge.",
        ):
            l = QLabel(t)
            l.setObjectName("hint")
            l.setWordWrap(True)
            l.setContentsMargins(0, 4, 0, 4)
            lay.addWidget(l)
        self.sec(lay, "Updates")
        self.row(lay, "Version", QLabel("v" + APP_VERSION))
        self.row(lay, "Automatic updates", self.switch("auto_update"), "Checks GitHub when the app starts, downloads the newest release and replaces this version")
        self.row(lay, "GitHub repository", self.text_box("update_repo", "owner/repo"), "The repository whose releases are used, for example owner/repo")
        upd = QPushButton("Check now")
        upd.clicked.connect(self.ctl.updater.check)
        self.row(lay, "Update", upd)
        self.upd_info = QLabel(self.ctl.updater.last)
        self.upd_info.setObjectName("hint")
        self.upd_info.setWordWrap(True)
        self.ctl.updater.status.connect(self.upd_info.setText)
        lay.addWidget(self.upd_info)
        self.sec(lay, "Credits")
        lay.addWidget(CreditBadge(self, False))
        lay.addStretch(1)

    def cache_update(self):
        files = list(CACHE_DIR.glob("*.json"))
        size = 0
        for f in files:
            try:
                size += f.stat().st_size
            except Exception:
                pass
        self.cache_info.setText(f"{len(files)} cached songs, {size / 1024:.1f} KB")

    def clear_cache(self):
        count, size = clear_lyrics_cache()
        self.cache_info.setText(f"Cleared {count} cached songs, freed {size / 1024:.1f} KB")
        if self.state.title:
            self.state.request_lyrics()

    def song_off_update(self):
        st = self.state
        self.song_off.setText(f"{st.track_ms():+d} ms" if st.active else "No song")

    def toggle_pos(self, key, on):
        cur = [k for k in POS_KEYS if k in self.cfg["positions"]]
        if on and key not in cur:
            cur.append(key)
        if not on and key in cur:
            if len(cur) <= 1:
                self.pos_buttons[key].blockSignals(True)
                self.pos_buttons[key].setChecked(True)
                self.pos_buttons[key].blockSignals(False)
                return
            cur.remove(key)
        self.set_val("positions", cur)

    def text_box(self, key, placeholder="", width=220):
        edit = QLineEdit(str(self.cfg[key]))
        edit.setPlaceholderText(placeholder)
        edit.setFixedWidth(width)

        def done():
            if edit.text() != str(self.cfg[key]):
                self.set_val(key, edit.text())

        edit.editingFinished.connect(done)
        return edit

    def file_box(self, key, title, filt):
        edit = QLineEdit(self.cfg[key])
        edit.setReadOnly(True)
        edit.setPlaceholderText("None")
        edit.setFixedWidth(170)
        browse = QPushButton("Browse")
        clear = QPushButton("Clear")
        browse.clicked.connect(lambda: self.pick_file(key, edit, title, filt))
        clear.clicked.connect(lambda: self.clear_file(key, edit))
        box = QWidget()
        bl = QHBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(edit)
        bl.addWidget(browse)
        bl.addWidget(clear)
        return box

    def pick_file(self, key, edit, title, filt):
        path, _ = QFileDialog.getOpenFileName(self, title, "", filt)
        if path:
            edit.setText(path)
            if key == "welcome_pic":
                self.cfg["welcome_pic_rect"] = [0.0, 0.0, 1.0, 1.0]
            self.set_val(key, path)

    def clear_file(self, key, edit):
        edit.setText("")
        if key == "welcome_pic":
            self.cfg["welcome_pic_rect"] = [0.0, 0.0, 1.0, 1.0]
        self.set_val(key, "")

    def fill_profiles(self):
        self.profile_combo.clear()
        for n in list_profiles():
            self.profile_combo.addItem(n, n)

    def save_profile(self):
        path = profile_path(self.profile_name.text())
        if path is None:
            self.cfg_info.setText("Type a profile name first")
            return
        try:
            self.cfg.write_to(path, False)
        except Exception as e:
            self.cfg_info.setText("Could not save: " + str(e))
            return
        self.cfg_info.setText("Saved profile " + path.stem)
        self.fill_profiles()

    def import_from(self, path):
        try:
            self.cfg.read_from(path)
        except Exception as e:
            self.cfg_info.setText("Could not load: " + str(e))
            return
        self.ctl.refresh()
        self.reopen()

    def load_profile(self):
        name = self.profile_combo.currentData()
        if name:
            self.import_from(profile_path(name))

    def delete_profile(self):
        name = self.profile_combo.currentData()
        if not name:
            return
        try:
            os.remove(str(profile_path(name)))
        except OSError as e:
            self.cfg_info.setText("Could not delete: " + str(e))
            return
        self.cfg_info.setText("Deleted profile " + name)
        self.fill_profiles()

    def export_cfg(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export settings", str(APP_DIR / "lyrics_hud_settings.json"), "JSON (*.json)")
        if not path:
            return
        try:
            self.cfg.write_to(path)
        except Exception as e:
            self.cfg_info.setText("Could not export: " + str(e))
            return
        self.cfg_info.setText("Exported to " + path)

    def import_cfg(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import settings", str(APP_DIR), "JSON (*.json)")
        if path:
            self.import_from(path)

    def open_folder(self):
        try:
            open_path(APP_DIR)
        except OSError as e:
            self.cfg_info.setText("Could not open the folder: " + str(e))

    def arm_reset(self):
        if self.reset_armed:
            self.on_reset()
            return
        self.reset_armed = True
        self.reset_btn.setText("Click again to confirm")
        self.reset_timer.start(3000)

    def disarm_reset(self):
        self.reset_armed = False
        self.reset_btn.setText("Reset all settings to default")

    def on_reset(self):
        self.cfg.reset()
        self.ctl.refresh()
        self.reopen()

    def update_font_info(self):
        th = self.ctl.theme
        if self.cfg["font_path"] and not th.font_ok:
            self.font_info.setText("Could not load this font file, using the default")
        elif self.cfg["font_path"]:
            self.font_info.setText(f"Loaded family: {th.family}")
        else:
            self.font_info.setText("Using Segoe UI")

    def set_hotkey(self, key, text):
        self.cfg[key] = text
        self.cfg.save()
        self.ctl.restart_hotkeys()

    def reset_hotkeys(self):
        for _, _, key in HOTKEY_ACTIONS:
            self.cfg[key] = DEFAULTS[key]
            self.hk_buttons[key].setText(DEFAULTS[key])
        self.cfg.save()
        self.ctl.restart_hotkeys()

    def open_pic_crop(self):
        if not self.cfg["welcome_pic"] or not os.path.isfile(self.cfg["welcome_pic"]):
            return
        PicCropDialog(self).exec()

    def open_text_area(self):
        if not self.cfg["text_image"] or not os.path.isfile(self.cfg["text_image"]):
            return
        dlg = TextAreaDialog(self)
        dlg.exec()

    def open_font_folder(self):
        try:
            FONT_DIR.mkdir(parents=True, exist_ok=True)
            open_path(FONT_DIR)
        except OSError as e:
            self.font_info.setText("Could not open the folder: " + str(e))

    def pick_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose font file", str(FONT_DIR), "Fonts (*.ttf *.otf *.ttc)")
        if path:
            self.cfg["font_path"] = path
            self.font_edit.setText(path)
            self.ctl.refresh()
            self.update_font_info()
            self.fill_font_combo()

    def clear_font(self):
        self.cfg["font_path"] = ""
        self.font_edit.setText("")
        self.ctl.refresh()
        self.update_font_info()
        self.fill_font_combo()

    def fill_font_combo(self):
        c = self.font_combo
        c.blockSignals(True)
        c.clear()
        c.addItem("Default (Segoe UI)", "")
        for p in list_font_files():
            c.addItem(p.stem, str(p))
        cur = self.cfg["font_path"]
        i = c.findData(cur)
        if cur and i < 0:
            c.addItem(Path(cur).name, cur)
            i = c.count() - 1
        c.setCurrentIndex(max(0, i))
        c.blockSignals(False)

    def on_font_combo(self, _):
        path = self.font_combo.currentData() or ""
        self.cfg["font_path"] = path
        self.font_edit.setText(path)
        self.ctl.refresh()
        self.update_font_info()

    def search_fonts(self):
        self.dl_info.setText("Searching...")
        self.fnet.load_index()

    def on_index_ready(self):
        q = self.font_query.text().strip().lower()
        found = [f for f in (FontNet.index or []) if q in f[0].lower()]
        found.sort(key=lambda f: (not f[0].lower().startswith(q), f[0].lower()))
        self.result_combo.clear()
        for name, cat, variants in found[:60]:
            self.result_combo.addItem(f"{name} ({cat})" if cat else name, (name, variants))
        self.dl_button.setEnabled(bool(found))
        if found:
            self.dl_info.setText(f"{len(found)} found" + (", showing the first 60" if len(found) > 60 else ""))
        else:
            self.dl_info.setText("No fonts found")

    def on_index_failed(self, msg):
        self.dl_info.setText("Could not reach Google Fonts: " + msg)

    def download_font(self):
        d = self.result_combo.currentData()
        if not d:
            return
        self.dl_info.setText(f"Downloading {d[0]}...")
        self.dl_button.setEnabled(False)
        self.fnet.download(d[0], d[1])

    def on_downloaded(self, path):
        self.dl_button.setEnabled(True)
        self.dl_info.setText("Saved to " + path)
        self.fill_font_combo()

    def on_download_failed(self, msg):
        self.dl_button.setEnabled(True)
        self.dl_info.setText("Download failed: " + msg)

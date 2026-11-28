"""Графический установщик. Рабочий поток сообщает события, Tk рисует их в главном."""
from __future__ import annotations

import copy
import math
import sys
import queue
import threading
import time
import tempfile
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from launcher_update import CHECK_INTERVAL_MS, announce_ready, download_and_launch, latest

PHASES = [
    ("scripts", "Реплики и сцены"), ("strings", "Органайзер и улики"),
    ("gk1", "Язык первой игры"), ("fonts", "Русские шрифты"),
    ("graphics", "Графика и звуки"),
]
BG, PANEL, TEXT, MUTED = "#101923", "#162330", "#eff4f5", "#a7b7c7"
GOLD, CYAN = "#e5be79", "#70d4d0"
ACTIVE_PANEL, ACTIVE_HEADER = "#172a36", "#203d49"
BUSY_BG, BUSY_TEXT, BUSY_EDGE, BUSY_RING = "#1b3f46", "#edf9f7", "#39646c", "#8de3d9"
DESCRIPTIONS = {
    "scripts": "Главы 1–5 и общая механика", "strings": "Улики, профили и меню",
    "gk1": "Немецкий → английский", "fonts": "Кириллица и размеры символов",
    "graphics": "Изображения, ролики и аудио",
}
DETAIL_NAMES = {
    "script_ger": "Реплики пяти глав", "script_ger_trial": "Вступление и общая механика",
    "strings_ger_main": "Улики, профили и меню", "strings_ger": "Общие подписи",
    "gk1_script_ger": "Реплики первой игры", "gk1_script_ger_trial": "Вступление первой игры",
    "font_data.unity3d": "Кириллица и размеры символов",
    "gk2_mapbg": "Фоны и карты", "gk2_mapobj": "Предметы на картах",
    "gk2_upcut": "Иллюстрации и крупные планы", "gk2_upcutlocal": "Надписи на иллюстрациях",
    "gk2_cutdata": "Данные сцен", "gk2_cutobj": "Объекты в сценах",
    "gk2_cutobjlocal": "Надписи в сценах", "gk2_bustup": "Портреты",
    "gk2_movie": "Ролики", "gk2_se": "Звуки и выкрики",
    "gk2_modelitem": "Модели улик", "gk2_modelitemlocal": "Надписи на моделях улик",
    "gk2_idcom": "Оформление диалогов", "gk2_idlocal": "Подписи диалогов",
    "gk2_logicchess": "Логические шахматы", "gk2_logickeyword": "Карточки логики",
    "gk2_logickeywordlocal": "Надписи на карточках логики", "gk2_openinglocal": "Заставки",
    "gk_common_ingameui": "Игровой интерфейс",
    "localization-assets-german(de)": "Изображения интерфейса",
    "localization-asset-tables-german(de)": "Привязки изображений интерфейса",
}


def detail_name(detail: str) -> str:
    direct = DETAIL_NAMES.get(detail)
    if direct:
        return direct
    stem = detail.removesuffix("_trial").replace("_classic", "").removesuffix("classic")
    name = DETAIL_NAMES.get(stem)
    if not name:
        return detail
    suffixes = []
    if "classic" in detail:
        suffixes.append("классика")
    if detail.endswith("_trial"):
        suffixes.append("вступление")
    return " · ".join([name, *suffixes])


class AnimatedBar(tk.Canvas):
    """Ease toward measured progress; moving stripes never change the count."""
    def __init__(self, master, **kwargs):
        kwargs.pop("style", None)
        kwargs.pop("maximum", None)
        super().__init__(master, height=12, bg="#293949", highlightthickness=0, **kwargs)
        self.target = self.value = 0.0
        self.mode = "determinate"
        self.running = False
        self.born = time.monotonic()
        self.drawn = None
        self.after(33, self.animate)

    def config(self, **kwargs):
        if "mode" in kwargs:
            self.mode = kwargs.pop("mode")
        if "value" in kwargs:
            self.target = max(0, min(100, float(kwargs.pop("value"))))
        if kwargs:
            super().config(**kwargs)

    configure = config

    def __setitem__(self, key, value):
        self.config(**{key: value})

    def start(self, interval=None):
        self.running = True

    def stop(self):
        self.running = False

    def animate(self):
        self.value += (self.target - self.value) * .13
        if abs(self.target - self.value) < .04:
            self.value = self.target
        width, height = self.winfo_width(), self.winfo_height()
        age = time.monotonic() - self.born
        if self.mode == "indeterminate" and self.running:
            span = width * .25
            left = (width - span) * (.5 - .5 * math.cos(age * 1.8))
            right = left + span
        else:
            left, right = 0, width * self.value / 100
        bounds = (width, height, round(left), round(right), self.running)
        if bounds == self.drawn:
            self.after(33, self.animate)
            return
        self.drawn = bounds
        self.delete("all")
        if right > left:
            self.create_rectangle(left, 0, right, height, fill=CYAN, outline="")
        self.after(33, self.animate)


class PhaseSection(tk.Frame):
    def __init__(self, master, title, description, toggle, reveal):
        super().__init__(master, bg=PANEL, highlightthickness=1, highlightbackground=PANEL)
        self.title = title
        self.description = description
        self.entries = {}
        self.count = 0
        self.all_records = False
        self.header = tk.Frame(self, bg=PANEL)
        self.header.pack(fill="x")
        self.header.columnconfigure(0, weight=1)
        self.button = tk.Button(self.header, anchor="w", bg=PANEL, fg=TEXT, width=1,
                                relief="flat", bd=0, padx=9, pady=3, cursor="hand2",
                                activebackground=ACTIVE_HEADER, activeforeground=TEXT,
                                highlightcolor=CYAN, highlightthickness=1,
                                font=("Segoe UI", 10), command=toggle)
        self.button.grid(row=0, column=0, sticky="nsew")
        self.button.bind("<Return>", lambda e: self.button.invoke() or "break")
        self.button.bind("<FocusIn>", lambda e: reveal())
        self.status = tk.Label(self.header, bg=PANEL, fg=MUTED, anchor="e",
                               padx=11, font=("Segoe UI", 9), cursor="hand2")
        self.status.grid(row=0, column=1, sticky="ns")
        self.status.bind("<ButtonRelease-1>", lambda e: toggle())
        self.details = tk.Frame(self, bg=ACTIVE_PANEL, padx=29, pady=5)
        controls = tk.Frame(self.details, bg=ACTIVE_PANEL)
        controls.pack(fill="x")
        self.bar = AnimatedBar(controls)
        self.bar.config(height=4)
        self.bar.pack(side="left", fill="x", expand=True, pady=(1, 4))
        self.records = tk.Label(self.details, bg=ACTIVE_PANEL, fg=MUTED, anchor="w",
                                justify="left", font=("Segoe UI", 9))
        self.records.pack(fill="x")
        self.more = tk.Button(controls, command=self.toggle_records, bg=ACTIVE_PANEL,
                               fg=CYAN, relief="flat", bd=0, cursor="hand2", padx=0, pady=2,
                               activebackground=ACTIVE_HEADER, activeforeground=TEXT,
                               font=("Segoe UI", 9))
        self.set_records()
        self.set_state("Ожидание")
        self.expand(False)

    def set_state(self, value, *, active=False, error=False):
        background = ACTIVE_HEADER if active else PANEL
        border = CYAN if active else GOLD if error else PANEL
        self.config(highlightbackground=border)
        self.header.config(bg=background)
        self.button.config(bg=background)
        color = GOLD if error else TEXT if active else CYAN if value == "Готово" else MUTED
        self.status.config(text=value, bg=background, fg=color)

    def expand(self, show):
        arrow = "▾" if show else "▸"
        self.button.config(text=f"{arrow}  {self.title}")
        if show:
            self.details.pack(fill="x")
        else:
            self.details.pack_forget()
            self.all_records = False
            self.set_records()

    def set_records(self):
        records = list(self.entries.items())
        if not self.all_records:
            records = records[-3:]
        self.records.config(text="\n".join(
            f"{'✓' if done else '•'}  {detail_name(name)}"
            for name, done in records
        ) if records else self.description)
        if len(self.entries) > 3:
            self.more.config(text="Свернуть список" if self.all_records else f"Все записи ({len(self.entries)})")
            self.more.pack(side="right", padx=(10, 0))
        else:
            self.more.pack_forget()

    def toggle_records(self):
        self.all_records = not self.all_records
        self.set_records()

    def record(self, name, count, streaming):
        if name:
            self.entries[name] = not streaming or count > self.count or self.entries.get(name, False)
            self.set_records()
        self.count = count

    def finish(self):
        self.entries = dict.fromkeys(self.entries, True)
        self.set_records()
        self.set_state("Готово")
        self.bar.stop()
        self.bar.config(mode="determinate", value=100)

    def reset(self):
        self.entries.clear()
        self.count = 0
        self.set_records()
        self.set_state("Ожидание")
        self.expand(False)
        self.bar.stop()
        self.bar.config(mode="determinate", value=0)
        self.bar.value = 0


class Installer:
    def __init__(self, args, runner):
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AAI2.RU.Installer")
        except (AttributeError, OSError):
            pass
        self.args, self.runner = args, runner
        self.events = queue.Queue()
        self.root = tk.Tk()
        self.root.title("AAI2 · Русская локализация")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "installer.ico"
        if icon.exists():
            self.root.iconbitmap(default=str(icon))
            self.root.iconbitmap(str(icon))
        width = min(1060, self.root.winfo_screenwidth() - 40)
        height = min(820, self.root.winfo_screenheight() - 100)
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(min(780, width), min(570, height))
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.temp = tempfile.TemporaryDirectory(prefix="aai2-loading-")
        self.busy = False
        self.ready = False
        self.preparing = True
        self.code = 0
        self.game = None
        self.audio = None
        self.music_volume = 35
        self.log = []
        self.log_window = self.log_text = None
        self.audio_status = None
        self.data_ok = False
        self.completed = set()
        self.active = None
        self.last_progress = None
        self.progress_description = ""
        self.graphics_detail = None
        self.checked_chapters = set()
        self.expanded_phases = set()
        self.reveal_job = None
        self.spinner_job = None
        self.spinner_key = None
        self.hero_image = self.background = None
        self.background_size = None
        self.scenes = []
        self.started = None
        self.release = None
        self.updating = False
        self.rollback = False
        self._build()
        self.root.report_callback_exception = self.report_ui_exception
        self.root.after(60, self.poll)
        self.root.after(150, self.tick)
        threading.Thread(target=self.prepare, daemon=True).start()
        if self.args.update_cache:
            self.root.after(0, self.check_updates)

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Load.Horizontal.TProgressbar", troughcolor="#293949",
                        background=CYAN, borderwidth=0, lightcolor=CYAN, darkcolor=CYAN)
        self.hero = tk.Canvas(self.root, height=212, bg="#203144", highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero_background = self.hero.create_image(0, 0, anchor="nw")
        self.hero.bind("<Configure>", self.draw_hero_background)
        self.hero.create_text(28, 21, text="ACE ATTORNEY INVESTIGATIONS 2", anchor="nw",
                              fill=GOLD, font=("Segoe UI", 12, "bold"), tags="hero_text")
        self.hero_headline = self.hero.create_text(
            28, 50, text="Расследование\nначинается по-русски", anchor="nw",
            fill=TEXT, font=("Segoe UI", 24, "bold"), tags="hero_text")
        # Reserve the action row before allocating the flexible content area.
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(side="bottom", fill="x", padx=28, pady=(10, 12))
        versions = tk.Frame(self.root, bg=BG)
        versions.pack(side="bottom", fill="x", padx=28)
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=28, pady=(14, 6))
        top = tk.Frame(body, bg=BG)
        top.pack(fill="x")
        self.title = tk.Label(top, text="Готовим материалы дела…", bg=BG, fg=TEXT,
                              font=("Segoe UI", 17, "bold"), anchor="w", justify="left",
                              width=1, wraplength=1)
        self.title.grid(row=0, column=0, sticky="ew")
        self.elapsed = tk.Label(top, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10))
        self.elapsed.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        top.columnconfigure(0, weight=1)
        self.title.bind("<Configure>", lambda e: self.title.config(wraplength=max(1, e.width - 4)))
        self.subtitle = tk.Label(body, text="Ищем установленную игру", bg=BG, fg=MUTED,
                                 font=("Segoe UI", 10), anchor="w", justify="left", width=1)
        self.subtitle.pack(fill="x", pady=(4, 10))
        self.subtitle.bind("<Configure>", lambda e: self.subtitle.config(wraplength=max(1, e.width - 4)))
        self.overall = AnimatedBar(body)
        self.overall.pack(fill="x")
        summary_row = tk.Frame(body, bg=BG)
        summary_row.pack(fill="x", pady=(4, 9))
        self.summary = tk.Label(summary_row, text="Подготовка", bg=BG, fg=GOLD,
                                font=("Segoe UI", 9), anchor="w")
        self.summary.pack(side="left")
        self.jump_button = tk.Button(summary_row, text="К текущему этапу", command=self.jump_to_phase,
                                     bg=BG, fg=CYAN, activebackground=PANEL, activeforeground=TEXT,
                                     relief="flat", bd=0, padx=7, pady=1, font=("Segoe UI", 9),
                                     cursor="hand2")
        self._build_progress(body)
        self.action = tk.Frame(footer, bg=GOLD, width=280, height=58)
        self.action.pack(side="right")
        self.action.pack_propagate(False)
        self.spinner = tk.Canvas(self.action, width=34, height=34, bg=GOLD, highlightthickness=0)
        self.spinner_image = self.spinner.create_image(0, 0, anchor="nw")
        self.start_button = tk.Button(self.action, text="Установить перевод", command=self.start,
                                     state="disabled", bg=GOLD, fg=BG, relief="flat",
                                     disabledforeground=BG, padx=8, font=("Segoe UI", 12, "bold"))
        self.start_button.pack(side="right", fill="both", expand=True)
        music = tk.Frame(footer, bg=BG)
        music.pack(side="left", padx=(0, 14))
        self.music_label = tk.Label(music, text="Музыка · ожидание", bg=BG, fg=MUTED,
                                    font=("Segoe UI", 9), anchor="w", bd=0, padx=0, highlightthickness=0)
        self.music_label.pack(fill="x")
        style.configure("Music.Horizontal.TScale", background=CYAN, troughcolor="#293949",
                        sliderlength=18, sliderthickness=18, borderwidth=0, gripcount=0)
        style.map("Music.Horizontal.TScale", background=[("disabled", "#495867"), ("active", TEXT)])
        style.configure("Progress.Vertical.TScrollbar", background="#53697b", troughcolor="#1d2b39",
                        bordercolor=BG, arrowcolor=TEXT, lightcolor="#53697b", darkcolor="#53697b")
        self.music_slider = ttk.Scale(music, from_=0, to=100, length=172,
                                     style="Music.Horizontal.TScale", command=self.set_music_volume)
        self.music_slider.set(self.music_volume)
        self.music_slider.state(["disabled"])
        self.music_slider.pack(fill="x")
        for button, value in (("Home", 0), ("End", 100)):
            self.music_slider.bind(f"<{button}>", lambda e, n=value: self.music_slider.set(n) or "break")
        tk.Button(footer, text="Журнал", command=self.show_log, bg=BG, fg=MUTED,
                  relief="flat", padx=10, pady=9).pack(side="left")
        self.folder_button = tk.Button(footer, text="Папка игры…", command=self.choose_game, state="disabled",
                                       bg=BG, fg=MUTED, relief="flat", pady=9)
        self.folder_button.pack(side="left")
        self.version_label = tk.Label(versions, text=self.args.release_tag or "",
                                      bg=BG, fg=MUTED, font=("Segoe UI", 9))
        if self.args.release_tag:
            self.version_label.pack(fill="x", anchor="w")
        self.version_label.config(anchor="w", justify="left", width=1)
        self.version_label.bind("<Configure>", lambda e: self.version_label.config(wraplength=max(1, e.width - 4)))
        self.version_actions = tk.Frame(versions, bg=BG)
        self.update_button = tk.Button(self.version_actions, command=self.update, bg=PANEL, fg=TEXT,
                                       relief="flat", padx=10, pady=3)
        self.rollback_button = tk.Button(self.version_actions, text="Вернуть предыдущую версию перевода",
                                         command=self.restore, bg=PANEL, fg=TEXT,
                                         relief="flat", padx=10, pady=3)
        self.root.bind("<Configure>", self.resize_hero)

    def _build_progress(self, body):
        pane = tk.Frame(body, bg=BG)
        pane.pack(fill="both", expand=True)
        self.viewport = tk.Canvas(pane, bg=BG, highlightthickness=0, takefocus=True)
        self.viewport.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(pane, orient="vertical", command=self.viewport.yview,
                                       style="Progress.Vertical.TScrollbar")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.viewport.config(yscrollcommand=self.scroll_progress)
        pane.rowconfigure(0, weight=1)
        pane.columnconfigure(0, weight=1)
        grid = tk.Frame(self.viewport, bg=BG)
        window = self.viewport.create_window(0, 0, window=grid, anchor="nw")
        self.viewport.bind("<Configure>", lambda e: self.viewport.itemconfigure(window, width=e.width))
        grid.bind("<Configure>", lambda e: self.viewport.config(scrollregion=self.viewport.bbox(window)))
        self.root.bind("<MouseWheel>", self.progress_wheel)
        self.viewport.bind("<Button-1>", lambda e: self.viewport.focus_set())
        for key, amount, unit in (("Up", -1, "units"), ("Down", 1, "units"),
                                  ("Prior", -1, "pages"), ("Next", 1, "pages")):
            self.viewport.bind(f"<{key}>", lambda e, n=amount, u=unit: self.viewport.yview_scroll(n, u))
        self.rows = {}
        phases = [p for p in PHASES if p[0] != "graphics" or not self.args.no_graphics]
        for i, (key, title) in enumerate(phases):
            row = PhaseSection(grid, title, DESCRIPTIONS[key], lambda k=key: self.toggle_phase(k),
                               lambda k=key: self.show_phase(k, header_only=True))
            row.grid(row=i, column=0, sticky="nsew", pady=(0, 3))
            self.rows[key] = row
        chapter_panel = tk.Frame(grid, bg=PANEL, padx=12, pady=4)
        chapter_panel.grid(row=len(phases), column=0, sticky="ew", pady=(0, 4))
        self.chapter_button = tk.Button(chapter_panel, command=self.toggle_chapters, bg=PANEL, fg=TEXT,
                                        relief="flat", anchor="w", font=("Segoe UI", 10))
        self.chapter_button.pack(fill="x")
        self.chapter_details = tk.Frame(chapter_panel, bg=PANEL)
        self.chapter_labels = {}
        for chapter in range(1, 6):
            label = tk.Label(self.chapter_details, text=f"Глава {chapter} · ожидание", bg=PANEL,
                             fg=MUTED, anchor="w", font=("Segoe UI", 9))
            label.pack(fill="x")
            self.chapter_labels[chapter] = label
        self.update_chapters()
        grid.columnconfigure(0, weight=1)

    def set_expanded_phases(self, keys):
        for key in self.expanded_phases ^ keys:
            self.rows[key].expand(key in keys)
        self.expanded_phases = keys

    def toggle_phase(self, key):
        if key in self.expanded_phases:
            self.set_expanded_phases(self.expanded_phases - {key})
            self.show_phase(key, header_only=True)
        else:
            self.open_phase(key)

    def open_phase(self, key):
        self.set_expanded_phases(self.expanded_phases | {key})
        self.show_phase(key)

    def show_phase(self, key, *, header_only=False):
        def scroll():
            self.reveal_job = None
            self.root.update_idletasks()
            row = self.rows[key]
            bounds = self.viewport.bbox("all")
            if not bounds or not row.winfo_ismapped():
                return
            row_top = row.winfo_y()
            row_height = row.header.winfo_height() if header_only else row.winfo_height()
            view_top = self.viewport.canvasy(0)
            view_height = self.viewport.winfo_height()
            if row_top < view_top or row_height >= view_height:
                target = row_top
            elif row_top + row_height > view_top + view_height:
                target = row_top + row_height - view_height
            else:
                return
            self.viewport.yview_moveto(target / max(1, bounds[3]))

        if self.reveal_job is not None:
            self.root.after_cancel(self.reveal_job)
        self.reveal_job = self.root.after_idle(scroll)

    def jump_to_phase(self):
        if self.active:
            self.open_phase(self.active)

    def scroll_progress(self, first, last):
        self.scrollbar.set(first, last)
        if float(first) > 0 or float(last) < 1:
            self.scrollbar.grid()
        else:
            self.scrollbar.grid_remove()

    def progress_wheel(self, event):
        widget = event.widget
        while widget is not None and widget is not self.viewport:
            widget = widget.master
        if widget is self.viewport and event.delta:
            steps = max(1, abs(event.delta) // 120)
            self.viewport.yview_scroll(-steps if event.delta > 0 else steps, "units")
            return "break"

    def resize_hero(self, event):
        if event.widget is self.root:
            short = event.height < 700
            self.hero.itemconfigure(self.hero_headline, font=("Segoe UI", 19 if short else 24, "bold"))
            bottom = self.hero.bbox(self.hero_headline)[3]
            self.hero.config(height=max(156, bottom + 26) if short else max(212, bottom + 42))
            self.hero.coords("scene", event.width - 28, self.hero_caption_y())
            self.hero.itemconfigure("scene", state="hidden" if short else "normal")

    def hero_caption_y(self):
        return int(self.hero.cget("height")) - 20

    def draw_hero_background(self, event=None):
        size = self.hero.winfo_width(), self.hero.winfo_height()
        if self.hero_image is None or size == self.background_size or min(size) <= 1:
            return
        from PIL import Image, ImageTk
        from PIL.ImageOps import fit

        image = fit(self.hero_image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.44))
        self.background = ImageTk.PhotoImage(image)
        self.hero.itemconfigure(self.hero_background, image=self.background)
        self.background_size = size

    def update_chapters(self):
        arrow = "▾" if self.chapter_details.winfo_manager() else "▸"
        self.chapter_button.config(text=f"{arrow}  Данные глав · проверено {len(self.checked_chapters)} из 5")

    def toggle_chapters(self):
        if self.chapter_details.winfo_manager():
            self.chapter_details.pack_forget()
        else:
            self.chapter_details.pack(fill="x")
            self.root.after_idle(lambda: self.viewport.yview_moveto(1))
        self.update_chapters()

    def check_updates(self):
        self.root.after(CHECK_INTERVAL_MS, self.check_updates)
        if not self.updating:
            threading.Thread(target=self.find_update, daemon=True).start()

    def find_update(self):
        try:
            self.events.put({"kind": "update_available", "release": latest(self.args.release_tag)})
        except Exception as exc:
            self.events.put({"kind": "log", "text": f"Проверка обновлений: {exc}"})

    def update(self):
        if not self.release or self.busy or self.updating or self.preparing:
            return
        self.updating = True
        self.update_button.config(text="Скачиваем установщик…")
        self.refresh_versions()
        release = self.release
        arguments = ["--gui"]
        for flag in ("no_graphics", "backup_graphics", "gk1_graphics", "full"):
            if getattr(self.args, flag):
                arguments.append("--" + flag.replace("_", "-"))
        if self.game:
            arguments.extend(("--game-path", str(self.game)))

        def worker():
            try:
                download_and_launch(self.args.update_cache, release, arguments, current=self.args.release_tag)
            except Exception as exc:
                self.events.put({"kind": "update_error", "text": str(exc)})
            else:
                self.events.put({"kind": "update_started"})

        threading.Thread(target=worker, daemon=True).start()

    def refresh_versions(self):
        from aai2ru import BACKUP_DIR, load_manifest

        manifest = load_manifest(self.game / BACKUP_DIR) if self.game and not self.args.preview else {}
        enabled = "normal" if not (self.busy or self.updating or self.preparing) else "disabled"
        self.folder_button.config(state=enabled)
        if not self.started:
            self.start_button.config(state=enabled if self.ready else "disabled")
        if self.release:
            if not self.updating:
                self.update_button.config(text="Обновить установщик")
            self.update_button.config(state=enabled)
            self.update_button.pack(side="right")
        else:
            self.update_button.pack_forget()
        installed = manifest.get("release_tag")
        tag = self.args.release_tag
        version_text = " · ".join(part for part in (
            f"Установщик {tag}" if tag else "",
            f"Перевод {installed}" if installed else "",
        ) if part)
        self.version_label.config(text=version_text)
        if version_text:
            before = self.version_actions if self.version_actions.winfo_manager() else None
            self.version_label.pack(fill="x", anchor="w", before=before)
        else:
            self.version_label.pack_forget()
        if manifest.get("rollback"):
            self.rollback_button.config(state=enabled)
            self.rollback_button.pack(side="right", padx=(0, 8))
        else:
            self.rollback_button.pack_forget()
        if self.release or manifest.get("rollback"):
            self.version_actions.pack(fill="x")
        else:
            self.version_actions.pack_forget()
        return manifest.get("rollback_tag") or "до последнего обновления"

    def restore(self):
        if self.busy or self.updating or self.preparing or not self.game:
            return
        tag = self.refresh_versions()
        if messagebox.askyesno("Вернуть предыдущую версию перевода",
                               f"Вернуть перевод ({tag})? Перед откатом закройте игру.",
                               parent=self.root):
            self.start(rollback=True)

    def prepare(self):
        try:
            import locate
            game = locate.find_game(self.args.game_path, progress=lambda s: self.events.put({"kind": "log", "text": s}))
            if not game:
                self.events.put({"kind": "missing"})
                return
            self.game = game
            from loading_assets import prepare, check_chapters
            from aai2ru import data_dir
            try:
                check_chapters(data_dir(self.args.data), self.events.put)
            except (OSError, ValueError, TypeError) as exc:
                self.events.put({"kind": "log", "text": traceback.format_exc()})
                self.events.put({"kind": "data_error", "text": str(exc)})
                return
            self.data_ok = True
            assets = prepare(game, Path(self.temp.name))
            self.events.put({"kind": "assets", **assets})
            from loading_audio import LoadingAudio
            audio = LoadingAudio()
            audio.start(game)
            self.events.put({"kind": "audio", "audio": audio})
            self.events.put({"kind": "ready", "path": str(game)})
        except Exception as exc:
            self.events.put({"kind": "log", "text": traceback.format_exc()})
            self.events.put({"kind": "prepare_error", "text": str(exc)})

    def choose_game(self):
        if self.updating or self.busy or self.preparing:
            return
        folder = filedialog.askdirectory(title="Выберите папку с GK12.exe")
        if folder:
            if self.audio:
                self.audio.stop()
                self.audio = None
            self.game = None
            self.data_ok = False
            self.ready = False
            self.preparing = True
            self.reset_progress()
            self.checked_chapters.clear()
            self.update_chapters()
            for chapter, label in self.chapter_labels.items():
                label.config(text=f"Глава {chapter} · ожидание", fg=MUTED)
            self.title.config(text="Ищем установленную игру")
            self.subtitle.config(text="")
            self.summary.config(text="Подготовка")
            self.update_music_status()
            self.args.game_path = folder
            self.folder_button.config(state="disabled")
            self.refresh_versions()
            threading.Thread(target=self.prepare, daemon=True).start()

    def reset_progress(self):
        self.started = self.active = self.last_progress = None
        self.graphics_detail = None
        self.completed.clear()
        self.elapsed.config(text="")
        self.overall.stop()
        self.overall.config(mode="determinate", value=0)
        self.overall.value = 0
        self.expanded_phases.clear()
        for row in self.rows.values():
            row.reset()
        self.jump_button.pack_forget()
        self.viewport.master.pack(fill="both", expand=True)
        self.viewport.yview_moveto(0)
        self.start_button.config(text="Установить перевод", state="disabled", command=self.start)

    def start(self, rollback=False):
        if (not self.ready and not rollback) or self.busy or self.updating or self.preparing:
            return
        self.reset_progress()
        self.rollback = rollback
        self.busy = True
        self.started = time.monotonic()
        self.last_progress = self.started
        self.action.config(bg=BUSY_BG, highlightbackground=BUSY_EDGE, highlightthickness=1)
        self.start_button.config(state="disabled", text="Возвращаем…" if rollback else "Устанавливаем…",
                                 bg=BUSY_BG, fg=BUSY_TEXT, activebackground=BUSY_BG,
                                 disabledforeground=BUSY_TEXT)
        self.spinner.config(bg=BUSY_BG)
        self.spinner.pack(side="left", before=self.start_button, padx=(12, 0))
        self.animate_spinner()
        self.append_log("Предпросмотр установки: файлы игры не меняются." if self.args.preview else "Начинаем установку перевода.")
        self.folder_button.config(state="disabled")
        self.title.config(text="Возвращаем предыдущий перевод" if rollback else "Собираем русский перевод")
        self.progress_description = "Проверяем резервную копию" if rollback else "Готовим файлы игры"
        self.subtitle.config(text=self.progress_description)
        self.summary.config(text="Восстановление файлов" if rollback else f"Завершено этапов: 0 из {len(self.rows)}")
        if rollback:
            self.viewport.master.pack_forget()
            self.overall.config(mode="indeterminate")
            self.overall.start()
        self.refresh_versions()
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        args = copy.copy(self.args)
        args.game_path = str(self.game)
        args.progress = self.events.put
        args.rollback = self.rollback
        failure = None
        try:
            if args.preview:
                # Демонстрация интерфейса: этот путь не вызывает установщик.
                for key, title in PHASES:
                    if key not in self.rows:
                        continue
                    self.events.put({"kind": "phase", "id": key, "title": title})
                    for n in range(1, 9):
                        time.sleep(.6)
                        self.events.put({"kind": "progress", "id": key, "current": n, "total": 8})
                    self.events.put({"kind": "phase_done", "id": key})
                code = 0
            else:
                code = self.runner(args)
        except Exception as exc:
            self.events.put({"kind": "log", "text": traceback.format_exc()})
            if isinstance(exc, MemoryError):
                failure = "memory"
            code = 1
        self.events.put({"kind": "finished", "code": code, "failure": failure})

    def handle(self, event):
        kind = event.get("kind")
        if kind == "log":
            self.append_log(event["text"])
        elif kind == "update_available":
            self.release = event["release"]
            self.refresh_versions()
        elif kind == "update_error":
            self.updating = False
            self.refresh_versions()
            self.append_log(event["text"])
            messagebox.showerror("Обновление установщика", event["text"], parent=self.root)
        elif kind == "update_started":
            self.updating = False
            self.close()
            return True
        elif kind == "audio":
            self.audio = event["audio"]
            self.audio.set_volume(self.music_volume / 100)
        elif kind == "assets":
            if event.get("warning"):
                self.append_log(event["warning"])
            self.scenes = event.get("scenes", [])
            if event.get("background"):
                from PIL import Image

                with Image.open(event["background"]) as image:
                    self.hero_image = image.convert("RGB")
                self.background_size = None
                self.draw_hero_background()
        elif kind in ("ready", "prepare_error"):
            self.preparing = False
            self.ready = self.game is not None and self.data_ok
            if self.ready:
                self.append_log("Игра найдена: " + str(self.game))
            self.start_button.config(state="normal" if self.ready else "disabled")
            self.folder_button.config(state="normal")
            self.title.config(text="Перевод готов к установке" if self.ready else "Нужна папка игры")
            self.subtitle.config(text=str(self.game) if self.ready else event.get("text", ""))
            if kind == "prepare_error":
                self.append_log("Оформление: " + event["text"])
            if self.args.preview:
                self.summary.config(text="ПРЕДПРОСМОТР · файлы игры не изменяются")
            else:
                self.summary.config(text="Начните установку, когда игра закрыта")
            self.refresh_versions()
        elif kind == "missing":
            self.preparing = False
            self.title.config(text="Укажите папку игры")
            self.subtitle.config(text="Выберите папку с GK12.exe кнопкой внизу")
            self.summary.config(text="")
            self.folder_button.config(state="normal")
            self.refresh_versions()
        elif kind == "chapter":
            chapter, count = event["chapter"], event["count"]
            self.checked_chapters.add(chapter)
            self.update_chapters()
            self.chapter_labels[chapter].config(text=f"Глава {chapter} · {count:,} записей".replace(",", " "), fg=CYAN)
            self.append_log(f"Глава {chapter}: данные проверены, записей {count}.")
        elif kind == "data_error":
            self.preparing = False
            self.ready = self.data_ok = False
            self.title.config(text="Не удалось проверить данные перевода")
            self.subtitle.config(text=event["text"])
            self.summary.config(text="Подробности в журнале")
            self.append_log("Ошибка данных: " + event["text"])
            self.folder_button.config(state="normal")
            self.refresh_versions()
        elif kind == "phase" and event.get("id") in self.rows:
            key = event["id"]
            self.append_log("Этап: " + event.get("title", key))
            self.active = key
            self.last_progress = time.monotonic()
            row = self.rows[key]
            row.set_state("В работе", active=True)
            row.bar.config(mode="indeterminate")
            row.bar.start()
            self.jump_button.pack(side="right")
            if not self.expanded_phases:
                self.open_phase(key)
            else:
                self.set_expanded_phases(self.expanded_phases | {key})
            self.title.config(text=row.title)
            self.progress_description = DESCRIPTIONS[key]
            self.subtitle.config(text=self.progress_description)
        elif kind == "progress" and event.get("id") in self.rows:
            key = event["id"]
            row = self.rows[key]
            self.last_progress = time.monotonic()
            total = event.get("total", 0)
            count = event.get("current", 0)
            self.progress_description = DESCRIPTIONS[key]
            if total:
                row.bar.stop()
                row.bar.config(mode="determinate", value=100 * count / total)
                self.overall["value"] = 100 * (len(self.completed) + count / total) / len(self.rows)
                row.set_state(f"{count} из {total}", active=key == self.active)
                self.progress_description += f" · {count} из {total}"
            detail = event.get("detail")
            row.record(detail, count, streaming=key == "graphics")
            if key == "graphics" and detail and detail != self.graphics_detail:
                self.graphics_detail = detail
                self.append_log(f"Графика: {detail} · обработано {count} из {total}")
            self.subtitle.config(text=self.progress_description)
        elif kind == "phase_done" and event.get("id") in self.rows:
            key = event["id"]
            row = self.rows[key]
            self.append_log("Этап завершён: " + row.title)
            self.completed.add(key)
            if self.active == key:
                self.active = None
                self.jump_button.pack_forget()
            row.finish()
            self.set_expanded_phases(self.expanded_phases - {key})
            self.overall["value"] = 100 * len(self.completed) / len(self.rows)
            self.summary.config(text=f"Завершено этапов: {len(self.completed)} из {len(self.rows)}")
            if len(self.completed) == len(self.rows):
                self.last_progress = time.monotonic()
                self.title.config(text="Завершаем установку")
                self.progress_description = "Сохраняем итоговое состояние"
                self.subtitle.config(text=self.progress_description)
        elif kind == "finished":
            self.busy = False
            self.code = event["code"]
            self.spinner.pack_forget()
            if self.spinner_job is not None:
                self.root.after_cancel(self.spinner_job)
                self.spinner_job = None
            self.jump_button.pack_forget()
            self.action.config(bg=GOLD, highlightthickness=0)
            self.start_button.config(bg=GOLD, fg=BG, activebackground="#f0cd90", disabledforeground=BG)
            action = "Откат" if self.rollback else "Установка"
            self.append_log("Предпросмотр завершён." if self.args.preview else
                            f"{action}: {'готово' if not self.code else 'ошибка'}.")
            if self.audio:
                self.audio.stop()
            self.overall.stop()
            self.overall.config(mode="determinate")
            for row in self.rows.values():
                row.bar.stop()
            title = "Предыдущая версия перевода возвращена" if self.rollback else "Всё готово. Можно начинать!"
            if self.args.preview and not self.code:
                title = "Предпросмотр завершён"
            if self.code:
                title = f"{action}: ошибка"
                if self.active:
                    row = self.rows[self.active]
                    row.set_state("Ошибка", error=True)
                    title = f"Ошибка: {row.title.lower()}"
            self.title.config(text=title)
            if event.get("failure") == "memory":
                message = "Не хватило памяти для обработки файлов. Подробности в журнале."
            elif self.code:
                message = "Подробности ошибки — в журнале."
            elif self.args.preview:
                message = "Игра не изменена."
            else:
                message = "Выберите «Русский» в настройках игры."
            self.subtitle.config(text=message)
            if not self.code:
                self.overall["value"] = 100
            self.start_button.config(text="Закрыть", state="normal", command=self.close)
            self.refresh_versions()

    def poll(self):
        for _ in range(100):
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            try:
                if self.handle(event):
                    return
            except Exception:
                self.root.report_callback_exception(*sys.exc_info())
        self.root.after(60, self.poll)

    def tick(self):
        self.root.after(150, self.tick)
        if self.started and self.busy:
            seconds = int(time.monotonic() - self.started)
            self.elapsed.config(text=f"{seconds // 60:02d}:{seconds % 60:02d}")
            if self.last_progress and time.monotonic() - self.last_progress >= 30:
                self.subtitle.config(text=f"{self.progress_description} · новых данных о ходе работы пока нет")
            scene = self.scenes[(seconds // 7) % len(self.scenes)] if self.scenes else None
            if scene and scene != getattr(self, "displayed_scene", None):
                self.displayed_scene = scene
                self.hero.delete("scene")
                self.hero.create_text(self.hero.winfo_width() - 28, self.hero_caption_y(), text=scene, anchor="e",
                                      fill=TEXT, font=("Segoe UI", 10), tags="scene",
                                      state="hidden" if self.root.winfo_height() < 700 else "normal")
        self.update_music_status()

    def animate_spinner(self):
        self.spinner_job = None
        if not self.busy:
            return
        span = round(self.overall.value * 3.6)
        start = -90
        if self.overall.target == 0:
            start = round(time.monotonic() * 260) % 360
            span = 76
        key = start, span
        if key != self.spinner_key:
            self.draw_ring(start, span)
            self.spinner_key = key
        self.spinner_job = self.root.after(40, self.animate_spinner)

    def draw_ring(self, start, span):
        from PIL import Image, ImageDraw, ImageTk

        size, center, radius, weight = 136, 68, 46, 10
        image = Image.new("RGB", (size, size), BUSY_BG)
        draw = ImageDraw.Draw(image)
        ring = (center - radius, center - radius, center + radius, center + radius)
        draw.ellipse(ring, outline=BUSY_EDGE, width=weight)
        if span >= 360:
            draw.ellipse(ring, outline=BUSY_RING, width=weight)
        elif span:
            draw.arc(ring, start, start + span, fill=BUSY_RING, width=weight)
            for angle in (start, start + span):
                angle = math.radians(angle)
                x = center + (radius - weight / 2) * math.cos(angle)
                y = center + (radius - weight / 2) * math.sin(angle)
                offset = weight / 2
                draw.ellipse((x - offset, y - offset, x + offset, y + offset), fill=BUSY_RING)
        self.ring_photo = ImageTk.PhotoImage(image.resize((34, 34), Image.Resampling.LANCZOS))
        self.spinner.itemconfigure(self.spinner_image, image=self.ring_photo)

    def set_music_volume(self, value):
        self.music_volume = round(float(value))
        if self.audio:
            self.audio.set_volume(self.music_volume / 100)
        self.update_music_status()

    def update_music_status(self):
        if self.audio and self.audio.available:
            status = "playing"
            text = f"Музыка · {self.music_volume}%"
        elif self.audio and self.audio.error:
            status, text = "error", "Музыка недоступна"
        elif self.started and not self.busy:
            status, text = "stopped", "Музыка остановлена"
        elif self.preparing or self.audio:
            status, text = "loading", "Загрузка музыки…"
        else:
            status, text = "unavailable", "Музыка недоступна"
        if status != self.audio_status:
            self.audio_status = status
            self.music_slider.state(["!disabled" if status == "playing" else "disabled"])
            if status == "playing":
                self.append_log("Музыка готова.")
            elif status == "error":
                self.append_log("Музыка недоступна: " + self.audio.error)
        self.music_label.config(text=text, fg=TEXT if status == "playing" else MUTED)

    def append_log(self, message):
        line = time.strftime("%H:%M:%S") + "  " + message
        self.log.append(line)
        if self.log_text is not None and self.log_text.winfo_exists():
            follow = self.log_text.yview()[1] >= 0.999
            self.log_text.config(state="normal")
            self.log_text.insert("end", line + "\n")
            if follow:
                self.log_text.see("end")
            self.log_text.config(state="disabled")

    def report_ui_exception(self, exc_type, exc, tb):
        self.append_log("Ошибка интерфейса:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))

    def show_log(self):
        if self.log_window is not None and self.log_window.winfo_exists():
            self.log_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.log_window = window
        window.title("Журнал установки")
        window.geometry("860x470")
        text = tk.Text(window, width=110, height=28, bg=PANEL, fg=TEXT, wrap="word")
        self.log_text = text
        text.pack(fill="both", expand=True)
        text.insert("1.0", "\n".join(self.log) + "\n")
        text.config(state="disabled")
        text.see("end")

    def close(self):
        if self.busy or self.updating:
            messagebox.showinfo("Идёт обновление" if self.updating else "Перевод",
                                "Дождитесь окончания операции. Окно можно свернуть.")
            return
        if self.preparing:
            messagebox.showinfo("Подготовка", "Дождитесь окончания поиска и загрузки оформления.")
            return
        if self.audio:
            self.audio.stop()
        self.temp.cleanup()
        for callback in self.root.tk.splitlist(self.root.tk.call("after", "info")):
            self.root.tk.call("after", "cancel", callback)
        self.root.destroy()


def launch(args, runner):
    app = Installer(args, runner)

    def mark_ready():
        if not announce_ready(args.release_tag):
            app.code = 1
            app.temp.cleanup()
            app.root.destroy()

    app.root.after_idle(mark_ready)
    app.root.mainloop()
    return app.code

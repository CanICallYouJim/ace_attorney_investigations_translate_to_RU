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

PHASES = [
    ("scripts", "Реплики и сцены"), ("strings", "Органайзер и улики"),
    ("gk1", "Язык первой игры"), ("fonts", "Русские шрифты"),
    ("graphics", "Графика и звуки"),
]
BG, PANEL, TEXT, MUTED = "#101923", "#162330", "#eff4f5", "#a7b7c7"
GOLD, CYAN = "#e5be79", "#70d4d0"
DESCRIPTIONS = {
    "scripts": "Главы 1–5 и общая механика", "strings": "Улики, профили и меню",
    "gk1": "Немецкий → английский", "fonts": "Кириллица и размеры символов",
    "graphics": "Изображения, ролики и аудио",
}


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
        self.delete("all")
        if right > left:
            self.create_rectangle(left, 0, right, height, fill=CYAN, outline="")
            # Clip each diagonal to the filled rectangle, including its leading edge.
            offset = (age * 32) % 24
            for x in range(-24, width + 24, 24):
                a = x + offset
                if a + 9 < left or a - 9 > right:
                    continue
                points = [max(left, min(right, px)) for px in (a, a + 9, a - 1, a - 10)]
                self.create_polygon(points[0], 0, points[1], 0, points[2], height,
                                    points[3], height, fill="#98e4df", outline="")
        self.after(33, self.animate)


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
        self.root.geometry("1060x820")
        self.root.minsize(940, 780)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.temp = tempfile.TemporaryDirectory(prefix="aai2-loading-")
        self.busy = False
        self.ready = False
        self.preparing = True
        self.code = 0
        self.game = None
        self.audio = None
        self.muted = False
        self.log = []
        self.log_window = self.log_text = None
        self.audio_status = None
        self.data_ok = False
        self.completed = set()
        self.active = None
        self.scenes = []
        self.started = None
        self._build()
        self.root.report_callback_exception = self.report_ui_exception
        self.root.after(60, self.poll)
        threading.Thread(target=self.prepare, daemon=True).start()

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Load.Horizontal.TProgressbar", troughcolor="#293949",
                        background=CYAN, borderwidth=0, lightcolor=CYAN, darkcolor=CYAN)
        self.hero = tk.Canvas(self.root, height=230, bg="#203144", highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.create_text(40, 35, text="ACE ATTORNEY INVESTIGATIONS 2", anchor="nw",
                              fill=GOLD, font=("Segoe UI", 12, "bold"), tags="hero_text")
        self.hero.create_text(40, 69, text="Расследование\nначинается по-русски", anchor="nw",
                              fill=TEXT, font=("Segoe UI", 24, "bold"), tags="hero_text")
        self.hero.create_text(42, 181, text="УСТАНОВКА РУССКОЙ ЛОКАЛИЗАЦИИ", anchor="nw",
                              fill=TEXT, font=("Segoe UI", 10), tags="hero_text")
        # Reserve the action row before allocating the flexible content area.
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(side="bottom", fill="x", padx=38, pady=(12, 18))
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=38, pady=(19, 15))
        top = tk.Frame(body, bg=BG)
        top.pack(fill="x")
        self.title = tk.Label(top, text="Готовим материалы дела…", bg=BG, fg=TEXT,
                              font=("Segoe UI", 17, "bold"), anchor="w")
        self.title.pack(side="left")
        self.elapsed = tk.Label(top, text="", bg=BG, fg=MUTED, font=("Segoe UI", 10))
        self.elapsed.pack(side="right")
        self.subtitle = tk.Label(body, text="Ищем установленную игру", bg=BG, fg=MUTED,
                                 font=("Segoe UI", 10), anchor="w")
        self.subtitle.pack(fill="x", pady=(4, 10))
        self.overall = AnimatedBar(body)
        self.overall.pack(fill="x")
        self.summary = tk.Label(body, text="Подготовка", bg=BG, fg=GOLD,
                                font=("Segoe UI", 9), anchor="w")
        self.summary.pack(fill="x", pady=(4, 12))
        grid = tk.Frame(body, bg=BG)
        grid.pack(fill="x")
        self.rows = {}
        self.scene_labels = {}
        phases = [p for p in PHASES if p[0] != "graphics" or not self.args.no_graphics]
        for i, (key, title) in enumerate(phases):
            row = tk.Frame(grid, bg=PANEL, padx=13, pady=7)
            row.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 10), pady=(0, 8))
            label = tk.Label(row, text=title, bg=PANEL, fg=MUTED, anchor="w", font=("Segoe UI", 10))
            label.pack(fill="x")
            scene_label = tk.Label(row, text=DESCRIPTIONS[key], bg=PANEL, fg=GOLD, anchor="w", font=("Segoe UI", 8))
            scene_label.pack(fill="x")
            self.scene_labels[key] = scene_label
            bar = AnimatedBar(row)
            bar.pack(fill="x", pady=(4, 0))
            self.rows[key] = (label, bar, title)
        chapter_panel = tk.Frame(grid, bg=PANEL, padx=13, pady=7)
        chapter_panel.grid(row=len(phases) // 2, column=len(phases) % 2, sticky="nsew", padx=(0, 10), pady=(0, 8))
        tk.Label(chapter_panel, text="Проверка данных глав", bg=PANEL, fg=TEXT,
                 anchor="w", font=("Segoe UI", 10)).pack(fill="x")
        self.chapter_labels = {}
        for chapter in range(1, 6):
            label = tk.Label(chapter_panel, text=f"Глава {chapter} · ожидание", bg=PANEL,
                             fg=MUTED, anchor="w", font=("Segoe UI", 8))
            label.pack(fill="x")
            self.chapter_labels[chapter] = label
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        self.action = tk.Frame(footer, bg=GOLD, width=310, height=62)
        self.action.pack(side="right")
        self.action.pack_propagate(False)
        self.spinner = tk.Canvas(self.action, width=26, height=26, bg=GOLD, highlightthickness=0)
        self.start_button = tk.Button(self.action, text="Установить перевод", command=self.start,
                                     state="disabled", bg=GOLD, fg=BG, relief="flat",
                                     disabledforeground=BG, padx=20, pady=14, font=("Segoe UI", 12, "bold"))
        self.start_button.pack(side="right", fill="both", expand=True)
        self.music_button = tk.Button(footer, text="Музыка · загрузка", command=self.toggle_music,
                                      bg=PANEL, fg=TEXT, relief="flat", padx=12, pady=9)
        self.music_button.pack(side="left")
        tk.Button(footer, text="Журнал", command=self.show_log, bg=BG, fg=MUTED,
                  relief="flat", padx=14, pady=9).pack(side="left")
        self.folder_button = tk.Button(footer, text="Папка игры…", command=self.choose_game, state="disabled",
                                       bg=BG, fg=MUTED, relief="flat", pady=9)
        self.folder_button.pack(side="left")

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
            self.audio = LoadingAudio()
            self.audio.start(game)
            self.audio.set_muted(self.muted)
            self.events.put({"kind": "ready", "path": str(game)})
        except Exception as exc:
            self.events.put({"kind": "log", "text": traceback.format_exc()})
            self.events.put({"kind": "prepare_error", "text": str(exc)})

    def choose_game(self):
        folder = filedialog.askdirectory(title="Выберите папку с GK12.exe")
        if folder:
            if self.audio:
                self.audio.stop()
            self.ready = False
            self.preparing = True
            self.start_button.config(state="disabled")
            self.args.game_path = folder
            self.folder_button.config(state="disabled")
            threading.Thread(target=self.prepare, daemon=True).start()

    def start(self):
        if not self.ready or self.busy:
            return
        self.busy = True
        self.started = time.monotonic()
        self.start_button.config(state="disabled", text="Устанавливается…")
        self.spinner.pack(side="left", before=self.start_button, padx=(12, 0))
        self.append_log("Предпросмотр установки: файлы игры не меняются." if self.args.preview else "Начинаем установку перевода.")
        self.folder_button.config(state="disabled")
        self.title.config(text="Собираем русский перевод")
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        args = copy.copy(self.args)
        args.game_path = str(self.game)
        args.progress = self.events.put
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
            code = 1
        self.events.put({"kind": "finished", "code": code})

    def handle(self, event):
        kind = event.get("kind")
        if kind == "log":
            self.append_log(event["text"])
        elif kind == "assets":
            if event.get("warning"):
                self.append_log(event["warning"])
            self.scenes = event.get("scenes", [])
            if event.get("background"):
                from PIL import Image, ImageTk
                from PIL.ImageOps import fit
                image = Image.open(event["background"]).convert("RGB")
                self.background = ImageTk.PhotoImage(fit(image, (1400, 300)))
                self.hero.create_image(0, 0, image=self.background, anchor="nw")
                self.hero.tag_raise("hero_text")
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
        elif kind == "missing":
            self.preparing = False
            self.title.config(text="Укажите папку игры")
            self.subtitle.config(text="Выберите папку с GK12.exe кнопкой внизу")
            self.folder_button.config(state="normal")
        elif kind == "chapter":
            chapter, count = event["chapter"], event["count"]
            self.chapter_labels[chapter].config(text=f"Глава {chapter} · данные проверены · {count:,}".replace(",", " "), fg=CYAN)
            self.append_log(f"Глава {chapter}: данные проверены, записей {count}.")
        elif kind == "data_error":
            self.preparing = False
            self.ready = self.data_ok = False
            self.title.config(text="Не удалось проверить данные перевода")
            self.subtitle.config(text=event["text"])
            self.append_log("Ошибка данных: " + event["text"])
            self.folder_button.config(state="normal")
        elif kind == "phase" and event.get("id") in self.rows:
            key = event["id"]
            self.append_log("Этап: " + event.get("title", key))
            self.active = key
            label, bar, title = self.rows[key]
            label.config(text=title + " · в работе", fg=CYAN)
            bar.config(mode="indeterminate")
            bar.start(18)
            self.title.config(text=event.get("title", title), font=("Segoe UI", 14, "bold"), wraplength=920)
            self.subtitle.config(text="Читаем и собираем файлы игры…")
        elif kind == "progress" and event.get("id") in self.rows:
            label, bar, title = self.rows[event["id"]]
            total = event.get("total", 0)
            if total:
                bar.stop()
                bar.config(mode="determinate", value=100 * event["current"] / total)
                self.overall["value"] = 100 * (len(self.completed) + event["current"] / total) / len(self.rows)
                label.config(text=f"{title} · {event['current']}/{total}")
            self.subtitle.config(text=event.get("detail") or "Собираем файлы игры…")
        elif kind == "phase_done" and event.get("id") in self.rows:
            key = event["id"]
            self.append_log("Этап завершён: " + self.rows[key][2])
            self.completed.add(key)
            label, bar, title = self.rows[key]
            bar.stop()
            bar.config(mode="determinate", value=100)
            label.config(text=title + " · готово", fg=TEXT)
            self.overall["value"] = 100 * len(self.completed) / len(self.rows)
            self.summary.config(text=f"Завершено этапов: {len(self.completed)} из {len(self.rows)}")
        elif kind == "finished":
            self.busy = False
            self.code = event["code"]
            self.spinner.pack_forget()
            self.append_log("Предпросмотр завершён; игра не изменена." if self.args.preview else
                            ("Установка завершена." if not self.code else "Установка остановлена с ошибкой."))
            if self.audio:
                self.audio.stop()
            for _, bar, _ in self.rows.values():
                bar.stop()
            self.title.config(text="Предпросмотр завершён" if self.args.preview else
                              ("Всё готово. Можно начинать!" if not self.code else "Установка остановлена"))
            self.subtitle.config(text="Выберите «Русский» в настройках игры." if not self.code and not self.args.preview
                                 else ("Игра не изменена." if self.args.preview else "Подробности ошибки — в журнале."))
            if not self.code:
                self.overall["value"] = 100
            self.start_button.config(text="Закрыть", state="normal", command=self.close)

    def poll(self):
        for _ in range(100):
            try:
                self.handle(self.events.get_nowait())
            except queue.Empty:
                break
        if self.started and self.busy:
            self.spinner.delete("all")
            self.spinner.create_oval(4, 4, 23, 23, outline="#bc954f", width=3)
            self.spinner.create_arc(4, 4, 23, 23, start=-(time.monotonic() * 230) % 360,
                                    extent=100, style="arc", outline=BG, width=3)
            seconds = int(time.monotonic() - self.started)
            self.elapsed.config(text=f"{seconds // 60:02d}:{seconds % 60:02d}")
            if self.scenes and seconds % 7 == 0:
                scene = self.scenes[(seconds // 7) % len(self.scenes)]
                self.hero.delete("scene")
                self.hero.create_text(self.hero.winfo_width() - 30, 215, text=f"СЦЕНЫ ИГРЫ · {scene}", anchor="e",
                                      fill=TEXT, font=("Segoe UI", 10), tags="scene")
        if self.audio:
            available = getattr(self.audio, "available", True)
            audio_status = "playing" if available else ("error" if self.audio.error else "loading")
            if audio_status != self.audio_status:
                self.audio_status = audio_status
                if available:
                    self.append_log("Музыка готова: громкость 35%." + (" Звук выключен." if self.muted else ""))
                elif self.audio.error:
                    self.append_log("Музыка недоступна: " + self.audio.error)
            self.music_button.config(text="Музыка · выкл." if self.muted else
                                     ("Музыка · 35%" if available else
                                      ("Музыка · недоступна" if self.audio.error else
                                       ("Музыка · остановлена" if self.started and not self.busy else "Музыка · загрузка"))))
        self.root.after(60, self.poll)

    def toggle_music(self):
        self.muted = not self.muted
        if self.audio:
            self.audio.set_muted(self.muted)
        self.append_log("Музыка выключена." if self.muted else "Музыка включена: 35%.")

    def append_log(self, message):
        line = time.strftime("%H:%M:%S") + "  " + message
        self.log.append(line)
        if self.log_text is not None and self.log_text.winfo_exists():
            self.log_text.config(state="normal")
            self.log_text.insert("end", line + "\n")
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
        if self.busy:
            messagebox.showinfo("Идёт установка", "Дождитесь окончания записи файлов. Окно можно свернуть.")
            return
        if self.preparing:
            messagebox.showinfo("Подготовка", "Дождитесь окончания поиска и загрузки оформления.")
            return
        if self.audio:
            self.audio.stop()
        self.temp.cleanup()
        self.root.destroy()


def launch(args, runner):
    app = Installer(args, runner)
    app.root.mainloop()
    return app.code

# -*- coding: utf-8 -*-
"""
yt-dlp 视频下载助手 - 桌面版（terminal-gui-hybrid 风格）
基于 customtkinter，深色终端美学 + 现代 GUI 控件
"""

import os
import re
import sys
import json
import time
import shutil
import threading
import subprocess

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

# ============================================================
# 设计令牌（terminal-gui-hybrid）
# ============================================================
COLORS = {
    "bg": "#0B1220",
    "surface": "#111827",
    "panel": "#1F2937",
    "panel_hover": "#273449",
    "border": "#2D3B52",
    "accent": "#38BDF8",
    "accent_dim": "#1E3A5F",
    "success": "#22C55E",
    "success_dim": "#14532D",
    "error": "#F87171",
    "error_dim": "#450A0A",
    "warning": "#FBBF24",
    "processing": "#C084FC",
    "text": "#E5E7EB",
    "text_dim": "#94A3B8",
    "text_mute": "#64748B",
    "log_bg": "#050A14",
    "log_text": "#CFFFE0",
}

FONT_UI = ("Microsoft YaHei UI", 12)
FONT_UI_SM = ("Microsoft YaHei UI", 10)
FONT_UI_BOLD = ("Microsoft YaHei UI", 12, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_MONO = ("Consolas", 11)
FONT_MONO_SM = ("Consolas", 10)

STATUS_TEXT = {
    "pending": "等待中", "starting": "启动中", "downloading": "下载中",
    "processing": "处理中", "completed": "已完成", "error": "失败", "cancelled": "已取消",
}
STATUS_COLOR = {
    "pending": COLORS["text_mute"], "starting": COLORS["text_mute"],
    "downloading": COLORS["accent"], "processing": COLORS["processing"],
    "completed": COLORS["success"], "error": COLORS["error"], "cancelled": COLORS["text_mute"],
}

PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
SPEED_RE = re.compile(r"at\s+([\d.]+\s*[KMGT]?i?B/s)")
ETA_RE = re.compile(r"ETA\s+(\d+:\d+)")
DEST_RE = re.compile(r"\[download\]\s+Destination:\s+(.+)")


def app_dir():
    """程序所在目录（打包后为 EXE 所在目录，开发时为脚本目录）"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ytdlp():
    d = app_dir()
    for c in [
        os.path.join(d, "yt-dlp.exe"),
        os.path.join(os.path.expanduser("~"), "Desktop", "yt-dlp.exe"),
    ]:
        if os.path.isfile(c):
            return c
    return shutil.which("yt-dlp")


def find_ffmpeg():
    d = app_dir()
    for c in [os.path.join(d, "ffmpeg.exe")]:
        if os.path.isfile(c):
            return c
    return shutil.which("ffmpeg")


# ============================================================
# 任务模型
# ============================================================
class DownloadTask:
    _counter = 0
    _lock = threading.Lock()

    def __init__(self, url, opts, save_dir):
        with DownloadTask._lock:
            DownloadTask._counter += 1
            self.id = f"t{DownloadTask._counter}"
        self.url = url
        self.opts = opts
        self.save_dir = save_dir
        self.status = "pending"
        self.progress = 0.0
        self.speed = ""
        self.eta = ""
        self.log = []
        self.output_file = ""
        self.proc = None
        self.cancel = False
        self.created_at = time.time()
        self.card = None

    def build_args(self, ytdlp):
        args = [ytdlp, "--no-warnings", "--newline", "--progress"]
        fmt = self.opts.get("format", "best")
        if fmt == "mp3":
            args += ["-x", "--audio-format", "mp3"]
        elif fmt == "height":
            h = self.opts.get("quality", "1080")
            args += ["-f", f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"]
        if self.opts.get("first_only"):
            args += ["--playlist-items", "1"]
        if self.opts.get("subs"):
            args += ["--write-subs", "--sub-langs", "all.*,zh.*,en.*"]
        if self.save_dir:
            args += ["-P", self.save_dir]
        args.append(self.url)
        return args

    def run(self, ytdlp, on_update):
        self.status = "starting"
        self.log.append(f"▶ 开始: {self.url}")
        on_update(self)
        try:
            args = self.build_args(ytdlp)
            env = os.environ.copy()
            d = app_dir()
            if d not in env.get("PATH", ""):
                env["PATH"] = d + os.pathsep + env.get("PATH", "")
            self.proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=env,
            )
            for raw in self.proc.stdout:
                if self.cancel:
                    break
                for seg in raw.rstrip("\r\n").split("\r"):
                    seg = seg.strip()
                    if not seg:
                        continue
                    m = PROGRESS_RE.search(seg)
                    if m:
                        self.progress = min(float(m.group(1)), 100.0)
                        self.status = "downloading"
                        sm = SPEED_RE.search(seg)
                        if sm: self.speed = sm.group(1)
                        em = ETA_RE.search(seg)
                        if em: self.eta = em.group(1)
                    dm = DEST_RE.search(seg)
                    if dm: self.output_file = dm.group(1).strip()
                    if "Merger" in seg or "ExtractAudio" in seg or "FFmpeg" in seg:
                        self.status = "processing"
                    if not (PROGRESS_RE.search(seg) and len(seg) < 120):
                        self.log.append(seg)
                    if len(self.log) > 300:
                        self.log = self.log[-200:]
                    on_update(self)
            self.proc.wait()
            code = self.proc.poll()
            if self.cancel:
                self.status = "cancelled"
                self.log.append("⏹ 已取消")
            elif code == 0:
                self.status = "completed"
                self.progress = 100.0
                self.log.append("✅ 下载完成")
            else:
                self.status = "error"
                self.log.append(f"❌ 失败（退出码 {code}）")
        except FileNotFoundError:
            self.status = "error"
            self.log.append("❌ 找不到 yt-dlp.exe")
        except Exception as e:
            self.status = "error"
            self.log.append(f"❌ 错误: {e}")
        finally:
            self.proc = None
            on_update(self)


# ============================================================
# 任务卡片 UI
# ============================================================
class TaskCard(ctk.CTkFrame):
    def __init__(self, master, task, app):
        super().__init__(master, corner_radius=10, fg_color=COLORS["surface"],
                         border_color=COLORS["border"], border_width=1)
        self.task = task
        self.app = app
        self.task.card = self

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))
        self.title_label = ctk.CTkLabel(top, text=task.url[:60] + ("..." if len(task.url) > 60 else ""),
                                         font=FONT_MONO_SM, text_color=COLORS["text"], anchor="w")
        self.title_label.pack(side="left", fill="x", expand=True)
        self.status_label = ctk.CTkLabel(top, text=STATUS_TEXT.get(task.status, task.status),
                                          font=("Microsoft YaHei UI", 9, "bold"),
                                          text_color=STATUS_COLOR.get(task.status, COLORS["text"]),
                                          width=60, anchor="e")
        self.status_label.pack(side="right")

        self.progress = ctk.CTkProgressBar(self, height=6, corner_radius=3,
                                            progress_color=COLORS["accent"], fg_color=COLORS["bg"])
        self.progress.set(0)
        self.progress.pack(fill="x", padx=12, pady=(4, 2))

        self.meta_label = ctk.CTkLabel(self, text="", font=FONT_MONO_SM, text_color=COLORS["text_mute"], anchor="w")
        self.meta_label.pack(fill="x", padx=12, pady=(0, 4))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))
        self.view_log_btn = ctk.CTkButton(btn_row, text="查看日志", width=70, height=26,
                                            font=FONT_UI_SM, fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                                            hover_color=COLORS["panel_hover"], command=self._view_log)
        self.view_log_btn.pack(side="left", padx=2)
        self.reveal_btn = ctk.CTkButton(btn_row, text="打开文件夹", width=80, height=26,
                                         font=FONT_UI_SM, fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                                         hover_color=COLORS["panel_hover"], command=self._reveal, state="disabled")
        self.reveal_btn.pack(side="left", padx=2)
        self.cancel_btn = ctk.CTkButton(btn_row, text="取消", width=60, height=26,
                                         font=FONT_UI_SM, fg_color=COLORS["error_dim"], text_color=COLORS["error"],
                                         hover_color="#5C1A1A", command=self._cancel)
        self.cancel_btn.pack(side="right", padx=2)
        self.remove_btn = ctk.CTkButton(btn_row, text="删除", width=60, height=26,
                                         font=FONT_UI_SM, fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                                         hover_color=COLORS["panel_hover"], command=self._remove)
        self.remove_btn.pack(side="right", padx=2)
        self.remove_btn.pack_forget()

        self.refresh()

    def refresh(self):
        t = self.task
        self.status_label.configure(text=STATUS_TEXT.get(t.status, t.status),
                                    text_color=STATUS_COLOR.get(t.status, COLORS["text"]))
        pct = t.progress / 100.0
        if t.status == "completed":
            self.progress.configure(progress_color=COLORS["success"])
        elif t.status == "error":
            self.progress.configure(progress_color=COLORS["error"])
        else:
            self.progress.configure(progress_color=COLORS["accent"])
        self.progress.set(pct)

        parts = []
        if t.output_file:
            parts.append("📄 " + os.path.basename(t.output_file)[:35])
        if t.speed and t.status == "downloading":
            parts.append(t.speed)
        if t.eta and t.status == "downloading":
            parts.append("ETA " + t.eta)
        parts.append(f"{t.progress:.0f}%")
        self.meta_label.configure(text="  ·  ".join(parts))

        is_active = t.status in ("pending", "starting", "downloading", "processing")
        if is_active:
            self.cancel_btn.pack(side="right", padx=2)
            self.remove_btn.pack_forget()
            self.reveal_btn.configure(state="disabled")
        else:
            self.cancel_btn.pack_forget()
            self.remove_btn.pack(side="right", padx=2)
            if t.status == "completed":
                self.reveal_btn.configure(state="normal")

    def _view_log(self):
        self.app.show_task_log(self.task)

    def _cancel(self):
        self.task.cancel = True
        if self.task.proc and self.task.proc.poll() is None:
            try: self.task.proc.terminate()
            except OSError: pass

    def _remove(self):
        self.app.remove_task(self.task)

    def _reveal(self):
        t = self.task
        if t.output_file and os.path.exists(t.output_file):
            subprocess.Popen(["explorer", "/select,", t.output_file],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        elif t.save_dir and os.path.isdir(t.save_dir):
            os.startfile(t.save_dir)


# ============================================================
# 主应用
# ============================================================
class YtDlpApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("yt-dlp 视频下载助手")
        self.geometry("980x740")
        self.minsize(860, 640)
        self.configure(fg_color=COLORS["bg"])

        self.ytdlp = find_ytdlp()
        self.tasks = []
        self.selected_task = None
        self._prefs = self._load_prefs()

        self._build_ui()
        self._update_status_bar()

        if not self.ytdlp:
            messagebox.showwarning("yt-dlp 下载助手", "未找到 yt-dlp.exe，请放到桌面或本程序同目录。")

    def _prefs_path(self):
        return os.path.join(os.path.expanduser("~"), ".ytdlp_gui_prefs.json")

    def _load_prefs(self):
        try:
            with open(self._prefs_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"format": "best", "quality": "1080", "save_dir": "", "first_only": False, "subs": False}

    def _save_prefs(self):
        try:
            with open(self._prefs_path(), "w", encoding="utf-8") as f:
                json.dump(self._prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _build_ui(self):
        topbar = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color=COLORS["surface"],
                               border_color=COLORS["border"], border_width=0)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        title_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        title_frame.pack(side="left", padx=16)
        icon_label = ctk.CTkLabel(title_frame, text="▶", font=("Microsoft YaHei UI", 18, "bold"),
                                   text_color=COLORS["accent"], width=24)
        icon_label.pack(side="left")
        ctk.CTkLabel(title_frame, text="yt-dlp 视频下载助手", font=FONT_TITLE, text_color=COLORS["text"]).pack(side="left", padx=(6, 0))
        ctk.CTkLabel(title_frame, text="桌面版", font=("Microsoft YaHei UI", 9), text_color=COLORS["text_mute"]).pack(side="left", padx=(8, 0))

        pill_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        pill_frame.pack(side="right", padx=16)
        self.yt_pill = self._make_pill(pill_frame, "yt-dlp", bool(self.ytdlp))
        self.yt_pill.pack(side="left", padx=4)
        self.ff_pill = self._make_pill(pill_frame, "FFmpeg", find_ffmpeg() is not None)
        self.ff_pill.pack(side="left", padx=4)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=10)

        self.sidebar = ctk.CTkFrame(body, width=330, corner_radius=12, fg_color=COLORS["surface"],
                                     border_color=COLORS["border"], border_width=1)
        self.sidebar.pack(side="left", fill="y", padx=(0, 10))
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True)

        list_header = ctk.CTkFrame(right, fg_color="transparent", height=36)
        list_header.pack(fill="x", pady=(0, 6))
        list_header.pack_propagate(False)
        ctk.CTkLabel(list_header, text="下载队列", font=("Microsoft YaHei UI", 13, "bold"),
                     text_color=COLORS["text"]).pack(side="left")
        self.task_count_label = ctk.CTkLabel(list_header, text="0", font=("Microsoft YaHei UI", 10),
                                              text_color=COLORS["text_mute"], fg_color=COLORS["panel"],
                                              corner_radius=10, width=28)
        self.task_count_label.pack(side="left", padx=8)
        ctk.CTkButton(list_header, text="清除已完成", width=90, height=28, font=FONT_UI_SM,
                      fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                      hover_color=COLORS["panel_hover"], command=self._clear_completed).pack(side="right")

        self.tasks_scroll = ctk.CTkScrollableFrame(right, fg_color=COLORS["bg"], corner_radius=0)
        self.tasks_scroll.pack(fill="both", expand=True, pady=(0, 8))
        self.tasks_scroll.configure(scrollbar_button_color=COLORS["panel"], scrollbar_button_hover_color=COLORS["border"])

        self.empty_frame = ctk.CTkFrame(self.tasks_scroll, fg_color="transparent")
        self.empty_frame.pack(fill="both", expand=True, pady=60)
        ctk.CTkLabel(self.empty_frame, text="⬇", font=("Microsoft YaHei UI", 36), text_color=COLORS["text_mute"]).pack()
        ctk.CTkLabel(self.empty_frame, text="还没有下载任务", font=("Microsoft YaHei UI", 14, "bold"),
                     text_color=COLORS["text_dim"]).pack(pady=(8, 4))
        ctk.CTkLabel(self.empty_frame, text="在左侧粘贴链接，选择格式后点击开始下载",
                     font=FONT_UI_SM, text_color=COLORS["text_mute"]).pack()

        log_frame = ctk.CTkFrame(right, height=180, corner_radius=10, fg_color=COLORS["log_bg"],
                                  border_color=COLORS["border"], border_width=1)
        log_frame.pack(fill="x")
        log_frame.pack_propagate(False)
        log_header = ctk.CTkFrame(log_frame, fg_color=COLORS["surface"], height=30, corner_radius=0)
        log_header.pack(fill="x")
        log_header.pack_propagate(False)
        self.log_title = ctk.CTkLabel(log_header, text="  运行日志（点击任务卡片的「查看日志」）",
                                       font=("Microsoft YaHei UI", 10, "bold"), text_color=COLORS["text_dim"], anchor="w")
        self.log_title.pack(side="left", fill="x", expand=True)
        self.log_text = ctk.CTkTextbox(log_frame, font=FONT_MONO_SM, fg_color=COLORS["log_bg"],
                                        text_color=COLORS["log_text"], corner_radius=0, border_width=0)
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.log_text.configure(state="disabled")

        self.status_bar = ctk.CTkFrame(self, height=26, corner_radius=0, fg_color=COLORS["surface"])
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.pack_propagate(False)
        self.status_left = ctk.CTkLabel(self.status_bar, text="", font=("Microsoft YaHei UI", 9),
                                         text_color=COLORS["text_mute"], anchor="w")
        self.status_left.pack(side="left", padx=12)
        self.status_right = ctk.CTkLabel(self.status_bar, text="", font=("Microsoft YaHei UI", 9),
                                          text_color=COLORS["text_mute"], anchor="e")
        self.status_right.pack(side="right", padx=12)

    def _make_pill(self, parent, text, ok):
        color = COLORS["success"] if ok else COLORS["error"]
        frame = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=12, height=24)
        frame.pack_propagate(False)
        dot = ctk.CTkLabel(frame, text="●", font=("Microsoft YaHei UI", 8), text_color=color, width=14)
        dot.pack(side="left", padx=(6, 0))
        ctk.CTkLabel(frame, text=text, font=("Microsoft YaHei UI", 9), text_color=COLORS["text_dim"]).pack(side="left", padx=(0, 8))
        return frame

    def _build_sidebar(self):
        pad = {"padx": 14, "pady": 2}

        ctk.CTkLabel(self.sidebar, text="视频链接", font=("Microsoft YaHei UI", 11, "bold"),
                     text_color=COLORS["text"]).pack(anchor="w", **{**pad, "pady": (14, 2)})
        self.url_text = ctk.CTkTextbox(self.sidebar, height=80, font=FONT_MONO_SM,
                                        fg_color=COLORS["bg"], text_color=COLORS["text"],
                                        border_color=COLORS["border"], border_width=1, corner_radius=8)
        self.url_text.pack(fill="x", **pad)
        self.url_text.insert("1.0", "")
        ctk.CTkLabel(self.sidebar, text="支持多个链接（每行一个），可拖拽链接到窗口",
                     font=("Microsoft YaHei UI", 9), text_color=COLORS["text_mute"]).pack(anchor="w", **pad)

        ctk.CTkLabel(self.sidebar, text="下载格式", font=("Microsoft YaHei UI", 11, "bold"),
                     text_color=COLORS["text"]).pack(anchor="w", **{**pad, "pady": (12, 2)})
        fmt_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        fmt_frame.pack(fill="x", **pad)
        self.fmt_buttons = {}
        fmts = [("best", "最高画质"), ("height", "指定清晰度"), ("mp3", "仅音频 MP3")]
        for i, (val, label) in enumerate(fmts):
            btn = ctk.CTkButton(fmt_frame, text=label, font=FONT_UI_SM, height=34,
                                fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                                hover_color=COLORS["panel_hover"], corner_radius=8,
                                command=lambda v=val: self._select_format(v))
            btn.grid(row=0, column=i, sticky="ew", padx=2)
            self.fmt_buttons[val] = btn
        for i in range(3):
            fmt_frame.grid_columnconfigure(i, weight=1)

        adv_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        adv_frame.pack(fill="x", **{**pad, "pady": (10, 2)})
        self.quality_var = ctk.StringVar(value=self._prefs.get("quality", "1080"))
        ctk.CTkLabel(adv_frame, text="清晰度上限", font=FONT_UI_SM, text_color=COLORS["text_dim"]).pack(side="left")
        self.quality_menu = ctk.CTkOptionMenu(adv_frame, values=["2160", "1440", "1080", "720", "480", "360"],
                                                variable=self.quality_var, width=90, height=28, font=FONT_UI_SM,
                                                fg_color=COLORS["panel"], button_color=COLORS["panel_hover"],
                                                button_hover_color=COLORS["border"], text_color=COLORS["text"],
                                                dropdown_fg_color=COLORS["panel"], dropdown_text_color=COLORS["text"])
        self.quality_menu.pack(side="right")

        self.first_only_var = ctk.BooleanVar(value=self._prefs.get("first_only", False))
        ctk.CTkSwitch(self.sidebar, text="播放列表仅下载第一集", font=FONT_UI_SM,
                      text_color=COLORS["text_dim"], fg_color=COLORS["accent"],
                      progress_color=COLORS["accent"], variable=self.first_only_var).pack(anchor="w", **pad)
        self.subs_var = ctk.BooleanVar(value=self._prefs.get("subs", False))
        ctk.CTkSwitch(self.sidebar, text="同时下载字幕", font=FONT_UI_SM,
                      text_color=COLORS["text_dim"], fg_color=COLORS["accent"],
                      progress_color=COLORS["accent"], variable=self.subs_var).pack(anchor="w", **pad)

        ctk.CTkLabel(self.sidebar, text="保存位置", font=("Microsoft YaHei UI", 11, "bold"),
                     text_color=COLORS["text"]).pack(anchor="w", **{**pad, "pady": (12, 2)})
        quick_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        quick_frame.pack(fill="x", **pad)
        for i, (label, key) in enumerate([("下载", "downloads"), ("桌面", "desktop"), ("视频", "videos")]):
            ctk.CTkButton(quick_frame, text=label, font=("Microsoft YaHei UI", 9), height=26,
                          fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                          hover_color=COLORS["panel_hover"], corner_radius=6,
                          command=lambda k=key: self._quick_save(k)).grid(row=0, column=i, sticky="ew", padx=2)
        for i in range(3):
            quick_frame.grid_columnconfigure(i, weight=1)

        self.save_var = ctk.StringVar(value=self._prefs.get("save_dir", ""))
        save_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        save_row.pack(fill="x", **pad)
        self.save_entry = ctk.CTkEntry(save_row, textvariable=self.save_var, font=FONT_MONO_SM,
                                        fg_color=COLORS["bg"], text_color=COLORS["text"],
                                        border_color=COLORS["border"], corner_radius=8, height=32)
        self.save_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(save_row, text="浏览", width=56, height=32, font=FONT_UI_SM,
                      fg_color=COLORS["panel"], text_color=COLORS["text_dim"],
                      hover_color=COLORS["panel_hover"], corner_radius=8,
                      command=self._pick_dir).pack(side="left", padx=(6, 0))

        self.download_btn = ctk.CTkButton(self.sidebar, text="▶  开始下载", font=("Microsoft YaHei UI", 13, "bold"),
                                           height=42, corner_radius=10,
                                           fg_color=COLORS["accent"], text_color="#0B1220",
                                           hover_color="#5BC4F0", command=self.start_download)
        self.download_btn.pack(fill="x", padx=14, pady=(16, 14))

        self._select_format(self._prefs.get("format", "best"))

    def _select_format(self, val):
        self._prefs["format"] = val
        self._save_prefs()
        for k, btn in self.fmt_buttons.items():
            if k == val:
                btn.configure(fg_color=COLORS["accent_dim"], text_color=COLORS["accent"], border_color=COLORS["accent"], border_width=1)
            else:
                btn.configure(fg_color=COLORS["panel"], text_color=COLORS["text_dim"], border_color=COLORS["panel"], border_width=0)

    def _quick_save(self, key):
        home = os.path.expanduser("~")
        mapping = {"downloads": os.path.join(home, "Downloads"), "desktop": os.path.join(home, "Desktop"),
                   "videos": os.path.join(home, "Videos")}
        path = mapping.get(key, "")
        if path:
            self.save_var.set(path)
            self._prefs["save_dir"] = path
            self._save_prefs()

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_var.get() or os.path.expanduser("~"))
        if d:
            self.save_var.set(d)
            self._prefs["save_dir"] = d
            self._save_prefs()

    def start_download(self):
        urls = [u.strip() for u in self.url_text.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showinfo("提示", "请先粘贴视频链接。")
            return
        if not self.ytdlp:
            messagebox.showwarning("提示", "未找到 yt-dlp.exe。")
            return

        opts = {
            "format": self._prefs.get("format", "best"),
            "quality": self.quality_var.get(),
            "first_only": self.first_only_var.get(),
            "subs": self.subs_var.get(),
        }
        save_dir = self.save_var.get().strip()
        if save_dir and not os.path.isdir(save_dir):
            try: os.makedirs(save_dir, exist_ok=True)
            except OSError as e:
                messagebox.showerror("错误", f"无法创建保存文件夹：\n{e}")
                return

        self._prefs.update({"quality": opts["quality"], "first_only": opts["first_only"],
                             "subs": opts["subs"], "save_dir": save_dir})
        self._save_prefs()

        for url in urls:
            task = DownloadTask(url, opts, save_dir)
            self.tasks.append(task)
            card = TaskCard(self.tasks_scroll, task, self)
            card.pack(fill="x", pady=4)
            t = threading.Thread(target=task.run, args=(self.ytdlp, self._on_task_update), daemon=True)
            t.start()

        self.url_text.delete("1.0", "end")
        self.empty_frame.pack_forget()
        self._update_status_bar()

    def _on_task_update(self, task):
        self.after(0, lambda: self._refresh_task(task))

    def _refresh_task(self, task):
        if task.card:
            task.card.refresh()
        self._update_status_bar()

    def remove_task(self, task):
        if task.card:
            task.card.destroy()
            task.card = None
        if task in self.tasks:
            self.tasks.remove(task)
        if self.selected_task == task:
            self.selected_task = None
            self.log_title.configure(text="  运行日志")
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")
        if not self.tasks:
            self.empty_frame.pack(fill="both", expand=True, pady=60)
        self._update_status_bar()

    def _clear_completed(self):
        to_remove = [t for t in self.tasks if t.status in ("completed", "error", "cancelled")]
        for t in to_remove:
            self.remove_task(t)

    def show_task_log(self, task):
        self.selected_task = task
        title = task.url[:50] + ("..." if len(task.url) > 50 else "")
        self.log_title.configure(text=f"  日志 — {title}")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", "\n".join(task.log[-200:]))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self._poll_log()

    def _poll_log(self):
        if self.selected_task and self.selected_task.status in ("pending", "starting", "downloading", "processing"):
            task = self.selected_task
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("1.0", "\n".join(task.log[-200:]))
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
            self.after(500, self._poll_log)

    def _update_status_bar(self):
        total = len(self.tasks)
        active = sum(1 for t in self.tasks if t.status in ("pending", "starting", "downloading", "processing"))
        done = sum(1 for t in self.tasks if t.status == "completed")
        errors = sum(1 for t in self.tasks if t.status == "error")
        self.task_count_label.configure(text=str(total))
        self.status_left.configure(text=f"共 {total} 个任务 · 进行中 {active} · 已完成 {done} · 失败 {errors}")
        ytdlp_name = os.path.basename(self.ytdlp) if self.ytdlp else "未找到"
        self.status_right.configure(text=f"yt-dlp: {ytdlp_name}")


def main():
    app = YtDlpApp()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except tk.TclError:
        sys.exit(1)

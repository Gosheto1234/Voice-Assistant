import os
import sys
import json
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import ttk, Toplevel
import speech_recognition as sr
from PIL import Image, ImageTk, ImageSequence

# ——— Version Handling & Update Checker ———
try:
    from version_info import __version__
except ImportError:
    __version__ = "0.0.0"
    try:
        ver_path = os.path.join(
            os.path.dirname(sys.executable if getattr(sys, "frozen", False) else __file__),
            "version.json"
        )
        with open(ver_path, "r", encoding="utf-8") as vf:
            __version__ = json.load(vf).get("version", __version__)
    except Exception:
        pass

VERSION_JSON_URL = "https://raw.githubusercontent.com/Gosheto1234/Voice-Assistant/main/version.json"
UPDATE_ZIP_PATH = "update.zip"

# ——— Logging Setup ———
LOG_PATH = os.path.join(os.getcwd(), "assistant.log")
logger = logging.getLogger("VA")
logger.setLevel(logging.DEBUG)
file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# ——— Persistence Helpers ———
def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# Settings paths
BASE_DIR = os.path.dirname(__file__)
SETTINGS = {
    'apps_db': os.path.join(BASE_DIR, 'apps.json'),
    'selected_mic': os.path.join(BASE_DIR, 'selected_mic.json'),
    'themes': os.path.join(BASE_DIR, 'themes.json'),
    'selected_theme': os.path.join(BASE_DIR, 'selected_theme.json'),
    'media_cfg': os.path.join(BASE_DIR, 'media_players.json'),
}

# ——— Theme Management ———

def load_themes():
    data = load_json(SETTINGS['themes'], {}) or {}
    if not data:
        default = {
            "sakura": {"bg":"#ffeef2","fg":"#5c2a2a","button_bg":"#f7cad0","button_fg":"#5c2a2a"},
            "Dark": {"bg":"#000","fg":"#fff","button_bg":"#333","button_fg":"#fff"},
        }
        save_json(SETTINGS['themes'], default)
        return default
    return data

# ——— UI Feedback & Logging ———
log_widget = None
status_label = None
feedback_frame = None

def ui_log(message, level="info"):
    getattr(logger, level)(message)
    if log_widget:
        log_widget.insert(tk.END, message + "\n")
        log_widget.see(tk.END)

def show_feedback(message):
    if feedback_frame:
        for w in feedback_frame.winfo_children(): w.destroy()
        tk.Label(feedback_frame, text=message, anchor="w").pack(fill=tk.X)

# ——— Core Logic Placeholders ———

# TODO: Initialize apps database (learn_apps, load/save)
# TODO: Initialize media players, music database
# TODO: Define command handlers (open, close, media, discord, custom intents)
# TODO: Speech recognition and execution logic

# ——— UI Construction ———
def open_settings():
    win = Toplevel(main_root)
    win.title("Settings")
    # TODO: Microphone selection combobox
    # TODO: Theme selection combobox
    # TODO: Apply button


def build_ui():
    global main_root, log_widget, status_label, feedback_frame
    main_root = tk.Tk()
    main_root.title("Voice Assistant")
    main_root.geometry("400x300")

    # Version Label
    version_label = tk.Label(main_root, text=f"Version: {__version__}")
    version_label.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)

    # Animation / Main Canvas
    animation_canvas = tk.Canvas(main_root)
    animation_canvas.pack(fill=tk.BOTH, expand=True)

    # Status and Feedback
    status_label = tk.Label(main_root, text="Idle")
    status_label.place(relx=0.01, rely=0.01, anchor="nw")
    feedback_frame = tk.Frame(main_root)
    feedback_frame.pack(side=tk.BOTTOM, fill=tk.X)

    # Controls
    button_frame = tk.Frame(main_root)
    button_frame.pack(side=tk.BOTTOM, pady=5)
    tk.Button(button_frame, text="Start", width=10, command=lambda: ui_log("Start pressed")).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Stop", width=10, command=lambda: ui_log("Stop pressed")).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Update", width=10, command=lambda: ui_log("Update pressed")).pack(side=tk.LEFT, padx=5)
    tk.Button(main_root, text="⚙️", width=4, command=open_settings).place(relx=1.0, x=-10, y=10, anchor="ne")

    # Log Widget
    log_widget = tk.scrolledtext.ScrolledText(main_root, height=5)
    log_widget.pack(side=tk.BOTTOM, fill=tk.X)

    # TODO: AnimatedDog setup

    return main_root

if __name__ == '__main__':
    # TODO: Check for update on startup
    music_db = {}  # TODO: build music DB
    app = build_ui()
    app.mainloop()

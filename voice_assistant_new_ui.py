import os
import sys
import json
import glob
import threading
import subprocess
import logging
from logging.handlers import RotatingFileHandler
import random
import time
import requests
import re



import tkinter as tk
from tkinter import ttk, scrolledtext, Toplevel, PanedWindow

import speech_recognition as sr
import pyautogui
import psutil
import pygetwindow as gw
from PIL import Image, ImageTk, ImageSequence
import win32gui
import win32con
import win32process
import difflib
import zipfile
import tkinter as tk
import tkinter.messagebox as mb


# ——— Configuration & Globals ———
LOG_PATH = os.path.join(os.getcwd(), "assistant.log")
APPS_DB_PATH = os.path.join(os.path.dirname(__file__), "apps.json")
SELECTED_MIC_PATH = os.path.join(os.path.dirname(__file__), "selected_mic.json")
THEMES_PATH = os.path.join(os.path.dirname(__file__), "themes.json")
SELECTED_THEME_PATH = os.path.join(os.path.dirname(__file__), "selected_theme.json")
MEDIA_CFG_PATH = os.path.join(os.path.dirname(__file__), "media_players.json")
USER_DESKTOP    = os.path.join(os.path.expanduser("~"), "Desktop")
MUSIC_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.ogg', '.m4a')

recognizer = sr.Recognizer()
microphones = []
selected_mic = None
log_widget = None
keep_listening = False
apps_db = {}
main_root = None
status_label = None
music_db = {}



# App version
__version__ = "0.0.0"

#update stuff
VERSION_JSON_URL = "https://raw.githubusercontent.com/Gosheto1234/Voice-Assistant/main/version.json"
UPDATE_ZIP_PATH = "update.zip"

# Only Status/Feedback panel
feedback_frame = None

# ——— Logging Setup ———
logger = logging.getLogger("VA")
logger.setLevel(logging.DEBUG)
file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # or '3' for errors only

def handle_exc(t, v, tb):
    if issubclass(t, KeyboardInterrupt):
        return
    logger.error("Uncaught Exception", exc_info=(t, v, tb))
sys.excepthook = handle_exc

# ——— Persistence Helpers ———
def load_json(path, default=None):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_selected_theme():
    data = load_json(SELECTED_THEME_PATH, default={}) or {}
    return data.get("theme", "Dark")    # fallback to Dark

def save_selected_theme(theme_name):
    save_json(SELECTED_THEME_PATH, {"theme": theme_name})

def enum_windows_callback(hwnd, window_list):
    if win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):  # Includes minimized
        tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        window_list.append((hwnd, pid, win32gui.GetWindowText(hwnd)))

def initialize_apps_db():
    """Scan for installed apps only if no cache exists."""
    global apps_db
    if not os.path.exists(APPS_DB_PATH) or os.path.getsize(APPS_DB_PATH) == 0:
        ui_log("apps.json not found or empty — learning apps…", "info")
        learn_apps()
    else:
        apps_db = load_json(APPS_DB_PATH, default={}) or {}
        ui_log(f"Loaded {len(apps_db)} apps from cache", "info")

def load_media_players():
    data = load_json(MEDIA_CFG_PATH, default={}) or {}
    available = {}
    for name, info in data.items():
        exe = info["exe"].lower()
        # check apps_db for an .exe or .lnk
        if any(exe in path.lower() for path in apps_db.values()):
            available[name] = info
    return available

media_players = load_media_players()


def build_music_db():
    """Scan the user’s Desktop (recursively) for music files."""
    db = {}
    for ext in MUSIC_EXTENSIONS:
        pattern = os.path.join(USER_DESKTOP, '**', f'*{ext}')
        for path in glob.glob(pattern, recursive=True):
            name = os.path.splitext(os.path.basename(path))[0].lower()
            db[name] = path
    return db
    

#App update check

def get_local_version():
    return __version__



def version_tuple(v):
    return tuple(map(int, re.sub("[^0-9.]", "", v).split(".")))



def query_update():
    GITHUB_API = "https://api.github.com/repos/Gosheto1234/Voice-Assistant/releases/latest"
    resp = requests.get(GITHUB_API)
    resp.raise_for_status()
    data = resp.json()

    remote = data.get("tag_name", "").lstrip("v")
    local  = get_local_version()
    if version_tuple(remote) <= version_tuple(local):
        return None

    # find the VoiceAssistant.exe asset
    download_url = None
    for asset in data["assets"]:
        if asset["name"].lower() == "voiceassistant.exe":
            download_url = asset["browser_download_url"]
            break

    if not download_url:
        mb.showerror("Update Error", "Could not find VoiceAssistant.exe on GitHub.")
        return None

    changelog = data.get("body", "")
    return remote, download_url, changelog


def perform_update(download_url):
    """
    1) Download the new exe as a temp file.
    2) Launch updater.exe to delete the old exe, move the new one into place,
       and restart the app.
    """
    temp_name = "VoiceAssistant_new.exe"
    try:
        r = requests.get(download_url)
        r.raise_for_status()
        with open(temp_name, "wb") as f:
            f.write(r.content)
    except Exception as e:
        mb.showerror("Update Error", f"Download failed:\n{e}")
        return

    # locate the updater stub shipped alongside your main exe
    updater_path = resource_path("updater.exe")
    if not os.path.exists(updater_path):
        mb.showerror("Update Error", f"Cannot find updater.exe at:\n{updater_path}")
        return

    # call updater.exe <new> <old>
    old_exe = sys.argv[0]
    subprocess.Popen([updater_path, temp_name, old_exe], close_fds=True)

    # tear down this instance
    try:
        if main_root:
            main_root.destroy()
    except:
        pass
    os._exit(0)

def on_update_click():
    """
    Handler for the Update button: query, prompt, then perform.
    """
    info = query_update()
    if info is None:
        mb.showinfo("No Update", "You’re already on the latest version.")
        return

    remote, url, changelog = info
    msg = f"Version {remote} is available.\n\nChangelog:\n{changelog}\n\nInstall now?"
    if mb.askyesno("Update Available", msg):
        perform_update(url)



def resource_path(relative_path):
    """
    Return the absolute path to a bundled resource, whether running
    as a script or in a PyInstaller one-file executable.
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller bundles files here
        base_path = sys._MEIPASS
    else:
        # Running in development
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)




# ——— Win32 Helpers for Enumerating & Activating Windows ———
def find_app_window(app_name):
    """Return the HWND of a top-level window whose process name contains app_name."""
    windows = []
    def enum_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            tid, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid)
                if app_name.lower() in proc.name().lower():
                    windows.append(hwnd)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    win32gui.EnumWindows(enum_callback, None)
    return windows[0] if windows else None

def activate_window(hwnd):
    """Maximize (if needed) and bring the given HWND to the foreground."""
    if not hwnd:
        return False

    # First restore in case it’s minimized, then maximize
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    win32gui.SetForegroundWindow(hwnd)
    return True

def find_media_player_via_title():
    """Return HWND of any window whose title contains 'Media Player'."""
    hwnds = []
    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd) or ""
            if "media player" in title.lower():
                hwnds.append(hwnd)
    win32gui.EnumWindows(_cb, None)
    return hwnds[0] if hwnds else None

# ——— Theme Management ———
def load_themes():
    """Load themes.json (create it with defaults if missing)."""
    if not os.path.exists(THEMES_PATH):
        default = {
            "sakura": {
                "bg": "#ffeef2",
                "fg": "#5c2a2a",
                "button_bg": "#f7cad0",
                "button_fg": "#5c2a2a"
            },
            "Dark": {
                "bg": "#000000",      # true black background
                "fg": "#ffffff",      # white text
                "button_bg": "#333333",
                "button_fg": "#ffffff",
                "module": "themes.darkmode"
            }
        }
        save_json(THEMES_PATH, default)
        return default
    return load_json(THEMES_PATH, {}) or {}

def apply_theme(root, theme):
    try:
        # accept both sets of key names
        bg          = theme.get("bg",          theme.get("background",   "#ffffff"))
        fg          = theme.get("fg",          theme.get("foreground",   "#000000"))
        button_bg   = theme.get("button_bg",   theme.get("bg",           bg))
        button_fg   = theme.get("button_fg",   theme.get("fg",           fg))

        root.configure(bg=bg)

        def recurse(w):
            cls = w.__class__.__name__
            if cls in ("Frame", "LabelFrame", "PanedWindow", "Toplevel"):
                w.configure(bg=bg)
            elif cls == "Label":
                w.configure(bg=bg, fg=fg)
            elif cls == "Button":
                w.configure(bg=button_bg, fg=button_fg)
            elif cls in ("Text", "ScrolledText"):
                w.configure(bg=bg, fg=fg, insertbackground=fg)
            elif cls == "Combobox":
                w.configure(background=bg, foreground=fg)
            for c in w.winfo_children():
                recurse(c)

        recurse(root)
        ui_log(f"Applied theme BG={bg} FG={fg}", "info")

    except Exception as e:
        ui_log(f"Theme apply failed: {e}", "error")


# ——— Apps DB ———
def initialize_apps_db():
    """On startup: if apps.json is missing or empty, scan; otherwise just load."""
    global apps_db
    if not os.path.exists(APPS_DB_PATH) or os.path.getsize(APPS_DB_PATH) == 0:
        ui_log("apps.json not found or empty — learning apps…", "info")
        learn_apps()
    else:
        apps_db = load_json(APPS_DB_PATH, default={}) or {}
        ui_log(f"Loaded {len(apps_db)} apps from cache", "info")
def save_apps_db():
    save_json(APPS_DB_PATH, apps_db)

def learn_apps():
    found = {}
    for rd in (os.environ.get("ProgramFiles",""), os.environ.get("ProgramFiles(x86)","")):
        for exe in glob.glob(os.path.join(rd, "**", "*.exe"), recursive=True):
            name = os.path.splitext(os.path.basename(exe))[0].lower()
            found[name] = exe
    sm = os.path.join(os.environ.get("APPDATA",""), r"Microsoft\Windows\Start Menu\Programs")
    for lnk in glob.glob(os.path.join(sm, "**", "*.lnk"), recursive=True):
        name = os.path.splitext(os.path.basename(lnk))[0].lower()
        found[name] = lnk
    apps_db.clear()
    apps_db.update(found)
    save_apps_db()
    ui_log(f"Learned {len(apps_db)} apps", "info")

# ——— Mic Management ———
def load_selected_mic():
    global selected_mic
    data = load_json(SELECTED_MIC_PATH, default={}) or {}
    idx = data.get("selected_mic", 0)
    if idx < 0 or idx >= len(microphones):
        idx = 0  # fallback
        ui_log("Mic index out of range, reset to 0", "warning")
    selected_mic.set(idx)
    ui_log("Loaded selected mic", "info")

def save_selected_mic():
    save_json(SELECTED_MIC_PATH, {"selected_mic": selected_mic.get()})
    ui_log("Saved selected mic", "info")

# ——— Media ———
def send_media(key):
    try:
        pyautogui.press(key)
        ui_log(f"Media:{key}", "info")
    except Exception as e:
        ui_log(f"Media failed:{e}", "error")

# ——— Window ———
def focus_app_window(name):
    hwnd = find_app_window(name)
    if hwnd and activate_window(hwnd):
        return True
    return False






# ——— Command Handlers ———
def is_process_running(name):
    """Check if a process with the given name is already running."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if name.lower() in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False

# 2. Handle opening the application with threading
def handle_open(args):
    def open_thread():
        # Build the spoken name
        name = " ".join(args).lower()

        # 1) Try exact lookup in apps_db
        path = apps_db.get(name)

        # 2) Fuzzy‐match fallback if not found
        if not path:
            keys = list(apps_db.keys())
            match = difflib.get_close_matches(name, keys, n=1, cutoff=0.6)
            if match:
                chosen = match[0]
                ui_log(f"Did you mean '{chosen}'? Using that.", "info")
                path = apps_db[chosen]
                name = chosen  # switch to matched key

        # 3) If still no path, abort
        if not path:
            ui_log(f"Unknown app: {name}", "warning")
            return

        # 4) If process already running, just focus it
        if is_process_running(name):
            ui_log(f"{name} already running; focusing…", "info")
            if focus_app_window(name):
                # Special Discord hook
                if name == "discord":
                    ui_log("Discord focused, ready for mute/deafen commands", "info")
            else:
                ui_log(f"Couldn’t find window for {name}", "error")

        # 5) Otherwise, launch then focus
        else:
            try:
                if path.lower().endswith('.lnk'):
                    os.startfile(path)
                else:
                    subprocess.Popen(path, shell=True)
                ui_log(f"Opened {name}", "info")

                # Give the app time to initialize, then focus and maximize
                time.sleep(2)
                if focus_app_window(name):
                    # Discord hook again
                    if name == "discord":
                        ui_log("Discord focused, ready for mute/deafen commands", "info")
                else:
                    ui_log(f"Launched {name} but couldn’t focus window", "warning")
            except Exception as e:
                ui_log(f"Open failed: {e}", "error")

    # Fire off in background thread so UI stays responsive
    threading.Thread(target=open_thread, daemon=True).start()




# 4. Handle closing the application with threading
def handle_close(args):
    def close_thread():
        nm = " ".join(args)
        exe = nm + ".exe"
        try:
            subprocess.call(["taskkill", "/f", "/im", exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ui_log(f"Closed {nm}", "info")
        except Exception as e:
            ui_log(f"Close failed: {e}", "error")
    
    # Create and start the thread for closing the app
    threading.Thread(target=close_thread, daemon=True).start()

    

# ——— Core Execution ———
def execute_command(text):
    show_feedback(f"Processing: {text}")
    cmd = text.lower().split()
    
    if not cmd: return

    # Command to relearn apps
    if cmd[0] in ("learn", "learn apps"):
        learn_apps()
        show_feedback("Apps relearned")
        return

    # Open application command
    if cmd[0] == "open":
        handle_open(cmd[1:])
        show_feedback(f"Opened {cmd[1]}")
        return


    # Close application command
    if cmd[0] == "close":
        handle_close(cmd[1:])
        show_feedback(f"Closed {cmd[1]}")
        return

# ——— Localized keyword mappings ———
# English → BG
command_map = {
    "open":    ["open", "стартирай", "отвори"],
    "close":   ["close", "затвори", "спри"],
}
media_map = {
    "play":        ["play", "start", "resume", "пусни", "проиграй"],
    "pause":       ["pause", "stop", "пауза", "пауза музика", "спри музика"],
    "next":        ["next", "skip", "следващ", "прескочи"],
    "previous":    ["previous", "prev", "назад", "предишен"],
    "volume up":   ["volume up", "increase volume", "увеличи звук", "гласно"],
    "volume down": ["volume down", "decrease volume", "намали звук", "по-тихо"],
}
discord_map = {
    "mute":     ["mute", "микрофон изключен", "изключи микрофона", "заглуши"],
    "unmute":   ["unmute", "включи микрофона", "отглуши"],
    "deafen":   ["deafen", "глух", "деафен", "слушалки"],
    "undeafen": ["undeafen", "отдеафен"],
}


# Helper function to check if Spotify (or another player) is running
def get_current_player():
    """
    Try process-based detection first (using media_players.json → exe),
    then fall back to window-title search for UWP Media Player.
    Returns (name, info, hwnd) or None.
    """
    # 1) check known exes
    for name, info in media_players.items():
        exe = info["exe"].lower()
        for proc in psutil.process_iter(["name"]):
            if proc.info["name"].lower() == exe:
                # find its window
                hwnd = find_app_window(name) or None
                return name, info, hwnd

    # 2) fallback for UWP-style “Media Player”
    hwnd = find_media_player_via_title()
    if hwnd:
        # look up its info from the JSON config
        info = media_players.get("Media Player")
        if info:
            return "Media Player (UWP)", info, hwnd
    return None

def ensure_player_running(player_name, exe):
    """Launch the player if it’s installed but not running."""
    if not any(p.name().lower() == exe.lower() for p in psutil.process_iter()):
        path = apps_db.get(player_name.lower())
        if path:
            os.startfile(path)
            time.sleep(2)  # give it a moment to spin up

# Function to control the media player (for example, Spotify or VLC)
def send_media_action(key):
    try:
        pyautogui.press(key)  # Send a key press (space, next track, etc.)
        ui_log(f"Sent media action: {key}", "info")
    except Exception as e:
        ui_log(f"Media control failed: {e}", "error")

# Updated command handler with better media control
# ——— Core Execution ———
def execute_command(text):
    show_feedback(f"Processing: {text}")
    lower = text.lower()
    cmd = lower.split()

    if not cmd:
        return

    # ——— Relearn apps ———
    if cmd[0] in ("learn", "learn apps"):
        learn_apps()
        show_feedback("Apps relearned")
        return

    # ——— Open / Close Application ———
    for action, keywords in command_map.items():
        if cmd[0] in keywords:
            args = cmd[1:]
            if action == "open":
                handle_open(args)
                show_feedback(f"Отворих: {' '.join(args)}")
            elif action == "close":
                handle_close(args)
                show_feedback(f"Затворих: {' '.join(args)}")
            return

    # ——— Play File ———
    if cmd[0] == "play" and cmd[1] == "file":
        song_query = " ".join(cmd[2:]).lower()
        match = None
        for name, path in music_db.items():
            if song_query in name:
                match = path
                break
        if match:
            os.startfile(match)
            show_feedback(f"Playing: {os.path.basename(match)}")
        else:
            show_feedback("Song not found.")
        return
    if cmd[0] == "play" and cmd[1] == "file":
        song_query = " ".join(cmd[2:]).lower()
        match = None
        for name, path in music_db.items():
            if song_query in name:
                match = path
                break
        if match:
            os.startfile(match)
            show_feedback(f"Playing: {os.path.basename(match)}")
        else:
            show_feedback("Song not found.")
        return
    # ——— Media control ———
    for action, keywords in media_map.items():
        if any(k in lower for k in keywords):
            # 1) See if any known player is already running
            current = get_current_player()

            # 2) If none running, pick the first installed and launch it
            if not current:
                try:
                    player_name, info = next(iter(media_players.items()))
                    ensure_player_running(player_name, info["exe"])
                    current = (player_name, info)
                except StopIteration:
                    current = None

            # 3) Still none? bail out
            if not current:
                ui_log("No media player found", "warning")
                show_feedback("Няма медия плейър")
                return

            # 4) Send the right hotkey for this action
            name, info, hwnd = current  # now get the HWND, too
            key = info["keys"].get(action)
            if key:
                if hwnd:
                    activate_window(hwnd)
                    time.sleep(0.1)

                show_feedback(f"{name}: {action}")
            else:
                ui_log(f"No key mapping for {action} in {name}", "warning")
                show_feedback(f"{name} не поддържа {action}")
            return

    # ——— Discord voice control ———
    for action, keywords in discord_map.items():
        if any(k in lower for k in keywords):
            if not focus_app_window("discord"):
                ui_log("Discord not running or not found", "warning")
                show_feedback("Discord не е отворен")
                return
            if action in ("mute", "unmute"):
                pyautogui.hotkey("ctrl", "shift", "m")
            else:
                pyautogui.hotkey("ctrl", "shift", "d")
            ui_log(f"Discord: {action}", "info")
            show_feedback(f"Discord: {action}")
            return

    # ——— Fallback ———
    ui_log(f"No action for: {text}", "warning")
    show_feedback("Няма действие")



# ——— Listening ———
def listen_once():
    idx=selected_mic.get()
    ui_log(f"Mic idx {idx}","debug")
    if idx < 0 or idx >= len(microphones):
        ui_log("Invalid mic index", "error")
        return
    try:
        with sr.Microphone(device_index=idx) as src:
            recognizer.adjust_for_ambient_noise(src, 0.5)
            ui_log("Listening…","debug")
            audio = recognizer.listen(src, timeout=2, phrase_time_limit=10)
    except Exception as e:
        ui_log(f"Mic error:{e}","error")
        return
    try:
        txt = recognizer.recognize_google(audio, language="bg-BG")
        ui_log(f"Heard: {txt}", "info")
        execute_command(txt)
    except sr.UnknownValueError:
        ui_log("No understand", "warning")
        show_feedback("…")
    except sr.RequestError as e:
        ui_log(f"Rec error:{e}", "error")
        show_feedback("Error")

def listen_loop():
    global keep_listening
    while keep_listening:
        listen_once()

def start_listening():
    global keep_listening, is_processing
    is_processing = True
    keep_listening = True  # Enable continuous listening
    update_status("Listening...")

    # Run listen_loop in a separate thread so it doesn't block the UI
    threading.Thread(target=listen_loop, daemon=True).start()

def stop_listening():
    global keep_listening, is_processing
    keep_listening = False  # Stop the listening loop
    is_processing = False
    update_status("Idle")
    ui_log("Listening stopped.", "info")
# ——— UI ———
def ui_log(msg, level="info"):
    getattr(logger, level)(msg)
    if log_widget:
        log_widget.insert(tk.END, msg+"\n")
        log_widget.see(tk.END)

def show_feedback(msg):
    if feedback_frame is None:
        print(f"Feedback skipped (UI not ready): {msg}")
        return

    for w in feedback_frame.winfo_children():
        w.destroy()
    tk.Label(feedback_frame, text=msg, anchor="w").pack(fill=tk.X)

def update_status(message):
    if status_label:
        status_label.config(text=message)
        status_label.update_idletasks()

def open_mic_selection():
    global main_root
    win=Toplevel(main_root)
    win.title("Settings")
    win.geometry("300x200")

    tk.Label(win, text="Microphone").pack(pady=5)
    combo=ttk.Combobox(win, values=microphones, state="readonly", width=30)
    combo.current(selected_mic.get())
    combo.pack(pady=5)
    combo.bind("<<ComboboxSelected>>", lambda e: selected_mic.set(combo.current()))

    themes=load_themes()
    names=list(themes.keys())
    current_theme = tk.StringVar(value=names[0])
    tk.Label(win, text="Theme").pack(pady=5)
    tcombo = ttk.Combobox(win, values=names, state="readonly", width=30, textvariable=current_theme)
    tcombo.pack(pady=5)

    def apply_changes():
        save_selected_mic()
        sel = current_theme.get()
        theme = themes[sel]
        apply_theme(main_root, theme)
        save_selected_theme(sel)
        # persist the selection
        save_selected_theme(sel)
        modname = theme.get("module")
        if modname:
            try:
               import importlib
               m = importlib.import_module(modname)
               if hasattr(m, "apply_animation"):
                   m.apply_animation(main_root)
                   ui_log(f"Anim from {modname}", "info")
            except Exception as e:
                ui_log(f"Anim load fail:{e}", "error")
        win.destroy()


       

    tk.Button(win, text="Apply", command=apply_changes).pack(pady=10)

def on_update_click():
    info = query_update()
    if not info:
        mb.showinfo("No Update", "You’re already on the latest version!")
        return

    remote, url, changelog = info
    if mb.askyesno("Update Available",
                   f"Version {remote} is available.\n\nChangelog:\n{changelog}\n\nInstall now?"):
        perform_update(url)


def build_ui():
    global main_root, microphones, selected_mic

    class AnimatedDog:
        def __init__(self, canvas, gif_path, bowl_x, bowl_y, bowl_radius, food_text):
            self.canvas = canvas
            self.bowl_x = bowl_x
            self.bowl_y = bowl_y
            self.bowl_radius = bowl_radius
            self.food_text = food_text

            # Bowl state
            self.bowl_fullness = 100  # 0–100
            threading.Thread(target=self._bowl_refill_loop, daemon=True).start()

            # Load animation frames
            self.frames = [
                ImageTk.PhotoImage(frame.resize((48, 48), Image.Resampling.LANCZOS))
                for frame in ImageSequence.Iterator(Image.open(gif_path))
            ]
            self.frame_idx = 0
            self.sprite = canvas.create_image(10, 10, image=self.frames[0], anchor="nw")

            # Movement target and pacing
            self.target = self._choose_new_target()
            self.step_size = 2
            self.anim_interval = 200  # ms
            self.move_interval = 100  # ms

            # Start loops
            self._schedule_animation()
            self._schedule_movement()

        def _bowl_refill_loop(self):
            while True:
                time.sleep(60)  # every minute
                self.bowl_fullness = 100
                # green outline
                self.canvas.itemconfig(self.bowl_id, outline="green", width=3)

        def _choose_new_target(self):
            w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
            return (
                random.randint(0, max(0, w - 48)),
                random.randint(0, max(0, h - 48))
            )

        def _schedule_animation(self):
            if not is_processing:
                self.frame_idx = (self.frame_idx + 1) % len(self.frames)
                self.canvas.itemconfig(self.sprite, image=self.frames[self.frame_idx])
            main_root.after(self.anim_interval, self._schedule_animation)

        def _schedule_movement(self):
            if not is_processing:
                cx, cy = self.canvas.coords(self.sprite)
                tx, ty = self.target
                dx, dy = tx - cx, ty - cy
                dist = (dx*dx + dy*dy) ** 0.5

                # if near bowl
                if dist < self.step_size and abs(cx - self.bowl_x) < self.bowl_radius and abs(cy - self.bowl_y) < self.bowl_radius:
                    if self.bowl_fullness > 0:
                        self.eat()
                    self.target = self._choose_new_target()
                elif dist < self.step_size:
                    self.target = self._choose_new_target()
                else:
                    nx = cx + dx/dist * self.step_size
                    ny = cy + dy/dist * self.step_size
                    self.canvas.coords(self.sprite, nx, ny)
            main_root.after(self.move_interval, self._schedule_movement)

        def eat(self):
            # empty bowl
            self.bowl_fullness = 0
            self.canvas.itemconfig(self.bowl_id, outline="red", width=3)

            # happy flicker
            orig_anim = self.anim_interval
            def fast_flicker(count=[0]):
                self.frame_idx = (self.frame_idx + 1) % len(self.frames)
                self.canvas.itemconfig(self.sprite, image=self.frames[self.frame_idx])
                count[0] += 1
                if count[0] < 10:
                    main_root.after(50, fast_flicker)
                else:
                    self.anim_interval = orig_anim
            fast_flicker()

            # treat emoji
            treat = tk.Label(main_root, text="🍖", font=("Arial", 24), bg="black")
            treat.place(x=self.bowl_x, y=self.bowl_y - 50)
            main_root.after(1000, treat.destroy)

    # Start UI
    main_root = tk.Tk()
    version_label = tk.Label(main_root, text=f"Version: {__version__}", bg="black", fg="white")
    version_label.place(relx=1.0, rely=0.0, anchor="ne", x=-10, y=10)
    root = main_root
    root.title("Voice Assistant")
    root.geometry("400x300")
    root.resizable(True, True)

    is_processing = False  # pause animations & movement while processing

    # Theme + mic/apps
    themes = load_themes()
    chosen_theme = themes.get(load_selected_theme(), themes["Dark"])
    selected_mic = tk.IntVar(value=0)
    microphones = sr.Microphone.list_microphone_names()
    load_selected_mic()
    initialize_apps_db()

    # Animation canvas
    animation_canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    animation_canvas.pack(fill=tk.BOTH, expand=True)

    # Bowl (with outline id)
    bowl_x = random.randint(150, 350)
    bowl_y = random.randint(150, 250)
    bowl_radius = 20
    bowl_id = animation_canvas.create_oval(
        bowl_x - bowl_radius, bowl_y - bowl_radius,
        bowl_x + bowl_radius, bowl_y + bowl_radius,
        fill="brown", outline="green", width=3
    )

    # Status & feedback
    status_label = tk.Label(root, text="Idle", font=("Helvetica", 12), bg="black", fg="white")
    status_label.place(relx=0.01, rely=0.01, anchor="nw")
    food_text = tk.Label(root, text="Food!", font=("Helvetica", 24, "bold"), fg="green", bg="black")
    food_text.place(x=-100, y=-100)

    # Controls
    button_frame = tk.Frame(root, bg=chosen_theme["bg"])
    button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
    tk.Button(button_frame, text="Start", command=start_listening, width=10).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Stop",  command=stop_listening,  width=10).pack(side=tk.LEFT, padx=5)
    tk.Button(button_frame, text="Update", command=on_update_click, width=10).pack(side=tk.LEFT, padx=5)
    gear = tk.Button(root, text="⚙️", command=open_mic_selection, width=4)
    gear.place(relx=1.0, x=-10, y=10, anchor="ne")

    # Dog instance
    gif_path = resource_path("annoying_dog.gif")
    dog = AnimatedDog(animation_canvas, gif_path, bowl_x, bowl_y, bowl_radius, food_text)
    dog.bowl_id = bowl_id

    # Apply theme & finalize
    apply_theme(root, chosen_theme)
    ui_log("Ready.", "info")
    update_status("Ready")
    return root




if __name__ == "__main__":
    # 1) First, optionally check for updates on startup
    #    (uses the same query/perform logic as the Update button)
    info = query_update()
    if info:
        remote, url, changelog = info
        if mb.askyesno("Update Available",
                       f"Version {remote} is available.\n\nChangelog:\n{changelog}\n\nInstall now?"):
            perform_update(url)

    # 2) Now, if we just came through an update, let the user know
    if os.path.exists("just_updated.flag"):
        try:
            mb.showinfo("Updated", f"Application updated to {__version__}!")
        finally:
            os.remove("just_updated.flag")

    # 3) Build and run the UI
    music_db = build_music_db()
    ui_log(f"Found {len(music_db)} music files on Desktop", "info")
    app = build_ui()
    if app:
        app.mainloop()

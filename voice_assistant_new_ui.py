import os
import sys
import json
import threading
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import ttk, Toplevel, messagebox as mb, filedialog
import speech_recognition as sr
from pathlib import Path
from PIL import Image, ImageTk, ImageSequence
import subprocess
import difflib
import winreg
import requests
import win32gui
import win32con
import ctypes
import win32api
import win32process
import pyautogui   # used for typing keystrokes
from media_control import MediaController
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import comtypes
import asyncio
import keyboard
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
import comtypes


# ─── Version Handling & Update Checker ─────────────────────────────────

try:
    from version_info import __version__
except ImportError:
    __version__ = "0.0.0"
    try:
        here = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
        remote_ver_file = here / "version.json"
        __version__ = json.loads(remote_ver_file.read_text()).get("version", __version__)
    except:
        pass

VERSION_JSON_URL = "https://raw.githubusercontent.com/Gosheto1234/Voice-Assistant/main/version.json"


# ─── Paths & Logging ────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent
LOG_PATH   = BASE_DIR / "assistant.log"
MIC_FILE   = BASE_DIR / "selected_mic.json"
THEME_JSON = BASE_DIR / "themes.json"
SEL_THEME  = BASE_DIR / "selected_theme.json"
APPS_JSON  = BASE_DIR / "apps_index.json"
USER_CFG   = BASE_DIR / "va_settings.json"  # <-- store media player + music folder here
CREATE_NO_WINDOW = 0x08000000
mc = MediaController()



logger = logging.getLogger("VA")
logger.setLevel(logging.DEBUG)
fh = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logger.addHandler(fh)
logger.addHandler(logging.StreamHandler(sys.stdout))

# ─── Persistence Helpers ─────────────────────────────────────────────────

def load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except:
        return default

def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))

# ─── Update Functions ───────────────────────────────────────────────────

def version_tuple(v): return tuple(map(int, v.split(".")))

def query_update():
    try:
        r = requests.get(VERSION_JSON_URL, timeout=5)
        j = r.json()
        remote  = j.get("version","0.0.0")
        # <-- use the same key your JSON actually has:
        exe_url = j.get("url")
    except Exception as e:
        logger.error("Update check failed: %s", e)
        return None
    if version_tuple(remote) <= version_tuple(__version__):
        return None
    return remote, exe_url, j.get("changelog","")

def perform_update(exe_url):
    try:
        r = requests.get(exe_url, timeout=15)
        r.raise_for_status()
        new_exe = BASE_DIR / "voice_assistant_new.exe"
        new_exe.write_bytes(r.content)
        # now hand off to updater.exe: updater.exe <new> <old>
        old_exe = Path(sys.executable)
        updater  = BASE_DIR / "updater.exe"
        subprocess.Popen(
            [str(updater), str(new_exe), str(old_exe)],
            creationflags=CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # exit immediately so updater can overwrite this process
        sys.exit(0)
    except Exception as e:
        mb.showerror("Update Failed", str(e))

def on_update_click():
    info = query_update()
    if not info:
        mb.showinfo("No Update","You’re on latest")
        return
    v,u,log = info
    if mb.askyesno("Update Available", f"{v}\n{log}\nInstall?"):
        perform_update(u)




# ─── Bulgarian ↔ English action-word mappings ────────────────────────────────
BG_TO_EN_ACTION = {
    # “open” synonyms
    "отвори":     "open",
    "стартирай":  "open",
    "пусни":      "open",

    # “close” synonyms
    "затвори":    "close",
    "спри":       "close",
    "затвори го": "close",

    # “switch” synonyms
    "превключи":  "switch",
    "смени":      "switch",
    "смени на":   "switch",

    # “play” synonyms (for media & music)
    "пусни":      "play",
    "изпълни":    "play",
    "слушай":     "play",
}

# Typing-mode toggles with a few alternative phrases
BG_TYPE_ON  = ("режим писане", "режим за писане", "включи писане")
BG_TYPE_OFF = ("излез режим писане", "изключи писане", "спри писане")





# ─── App‐scan & commands ─────────────────────────────────────────────────

def scan_installed_apps():
    apps = {}

    # 1) HKLM Uninstall (32-bit & 64-bit)
    for hive, flag in (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
    ):
        sub_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        try:
            with winreg.OpenKey(hive, sub_key, 0, winreg.KEY_READ | flag) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        sub = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, sub) as sk:
                            name, _ = winreg.QueryValueEx(sk, "DisplayName")
                            icon, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                            if name and icon:
                                exe_path = icon.split(",")[0]
                                apps[name.lower()] = exe_path
                    except OSError:
                        continue
        except OSError:
            continue

    # 2) HKCU Uninstall (current user)
    try:
        cu_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cu_key, 0, winreg.KEY_READ) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, sub) as sk:
                        name, _ = winreg.QueryValueEx(sk, "DisplayName")
                        icon, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                        if name and icon:
                            exe_path = icon.split(",")[0]
                            apps[name.lower()] = exe_path
                except OSError:
                    continue
    except OSError:
        pass

    # Helper to scan a Start Menu folder for .lnk shortcuts
    def scan_start_menu_folder(folder_path):
        for root_dir, _, files in os.walk(folder_path):
            for fn in files:
                if fn.lower().endswith(".lnk"):
                    full = os.path.join(root_dir, fn)
                    ps = [
                        "powershell",
                        "-NoProfile",
                        "-WindowStyle", "Hidden",
                        "-Command",
                        f"(New-Object -COM WScript.Shell).CreateShortcut('{full}').TargetPath"
                    ]
                    try:
                        tgt = subprocess.check_output(
                            ps,
                            universal_newlines=True,
                            stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW
                        ).strip()
                        name = fn.lower().rsplit(".", 1)[0]
                        if tgt:
                            apps[name] = tgt
                    except subprocess.SubprocessError:
                        continue
                        
    # 3) All Users Start Menu
    program_data = os.environ.get("PROGRAMDATA", "")
    all_users_start = os.path.join(program_data, "Microsoft", "Windows", "Start Menu", "Programs")
    if os.path.isdir(all_users_start):
        scan_start_menu_folder(all_users_start)

    # 4) Current User’s Start Menu
    app_data = os.environ.get("APPDATA", "")
    user_start = os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs")
    if os.path.isdir(user_start):
        scan_start_menu_folder(user_start)

    return apps

def load_or_build_app_index():
    if APPS_JSON.exists():
        try:
            return load_json(APPS_JSON, {})
        except:
            pass
    apps = scan_installed_apps()
    save_json(APPS_JSON, apps)
    return apps

APP_COMMANDS = load_or_build_app_index()

def handle_system_command(text) -> bool:
    """
    Fuzzy “open”, “close” or “switch” based on APP_COMMANDS.
    Returns True if a command was handled.
    """
    t = text.lower().strip()
    words = t.split()
    if len(words) < 2:
        return False

    action, target = words[0], " ".join(words[1:])
    names = list(APP_COMMANDS.keys())
    best = difflib.get_close_matches(target, names, n=1, cutoff=0.6)
    if not best:
        return False

    app_name = best[0]
    exe_path = APP_COMMANDS[app_name]

    if action == "open":
        try:
            subprocess.Popen(exe_path)
        except Exception:
            pass
        return True

    if action == "close":
        proc = os.path.basename(exe_path)
        try:
            subprocess.run(["taskkill", "/im", proc, "/f"], check=True)
        except Exception:
            pass
        return True

    if action == "switch":
        # First try to bring an existing window to front
        if switch_to_window(app_name):
            return True

        # Otherwise, launch it
        try:
            subprocess.Popen(exe_path)
        except Exception:
            pass
        return True

    return False

def switch_to_window(app_name_fragment: str) -> bool:
    """
    Search all visible top‐level windows for one whose title contains
    `app_name_fragment` (case-insensitive). If found, restore/minimize &
    bring it to the foreground as if Alt+Tabbed to it.
    """
    fragment = app_name_fragment.lower()
    candidates = []

    def _enum(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if fragment in title:
                candidates.append(hwnd)

    win32gui.EnumWindows(_enum, None)
    if not candidates:
        return False

    hwnd = candidates[0]
    try:
        # If window is minimized, restore it
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        # If not already foreground, attach input threads to force focus
        foreground_hwnd = win32gui.GetForegroundWindow()
        if foreground_hwnd != hwnd:
            current_thread = win32api.GetCurrentThreadId()
            target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)

            ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, True)

            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetActiveWindow(hwnd)

            ctypes.windll.user32.AttachThreadInput(current_thread, target_thread, False)
        else:
            win32gui.BringWindowToTop(hwnd)

        return True
    except Exception:
        return False

# ─── Theme Helpers ───────────────────────────────────────────────────────

def load_themes():
    d = load_json(THEME_JSON, {})
    if not d:
        d = {
            "Light": {"bg":"#f0f0f0","fg":"#000","btn_bg":"#e0e0e0","btn_fg":"#000"},
            "Dark":  {"bg":"#333","fg":"#eee","btn_bg":"#555","btn_fg":"#fff"},
        }
        save_json(THEME_JSON, d)
    return d

def load_selected_theme():
    return load_json(SEL_THEME, {}).get("theme", "Dark")

def save_selected_theme(n):
    save_json(SEL_THEME, {"theme":n})

def apply_theme(root, th):
    bg, fg = th["bg"], th["fg"]
    bb, bf = th.get("btn_bg"), th.get("btn_fg")
    root.configure(bg=bg)
    def walk(w):
        for c in w.winfo_children():
            cls = c.__class__.__name__
            if cls in ("Frame","Toplevel"):
                c.configure(bg=bg)
            if cls == "Label":
                c.configure(bg=bg, fg=fg)
            if cls == "Button":
                c.configure(bg=bb, fg=bf)
            walk(c)
    walk(root)

# ─── Mic Helpers ──────────────────────────────────────────────────────────

def load_mic():
    return load_json(MIC_FILE, {}).get("device_index", None)

def save_mic(i):
    save_json(MIC_FILE, {"device_index": i})

# ─── User Settings (media player & music folder) ──────────────────────────

def load_user_cfg():
    cfg = load_json(USER_CFG, {})
    return {
        "media_player": cfg.get("media_player", ""),
        "music_folder": cfg.get("music_folder", "")
    }

def save_user_cfg(media_player, music_folder):
    cfg = {
        "media_player": media_player,
        "music_folder": music_folder
    }
    save_json(USER_CFG, cfg)

# ─── Main UI ───────────────────────────────────────────────────────────────

class VoiceAssistantApp:
    def __init__(self, root):
        self.root = root
        root.title("Voice Assistant")
        root.geometry("500x380")

        # ── Volume control setup via pycaw ────────────────────────
        devices   = AudioUtilities.GetSpeakers()
        interface = devices.Activate(
            IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None
        )
        self.volume = comtypes.cast(interface, comtypes.POINTER(IAudioEndpointVolume))

        # ── Mic indicator ─────────────────────────────────────────
        self.mic_indicator = tk.Label(
            root, text="● Mic: OFF", fg="red", font=("Segoe UI", 10, "bold")
        )
        self.mic_indicator.place(relx=0.01, rely=0.95, anchor="sw")

        # ── Media controller ───────────────────────────────────────
        self.mc = MediaController()

        # ── Top Controls ───────────────────────────────────────────
        frm = tk.Frame(root); frm.pack(pady=5)
        self.start_btn = tk.Button(frm, text="Start", command=self.start_listening)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = tk.Button(frm, text="Stop", command=self.stop_listening, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)
        tk.Button(frm, text="⚙️Settings",   command=self.open_settings).pack(side=tk.LEFT, padx=5)
        tk.Button(frm, text="Check Update", command=on_update_click).pack(side=tk.LEFT)
        tk.Button(frm, text="update test", command=on_update_click).pack(side=tk.LEFT)
        

        # ── Little Dog GIF ─────────────────────────────────────────
        gif = BASE_DIR / "annoying_dog.gif"
        if gif.exists():
            img = Image.open(gif)
            self.frames = [
                ImageTk.PhotoImage(f.resize((80,80), Image.LANCZOS))
                for f in ImageSequence.Iterator(img)
            ]
            self._gif_i  = 0
            self.dog_lbl = tk.Label(root, bg=root["bg"])
            self.dog_lbl.place(relx=1, rely=1, anchor="se", x=-5, y=-5)
            self._animate_gif()

        # ── Speech Recognizer ──────────────────────────────────────
        self.recognizer   = sr.Recognizer()
        self.mic_index    = load_mic()
        self.microphone   = (
            sr.Microphone(device_index=self.mic_index)
            if self.mic_index is not None else sr.Microphone()
        )
        self.bg_listener = None
        self.typing_mode = False

        # ── Load user config ───────────────────────────────────────
        cfg = load_user_cfg()
        self.media_player = cfg["media_player"]
        self.music_folder = cfg["music_folder"]

        # ── Apply theme ───────────────────────────────────────────
        themes = load_themes()
        apply_theme(root, themes[load_selected_theme()])


    def _animate_gif(self):
        self.dog_lbl.config(image=self.frames[self._gif_i])
        self._gif_i = (self._gif_i + 1) % len(self.frames)
        self.root.after(100, self._animate_gif)


    def start_listening(self):
        if not self.bg_listener:
            with self.microphone as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=0.5)
            self.bg_listener = self.recognizer.listen_in_background(
                self.microphone, self._callback
            )
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.mic_indicator.config(text="● Mic: ON", fg="green")


    def stop_listening(self):
        if self.bg_listener:
            self.bg_listener(wait_for_stop=False)
            self.bg_listener = None
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.mic_indicator.config(text="● Mic: OFF", fg="red")


    def _callback(self, recognizer, audio):
        """Called from the background thread when speech is detected."""
        try:
            # 1) recognize speech
            text  = recognizer.recognize_google(audio, language="bg-BG")
            lower = text.lower().strip()
            print("[You said]", text)

            # 2) volume controls
            if lower in ("запази", "mute"):
                self.volume.SetMute(1, None); print("[Volume] muted"); return
            if lower in ("възстанови звук", "unmute"):
                self.volume.SetMute(0, None); print("[Volume] unmuted"); return
            if lower in ("свиване", "volume down", "громкост надолу"):
                curr = self.volume.GetMasterVolumeLevelScalar()
                new  = max(0.0, curr - 0.1)
                self.volume.SetMasterVolumeLevelScalar(new, None)
                print(f"[Volume] down → {new:.10%}"); return
            if lower in ("повече звук", "volume up", "громкост нагоре"):
                curr = self.volume.GetMasterVolumeLevelScalar()
                new  = min(1.0, curr + 0.1)
                self.volume.SetMasterVolumeLevelScalar(new, None)
                print(f"[Volume] up → {new:.10%}"); return

            # 3) media controls via keyboard
            if lower in ("пауза", "pause"):
                keyboard.send("play/pause media"); print("[Media] play/pause"); return
            if lower in ("пусни", "продължи", "play", "resume"):
                keyboard.send("play/pause media"); print("[Media] play/resume"); return
            if lower in ("следваща песен", "следващ", "next"):
                keyboard.send("next track"); print("[Media] next"); return
            if lower in ("предишна песен", "предишен", "previous"):
                keyboard.send("previous track"); print("[Media] previous"); return
            if lower in ("спри", "stop"):
                keyboard.send("stop media"); print("[Media] stop"); return

            # 4) typing mode
            if lower in BG_TYPE_ON:
                self.typing_mode = True; print("[Typing Mode] enabled"); return
            if lower in BG_TYPE_OFF:
                self.typing_mode = False; print("[Typing Mode] disabled"); return
            if self.typing_mode:
                if lower in ("ентър", "enter"):
                    pyautogui.press("enter")
                else:
                    pyautogui.write(text + " ")
                return

            # 5) Bulgarian → English open/close/switch/play
            words = lower.split()
            if words and words[0] in BG_TO_EN_ACTION:
                en_act = BG_TO_EN_ACTION[words[0]]
                rest   = " ".join(words[1:])
                if en_act == "play":
                    self._play_song(rest); return
                if handle_system_command(f"{en_act} {rest}"):
                    return

            # 6) English “play …” fallback
            if lower.startswith("play "):
                self._play_song(lower[5:]); return

            # 7) English open/close/switch fallback
            if handle_system_command(text):
                return

        except sr.UnknownValueError:
            pass
        except Exception as e:
            print("Recognition error:", e)


    def _play_song(self, song_name_fragment: str):
        """Fuzzy-match a file in self.music_folder and launch it."""
        if not self.media_player or not os.path.isfile(self.media_player):
            print("[Music] No media player set."); return
        if not self.music_folder or not os.path.isdir(self.music_folder):
            print("[Music] No music folder set."); return

        audio_exts = (".mp3",".wav",".flac",".aac",".ogg",".m4a")
        candidates, file_map = [], {}
        for root_dir, _, files in os.walk(self.music_folder):
            for fn in files:
                if fn.lower().endswith(audio_exts):
                    base = os.path.splitext(fn)[0].lower()
                    full = os.path.join(root_dir, fn)
                    candidates.append(base)
                    file_map[base] = full

        if not candidates:
            print("[Music] No audio files found."); return

        best = difflib.get_close_matches(song_name_fragment.lower(), candidates, n=1, cutoff=0.5)
        if not best:
            print(f"[Music] No match for {song_name_fragment!r}."); return

        path = file_map[best[0]]
        print(f"[Music] Playing {best[0]!r} → {path}")
        try:
            subprocess.Popen([self.media_player, path])
        except Exception as e:
            print(f"[Music] Failed to launch player: {e}")


    def open_settings(self):
        win = Toplevel(self.root)
        win.title("Settings")
        win.geometry("350x300")

        # — Theme Selector —
        tk.Label(win, text="Theme:").pack(pady=(10,0))
        themes = load_themes()
        tv = tk.StringVar(value=load_selected_theme())
        cb = ttk.Combobox(win, values=list(themes), textvariable=tv, state="readonly")
        cb.pack(fill=tk.X, padx=20)

        # — Microphone Selector —
        tk.Label(win, text="Microphone:").pack(pady=(15,0))
        mic_names = sr.Microphone.list_microphone_names()
        mv = tk.StringVar()
        idx = load_mic()
        if isinstance(idx, int) and idx < len(mic_names):
            mv.set(mic_names[idx])
        elif mic_names:
            mv.set(mic_names[0])
        mc_combo = ttk.Combobox(win, values=mic_names, textvariable=mv, state="readonly")
        mc_combo.pack(fill=tk.X, padx=20)

        # — Media Player Selector —
        tk.Label(win, text="Preferred Media Player:").pack(pady=(15,0))
        media_keywords = ("player","vlc","spotify","itunes","winamp","foobar")
        player_names, player_map = [], {}
        for friendly, path in APP_COMMANDS.items():
            if any(k in friendly for k in media_keywords):
                player_names.append(friendly)
                player_map[friendly] = path
        mp_var = tk.StringVar(value="")
        cfg = load_user_cfg()
        for friendly, path in player_map.items():
            if path.lower() == cfg["media_player"].lower():
                mp_var.set(friendly); break
        mp_combo = ttk.Combobox(win, values=player_names, textvariable=mp_var, state="readonly")
        mp_combo.pack(fill=tk.X, padx=20)
        def choose_media_player():
            p = filedialog.askopenfilename(
                title="Select Media Player", filetypes=[("EXE","*.exe"),("All","*.*")]
            )
            if p: mp_var.set(p)
        tk.Button(win, text="Browse…", command=choose_media_player).pack(pady=(5,0))

        # — Music Folder Selector —
        tk.Label(win, text="Music Folder:").pack(pady=(15,0))
        mf_var = tk.StringVar(value=cfg["music_folder"])
        mf_entry = tk.Entry(win, textvariable=mf_var, state="readonly")
        mf_entry.pack(fill=tk.X, padx=20)
        def choose_music_folder():
            d = filedialog.askdirectory(title="Select Music Folder")
            if d: mf_var.set(d)
        tk.Button(win, text="Browse…", command=choose_music_folder).pack(pady=(5,0))

        # — Apply & Close —
        def apply_and_close():
            # theme
            save_selected_theme(tv.get())
            apply_theme(self.root, themes[tv.get()])
            # mic
            if mic_names:
                new_idx = mic_names.index(mv.get())
                save_mic(new_idx)
                self.mic_index = new_idx
                self.microphone = sr.Microphone(device_index=new_idx)
                if self.bg_listener:
                    self.stop_listening(); self.start_listening()
            # media player & music folder
            chosen = mp_var.get().strip()
            mpath = player_map.get(chosen, chosen)
            save_user_cfg(mpath, mf_var.get().strip())
            self.media_player  = mpath
            self.music_folder  = mf_var.get().strip()
            win.destroy()

        tk.Button(win, text="Apply", command=apply_and_close).pack(pady=15)
        


if __name__ == "__main__":
    # 0) If updater.exe just wrote a flag file, notify and delete it
    flag = BASE_DIR / "just_updated.flag"
    if flag.exists():
        flag.unlink()
        mb.showinfo("Updated", "Voice Assistant was successfully updated.")
    root = tk.Tk()

    # Optional auto‐update on launch
    info = query_update()
    if info:
        v,u,chg = info
        if mb.askyesno("Update Available", f"{v}\n{chg}\nInstall now?"):
            perform_update(u)
    
    VoiceAssistantApp(root)
    root.mainloop()

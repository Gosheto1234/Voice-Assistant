import os
import sys
import json
import threading
import time
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import ttk, Toplevel, scrolledtext, messagebox as mb
import speech_recognition as sr
import glob
import subprocess
import psutil
import difflib
import random
import requests
import zipfile
from PIL import Image, ImageTk, ImageSequence
import win32gui, win32process, win32con
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
import asyncio
import nest_asyncio

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

# ——— Update Functions ———
def version_tuple(v):
    return tuple(map(int, v.split('.')))


def query_update():
    try:
        resp = requests.get(VERSION_JSON_URL, timeout=5)
        data = resp.json()
        remote = data.get("version", "0.0.0")
    except Exception as e:
        ui_log(f"Update check failed: {e}", "error")
        return None
    if version_tuple(remote) <= version_tuple(__version__):
        return None
    download_url = data.get("zip_url")
    changelog = data.get("changelog", "")
    return remote, download_url, changelog


def perform_update(download_url):
    try:
        r = requests.get(download_url, timeout=10)
        r.raise_for_status()
        with open(UPDATE_ZIP_PATH, 'wb') as f:
            f.write(r.content)
        with zipfile.ZipFile(UPDATE_ZIP_PATH, 'r') as z:
            z.extractall(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else __file__))
        mb.showinfo("Updated", f"Updated to new version. Please restart.")
        main_root.destroy()
    except Exception as e:
        mb.showerror("Update Failed", str(e))


def on_update_click():
    info = query_update()
    if not info:
        mb.showinfo("No Update", "You’re on the latest version.")
        return
    remote, url, changelog = info
    if mb.askyesno("Update Available", f"Version {remote} available.\nChangelog:\n{changelog}\nInstall?" ):
        perform_update(url)

# ——— Theme & UI Helpers ———
BASE_DIR = os.path.dirname(__file__)
SETTINGS = {
    'themes': os.path.join(BASE_DIR, 'themes.json'),
    'selected_theme': os.path.join(BASE_DIR, 'selected_theme.json'),
}

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


def load_selected_theme():
    data = load_json(SETTINGS['selected_theme'], {}) or {}
    return data.get("theme", "Dark")


def save_selected_theme(theme_name):
    save_json(SETTINGS['selected_theme'], {"theme": theme_name})


def apply_theme(root, theme):
    bg = theme['bg']; fg=theme['fg']; bbg=theme['button_bg']; bfg=theme['button_fg']
    root.configure(bg=bg)
    def rec(w):
        cls = w.__class__.__name__
        if cls in ("Frame","Label","Button","Canvas","Toplevel"): w.configure(bg=bg)
        if cls in ("Label",): w.configure(fg=fg)
        if cls=="Button": w.configure(bg=bbg, fg=bfg)
        for c in w.winfo_children(): rec(c)
    rec(root)
    ui_log(f"Applied theme {theme}", "info")

# ——— UI Feedback & Logging ———
log_widget = None; feedback_frame=None; status_label=None

def ui_log(msg, lvl="info"):
    getattr(logger, lvl)(msg)
    if log_widget:
        log_widget.insert(tk.END, msg+"\n"); log_widget.see(tk.END)

def show_feedback(msg):
    if feedback_frame:
        for w in feedback_frame.winfo_children(): w.destroy()
        tk.Label(feedback_frame, text=msg, anchor="w").pack(fill=tk.X)

# ——— AnimatedDog ———
class AnimatedDog:
    def __init__(self, canvas, gif_path, bowl_x, bowl_y, bowl_radius):
        self.canvas=canvas; self.bowl_x=bowl_x; self.bowl_y=bowl_y; self.bowl_radius=bowl_radius; self.bowl_full=100
        self.frames=[ImageTk.PhotoImage(f.resize((48,48), Image.Resampling.LANCZOS))
                     for f in ImageSequence.Iterator(Image.open(gif_path))]
        self.idx=0; self.step=2
        self.sprite=canvas.create_image(10,10,image=self.frames[0],anchor="nw")
        main_root.after(100,self._init_target); threading.Thread(target=self._refill_loop,daemon=True).start()
        self.anim(); self.move()
    def _init_target(self): self.target=self._new_target()
    def _refill_loop(self):
        while True: time.sleep(60); self.bowl_full=100; self.canvas.itemconfig(self.bowl_id, outline="green",width=3)
    def _new_target(self):
        self.canvas.update_idletasks(); w=max(self.canvas.winfo_width(),48);h=max(self.canvas.winfo_height(),48)
        return (random.randint(0,w-48), random.randint(0,h-48))
    def anim(self):
        self.idx=(self.idx+1)%len(self.frames); self.canvas.itemconfig(self.sprite,image=self.frames[self.idx])
        main_root.after(200,self.anim)
    def move(self):
        if hasattr(self,'target'):
            cx,cy=self.canvas.coords(self.sprite);tx,ty=self.target
            dx,dy=tx-cx,ty-cy; dist=(dx*dx+dy*dy)**.5
            if dist<self.step: self.target=self._new_target()
            else: self.canvas.coords(self.sprite,cx+dx/dist*self.step,cy+dy/dist*self.step)
        main_root.after(100,self.move)
    def eat(self):
        self.bowl_full=0; self.canvas.itemconfig(self.bowl_id, outline="red",width=3)
        t=tk.Label(main_root,text="🍖",font=("Arial",24),bg="black");t.place(x=self.bowl_x,y=self.bowl_y-50)
        main_root.after(1000,t.destroy)

# ——— UI Construction ———
def open_settings():
    win=Toplevel(main_root); win.title("Settings"); win.geometry("300x200")
    tk.Label(win,text="Theme").pack(pady=5)
    themes=load_themes(); names=list(themes.keys()); sel=tk.StringVar(value=load_selected_theme())
    combo=ttk.Combobox(win,values=names,state="readonly",textvariable=sel); combo.pack(pady=5)
    def apply(): save_selected_theme(sel.get()); apply_theme(main_root,themes[sel.get()]); win.destroy()
    tk.Button(win,text="Apply",command=apply).pack(pady=10)


def build_ui():
    global main_root, log_widget, feedback_frame, status_label
    main_root=tk.Tk(); main_root.title("Voice Assistant"); main_root.geometry("400x300")
    tk.Label(main_root,text=f"Version: {__version__}").place(relx=1,rely=0,anchor="ne",x=-10,y=10)
    canvas=tk.Canvas(main_root,bg="black"); canvas.pack(fill=tk.BOTH,expand=True)
    bowl_x,bowl_y,rad=200,150,20
    canvas.create_oval(bowl_x-rad,bowl_y-rad,bowl_x+rad,bowl_y+rad,fill="brown",outline="green",width=3,tags="bowl")
    dog=AnimatedDog(canvas,os.path.join(BASE_DIR,"annoying_dog.gif"),bowl_x,bowl_y,rad)
    dog.bowl_id=canvas.find_withtag("bowl")[0]
    status_label=tk.Label(main_root,text="Idle",bg="black",fg="white"); status_label.place(relx=0.01,rely=0.01,anchor="nw")
    feedback_frame=tk.Frame(main_root,bg="black"); feedback_frame.pack(side=tk.BOTTOM,fill=tk.X)
    frame=tk.Frame(main_root,bg="black"); frame.pack(side=tk.BOTTOM,pady=5)
    tk.Button(frame,text="Start",width=10,command=lambda: ui_log("Start")).pack(side=tk.LEFT,padx=5)
    tk.Button(frame,text="Stop",width=10,command=lambda: ui_log("Stop")).pack(side=tk.LEFT,padx=5)
    tk.Button(frame,text="Update",width=10,command=on_update_click).pack(side=tk.LEFT,padx=5)
    tk.Button(main_root,text="⚙️",width=4,command=open_settings).place(relx=1,x=-10,y=10,anchor="ne")
    log_widget=scrolledtext.ScrolledText(main_root,height=5); log_widget.pack(side=tk.BOTTOM,fill=tk.X)
    # Apply theme
    themes=load_themes(); apply_theme(main_root, themes.get(load_selected_theme()))
    ui_log("Ready.","info")
    return main_root

if __name__=='__main__':
    # On startup update check
    info=query_update()
    if info:
        rem, url, log=text=info
        if mb.askyesno("Update Available",f"Version {rem} available.\nChangelog:\n{log}\nInstall?" ):
            perform_update(url)
    app=build_ui(); app.mainloop()

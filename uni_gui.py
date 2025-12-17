import tkinter as tk
from tkinter import ttk, messagebox
import json
import subprocess
import re
import os
import shutil
import time
import sys
import hashlib

# --- VERSION CONTROL ---
# Increment this number whenever you change the Daemon logic!
DAEMON_VERSION = "1.1"

# --- EMBEDDED INSTALLER SCRIPT ---
INSTALLER_SCRIPT_CONTENT = r"""#!/bin/bash
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

DAEMON_PATH="/usr/local/bin/uni-curve-daemon.py"
SERVICE_PATH="/etc/systemd/system/uni-curve.service"

echo "--- Installing Uni-Sync Smart Daemon v__VERSION__ ---"

# 1. Write the Python Daemon
cat << 'PY_EOF' > $DAEMON_PATH
#!/usr/bin/env python3
# VERSION: __VERSION__
import json, subprocess, time, os, hashlib, sys

CURVE_FILE = "/etc/uni-sync/fan_curves.json"
CONFIG_FILE = "/etc/uni-sync/uni-sync.json"

def get_file_hash(filepath):
    try:
        with open(filepath, 'rb') as f: return hashlib.md5(f.read()).hexdigest()
    except: return ""

def get_temp():
    max_t = 0
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            t = int(f.read()) / 1000
            if t > max_t: max_t = t
    except: pass
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'], capture_output=True, text=True)
        if r.returncode == 0:
            t = float(r.stdout.strip())
            if t > max_t: max_t = t
    except: pass
    return max_t

def calculate_speed(temp, points):
    if not points: return 50
    points.sort(key=lambda x: x[0])
    if temp <= points[0][0]: return points[0][1]
    if temp >= points[-1][0]: return points[0][1]
    for i in range(len(points) - 1):
        t1, s1 = points[i]
        t2, s2 = points[i+1]
        if t1 < temp <= t2:
            return int(s1 + (s2 - s1) * ((temp - t1) / (t2 - t1)))
    return points[-1][1]

def apply_fan_settings():
    try: subprocess.Popen(['uni-sync'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

def main():
    if not os.path.exists(CURVE_FILE):
        with open(CURVE_FILE, 'w') as f: json.dump({}, f)
    
    last_hash = get_file_hash(CONFIG_FILE)
    last_run = 0
    
    while True:
        try:
            curr_time = time.time()
            curr_hash = get_file_hash(CONFIG_FILE)
            
            # Instant Update
            if curr_hash != last_hash:
                apply_fan_settings()
                last_hash = curr_hash
                time.sleep(1)
                continue

            # Curve Update (Every 3s)
            if curr_time - last_run > 3:
                last_run = curr_time
                if not os.path.exists(CURVE_FILE): continue
                try:
                    with open(CURVE_FILE, 'r') as f: curves = json.load(f)
                    with open(CONFIG_FILE, 'r') as f: uni_conf = json.load(f)
                except: continue
                
                if not curves: continue
                curr_t = get_temp()
                changed = False

                for uid, pts in curves.items():
                    try:
                        d_idx, c_idx = map(int, uid.split('-'))
                        if d_idx < len(uni_conf['configs']):
                            ch = uni_conf['configs'][d_idx]['channels'][c_idx]
                            if ch.get('mode') == 'Manual':
                                tgt = calculate_speed(curr_t, pts)
                                if abs(ch.get('speed', 0) - tgt) > 0:
                                    ch['speed'] = tgt
                                    changed = True
                    except: pass

                if changed:
                    with open(CONFIG_FILE, 'w') as f: json.dump(uni_conf, f, indent=4)
                    apply_fan_settings()
                    last_hash = get_file_hash(CONFIG_FILE)
        except: pass
        time.sleep(1)

if __name__ == "__main__":
    main()
PY_EOF
chmod +x $DAEMON_PATH

# 2. Write Service
cat << SVC_EOF > $SERVICE_PATH
[Unit]
Description=Uni-Sync Temperature Curve Daemon
After=network.target uni-sync.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 $DAEMON_PATH
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SVC_EOF

# 3. Start
systemctl daemon-reload
systemctl enable uni-curve.service
systemctl restart uni-curve.service
""".replace("__VERSION__", DAEMON_VERSION)

# --- GUI CODE ---
CONFIG_PATH = "/etc/uni-sync/uni-sync.json"
CURVE_PATH = "/etc/uni-sync/fan_curves.json"
DAEMON_SVC = "uni-curve.service"
DAEMON_BIN = "/usr/local/bin/uni-curve-daemon.py"

COLOR_BG, COLOR_CARD, COLOR_ACCENT = "#121212", "#1E1E1E", "#00ADEF"
COLOR_TEXT, COLOR_SUCCESS, COLOR_ERROR = "#FFFFFF", "#00E676", "#FF5252"
COLOR_WARN = "#FFC107"

class UniSyncGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Uni-Sync Controller")
        self.geometry("850x750")
        self.configure(bg=COLOR_BG)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.config_data = {}
        self.curve_data = self.load_json(CURVE_PATH)
        self.setup_theme()
        self.setup_ui()
        self.load_config()
        self.after(500, self.check_status)

    def load_json(self, path):
        if not os.path.exists(path): return {}
        try:
            with open(path, 'r') as f: 
                d = json.load(f)
                if path == CURVE_PATH:
                    for k,v in d.items(): d[k] = [list(p) for p in v]
                return d
        except PermissionError:
            try:
                r = subprocess.run(["cat", path], capture_output=True, text=True)
                d = json.loads(r.stdout)
                if path == CURVE_PATH:
                     for k,v in d.items(): d[k] = [list(p) for p in v]
                return d
            except: pass
        except: pass
        return {}

    def setup_theme(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        s.configure("TCombobox", fieldbackground="#333", background="#333", foreground="white", arrowcolor=COLOR_ACCENT, borderwidth=0)
        s.map("TCombobox", fieldbackground=[("readonly", "#333")], selectbackground=[("readonly", "#333")], selectforeground=[("readonly", "white")])
        s.configure("Horizontal.TScale", background=COLOR_CARD, troughcolor="#2C2C2C", sliderthickness=15)
        s.map("Horizontal.TScale", background=[("active", COLOR_ACCENT), ("!active", COLOR_ACCENT)])

    def setup_ui(self):
        h = tk.Frame(self, bg=COLOR_BG, pady=20)
        h.grid(row=0, column=0, sticky="ew")
        
        tk.Label(h, text="UNI-SYNC", font=("Segoe UI", 20, "bold"), fg=COLOR_ACCENT, bg=COLOR_BG).pack(side=tk.LEFT, padx=(25, 5))
        tk.Label(h, text="MANAGER", font=("Segoe UI", 20), fg=COLOR_TEXT, bg=COLOR_BG).pack(side=tk.LEFT)
        
        self.st_frm = tk.Frame(h, bg=COLOR_BG)
        self.st_frm.pack(side=tk.RIGHT, padx=25)
        self.daemon_box = tk.Frame(self.st_frm, bg=COLOR_BG)
        self.daemon_box.pack(anchor="e")

        c = tk.Frame(self, bg=COLOR_BG)
        c.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)
        
        self.cvs = tk.Canvas(c, bg=COLOR_BG, highlightthickness=0)
        sb = ttk.Scrollbar(c, orient="vertical", command=self.cvs.yview)
        self.frm = tk.Frame(self.cvs, bg=COLOR_BG)
        self.win_id = self.cvs.create_window((0, 0), window=self.frm, anchor="nw")
        
        self.frm.bind("<Configure>", lambda e: self.cvs.configure(scrollregion=self.cvs.bbox("all")))
        self.cvs.bind("<Configure>", lambda e: self.cvs.itemconfig(self.win_id, width=e.width))
        self.cvs.configure(yscrollcommand=sb.set)
        self.cvs.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        f = tk.Frame(self, bg=COLOR_CARD, pady=15, padx=25)
        f.grid(row=2, column=0, sticky="ew")
        
        self.msg = tk.StringVar(value="Ready")
        self.lbl_msg = tk.Label(f, textvariable=self.msg, fg="gray", bg=COLOR_CARD)
        self.lbl_msg.pack(side=tk.LEFT)
        
        self.btn_sav = tk.Button(f, text="APPLY CHANGES", command=self.save, bg=COLOR_ACCENT, fg="white", font=("Segoe UI", 10, "bold"), relief="flat", padx=20, pady=5)
        self.btn_sav.pack(side=tk.RIGHT)
        tk.Button(f, text="Reload", command=self.load_config, bg="#333", fg="white", relief="flat", padx=10, pady=5).pack(side=tk.RIGHT, padx=10)

        def _on_mousewheel(event):
            if event.num == 4: self.cvs.yview_scroll(-1, "units")
            elif event.num == 5: self.cvs.yview_scroll(1, "units")
            elif event.delta: self.cvs.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.bind_all("<Button-4>", _on_mousewheel)
        self.bind_all("<Button-5>", _on_mousewheel)
        self.bind_all("<MouseWheel>", _on_mousewheel)

    def check_status(self):
        for w in self.daemon_box.winfo_children(): w.destroy()
        
        is_active = False
        try:
            r = subprocess.run(["systemctl", "is-active", DAEMON_SVC], capture_output=True, text=True)
            if r.stdout.strip() == "active":
                is_active = True
        except: pass

        if not is_active:
             tk.Button(self.daemon_box, text="⚠ INSTALL SERVICE", command=self.install, bg=COLOR_ERROR, fg="white", font=("Segoe UI", 8, "bold"), relief="flat").pack(pady=2)
             return

        installed_version = "0.0"
        if os.path.exists(DAEMON_BIN):
            try:
                with open(DAEMON_BIN, "r") as f:
                    for line in f:
                        if "# VERSION:" in line:
                            installed_version = line.split("VERSION:")[1].strip()
                            break
            except: pass
        
        if installed_version != DAEMON_VERSION:
            tk.Button(self.daemon_box, text="⚠ UPDATE SERVICE", command=self.install, bg=COLOR_WARN, fg="black", font=("Segoe UI", 8, "bold"), relief="flat").pack(pady=2)
        else:
            tk.Label(self.daemon_box, text=f"● Service v{DAEMON_VERSION} Active", font=("Segoe UI", 9), bg=COLOR_BG, fg=COLOR_SUCCESS).pack(anchor="e")

    def install(self):
        unique_id = int(time.time())
        tmp = f"/tmp/uni_sync_install_{unique_id}.sh"
        
        try:
            with open(tmp, "w") as f: 
                f.write(INSTALLER_SCRIPT_CONTENT)
            
            os.chmod(tmp, 0o755)
            self.msg.set("Requesting Root...")
            self.update_idletasks()
            
            # Execute the installer
            subprocess.run(["pkexec", tmp], check=True)
            
            # Cleanup the temp file immediately after use
            if os.path.exists(tmp):
                os.remove(tmp)
                
            self.check_status()
            messagebox.showinfo("Success", f"Service Updated to v{DAEMON_VERSION}!")
            self.msg.set("Installed!")
        except Exception as e: 
            messagebox.showerror("Error", f"Installation failed: {e}")
        finally:
            # Ensure cleanup happens even if the install fails
            if os.path.exists(tmp):
                os.remove(tmp)

    def load_config(self):
        for w in self.frm.winfo_children(): w.destroy()
        d = self.load_json(CONFIG_PATH)
        if "configs" in d:
            self.config_data = d
            for i, c in enumerate(d["configs"]): self.card(i, c)

    def card(self, i, c):
        fr = tk.Frame(self.frm, bg=COLOR_CARD, pady=10, padx=10)
        fr.pack(fill=tk.X, expand=True, pady=10)
        tk.Label(fr, text=f"CONTROLLER {i+1}", font=("Segoe UI", 12, "bold"), fg=COLOR_TEXT, bg=COLOR_CARD).pack(anchor="w")
        for j, ch in enumerate(c.get("channels", [])): self.row(fr, i, ch, j)

    def row(self, p, di, ch, ci):
        uid = f"{di}-{ci}"
        mode = ch.get("mode", "Manual")
        if uid in self.curve_data: mode = "Curve"
        
        cont = tk.Frame(p, bg=COLOR_CARD, pady=5)
        cont.pack(fill=tk.X)
        top = tk.Frame(cont, bg=COLOR_CARD)
        top.pack(fill=tk.X)
        tk.Label(top, text=f"GROUP {ci+1}", width=8, anchor="w", bg=COLOR_CARD, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        mv = tk.StringVar(value=mode)
        cb = ttk.Combobox(top, textvariable=mv, values=["Manual", "PWM", "Curve"], state="readonly", width=8)
        cb.pack(side=tk.LEFT, padx=10)
        
        area = tk.Frame(cont, bg=COLOR_CARD)
        area.pack(fill=tk.X, pady=5, padx=2)

        def rend(*a):
            for w in area.winfo_children(): w.destroy()
            m = mv.get()
            if m != "Curve":
                ch["mode"] = m
                if uid in self.curve_data: del self.curve_data[uid]
            else:
                ch["mode"] = "Manual"
                if uid not in self.curve_data: self.curve_data[uid] = [[30,30], [50,50], [80,100]]

            if m == "Manual": self.slide(area, ch)
            elif m == "PWM": tk.Label(area, text="Synced to Motherboard", fg="gray", bg=COLOR_CARD).pack(anchor="w", padx=10)
            elif m == "Curve": self.curve(area, uid)
        mv.trace_add("write", rend)
        rend()

    def slide(self, p, ch):
        fr = tk.Frame(p, bg=COLOR_CARD)
        fr.pack(fill=tk.X)
        vv = tk.IntVar(value=ch.get("speed", 50))
        l = tk.Label(fr, text=f"{vv.get()}%", fg=COLOR_ACCENT, bg=COLOR_CARD, width=4, font="bold")
        l.pack(side=tk.RIGHT, padx=10)
        s = ttk.Scale(fr, from_=0, to=100, orient=tk.HORIZONTAL, variable=vv)
        s.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        def up(*a): ch["speed"] = vv.get(); l.config(text=f"{vv.get()}%")
        vv.trace_add("write", up)

    def curve(self, p, uid):
        ed = tk.Frame(p, bg="#252525", pady=10, padx=10)
        ed.pack(fill=tk.X, padx=10)
        pts = self.curve_data[uid]
        rf = tk.Frame(ed, bg="#252525")
        rf.pack(fill=tk.X)
        
        def ref():
            for w in rf.winfo_children(): w.destroy()
            pts.sort(key=lambda x: x[0])
            for i, pt in enumerate(pts):
                r = tk.Frame(rf, bg="#252525", pady=4)
                r.pack(fill=tk.X)
                tv, sv = tk.IntVar(value=pt[0]), tk.IntVar(value=pt[1])
                tk.Entry(r, textvariable=tv, width=4, bg="#333", fg="white", justify="center").pack(side=tk.LEFT, padx=10)
                ttk.Scale(r, from_=0, to=100, orient=tk.HORIZONTAL, variable=sv).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
                sl = tk.Label(r, text=f"{pt[1]}%", width=4, bg="#252525", fg="white")
                sl.pack(side=tk.LEFT)
                
                tv.trace_add("write", lambda *a, v=tv, idx=i: pts[idx].__setitem__(0, v.get() if v.get() else 0))
                def u_s(*a, v=sv, l=sl, idx=i): v_i=int(v.get()); pts[idx][1]=v_i; l.config(text=f"{v_i}%")
                sv.trace_add("write", u_s)
                
                if len(pts)>2: tk.Button(r, text="×", command=lambda x=i: [del_pt(x), ref()], bg="#252525", fg=COLOR_ERROR, bd=0).pack(side=tk.RIGHT)
        
        def del_pt(i): del pts[i]
        def add(): pts.append([60,60]); ref()
        
        def apply_all():
            current_curve = [list(p) for p in pts]
            for di, conf in enumerate(self.config_data.get("configs", [])):
                for ci, chan in enumerate(conf.get("channels", [])):
                    self.curve_data[f"{di}-{ci}"] = [list(p) for p in current_curve]
            self.load_config()
            self.msg.set("Curve copied to all fans.")
            self.lbl_msg.config(fg=COLOR_ACCENT)

        ref()
        br = tk.Frame(ed, bg="#252525")
        br.pack(fill=tk.X, pady=5)
        tk.Button(br, text="+ Add Point", command=add, bg="#333", fg="white", relief="flat", font=("Segoe UI", 8)).pack(side=tk.LEFT)
        tk.Button(br, text="COPY TO ALL FANS", command=apply_all, bg="#444", fg="#00ADEF", relief="flat", font=("Segoe UI", 8, "bold")).pack(side=tk.RIGHT)

    def save(self):
        try:
            with open(CONFIG_PATH, 'w') as f: json.dump(self.config_data, f, indent=4)
            with open(CURVE_PATH, 'w') as f: json.dump(self.curve_data, f, indent=4)
            self.flash_success()
        except PermissionError:
            try:
                t1, t2 = "/tmp/u.tmp", "/tmp/c.tmp"
                with open(t1, 'w') as f: json.dump(self.config_data, f, indent=4)
                with open(t2, 'w') as f: json.dump(self.curve_data, f, indent=4)
                subprocess.run(["pkexec", "sh", "-c", f"mv {t1} {CONFIG_PATH} && mv {t2} {CURVE_PATH}"], check=True)
                self.flash_success()
            except:
                self.msg.set("Save Failed")
                self.lbl_msg.config(fg=COLOR_ERROR)
    
    def flash_success(self):
        self.msg.set("Settings Saved")
        self.lbl_msg.config(fg=COLOR_SUCCESS)
        t, b = self.btn_sav.cget("text"), self.btn_sav.cget("bg")
        self.btn_sav.config(text="✔ SAVED", bg=COLOR_SUCCESS)
        self.after(1000, lambda: self.btn_sav.config(text=t, bg=b))

if __name__ == "__main__":
    app = UniSyncGUI()
    app.mainloop()
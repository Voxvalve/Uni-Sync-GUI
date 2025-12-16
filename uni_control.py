import tkinter as tk
from tkinter import ttk, messagebox
import json
import subprocess
import re
import os
import time
import shutil

CONFIG_PATH = "/etc/uni-sync/uni-sync.json"
SERVICE_NAME = "uni-sync"
POSSIBLE_BINARIES = ["/usr/local/sbin/uni-sync", "/usr/bin/uni-sync", "/usr/sbin/uni-sync"]

# --- THEME COLORS ---
COLOR_BG = "#121212"
COLOR_CARD = "#1E1E1E"
COLOR_ACCENT = "#00ADEF"
COLOR_TEXT = "#FFFFFF"
COLOR_GRAY = "#555555"
COLOR_TROUGH = "#2C2C2C"
COLOR_SCROLL = "#444444"
COLOR_SUCCESS = "#00E676" 
COLOR_ERROR = "#FF5252"  

class UniSyncGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Uni-Sync Controller")
        self.geometry("750x650")
        self.configure(bg=COLOR_BG)
        self.config_data = {}
        self.binary_location = self.find_binary()
        
        self.setup_theme()

        # --- Header ---
        header_frame = tk.Frame(self, bg=COLOR_BG, pady=20)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        
        tk.Label(header_frame, text="UNI-SYNC", font=("Segoe UI", 20, "bold"), 
                 fg=COLOR_ACCENT, bg=COLOR_BG).pack(side=tk.LEFT, padx=(25, 5))
        tk.Label(header_frame, text="MANAGER", font=("Segoe UI", 20), 
                 fg=COLOR_TEXT, bg=COLOR_BG).pack(side=tk.LEFT)

        # Status Indicator (Top Right)
        self.status_frame = tk.Frame(header_frame, bg=COLOR_BG)
        self.status_frame.pack(side=tk.RIGHT, padx=25)
        
        self.status_dot = tk.Label(self.status_frame, text="●", font=("Segoe UI", 16), bg=COLOR_BG, fg=COLOR_GRAY)
        self.status_dot.pack(side=tk.LEFT)
        self.status_text = tk.Label(self.status_frame, text="Ready", font=("Segoe UI", 10, "bold"), bg=COLOR_BG, fg=COLOR_GRAY)
        self.status_text.pack(side=tk.LEFT, padx=5)

        # --- Bottom Bar ---
        self.btn_frame = tk.Frame(self, bg=COLOR_CARD, pady=15, padx=25)
        self.btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.msg_var = tk.StringVar(value="System Ready")
        self.lbl_msg = tk.Label(self.btn_frame, textvariable=self.msg_var, 
                                   fg="gray", bg=COLOR_CARD, font=("Segoe UI", 10))
        self.lbl_msg.pack(side=tk.LEFT)

        self.btn_save = tk.Button(self.btn_frame, text="APPLY CHANGES", command=self.save_and_apply,
                                  bg=COLOR_ACCENT, fg="white", font=("Segoe UI", 10, "bold"),
                                  relief="flat", padx=25, pady=8, cursor="hand2", activebackground="#008ec2")
        self.btn_save.pack(side=tk.RIGHT)

        self.btn_reload = tk.Button(self.btn_frame, text="RELOAD CONFIG", command=self.load_config,
                                    bg="#333", fg="white", font=("Segoe UI", 10),
                                    relief="flat", padx=15, pady=8, cursor="hand2", activebackground="#444")
        self.btn_reload.pack(side=tk.RIGHT, padx=10)

        # --- Content ---
        container = tk.Frame(self, bg=COLOR_BG)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

        self.scrollbar = ttk.Scrollbar(container, orient="vertical", style="Vertical.TScrollbar")
        self.canvas = tk.Canvas(container, bg=COLOR_BG, highlightthickness=0, 
                                yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.config(command=self.canvas.yview)

        self.scrollable_frame = tk.Frame(self.canvas, bg=COLOR_BG)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.scrollable_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

        # Load Config on start
        self.load_config()

    def find_binary(self):
        """Locates the uni-sync binary."""
        for path in POSSIBLE_BINARIES:
            if os.path.exists(path):
                return path
        return shutil.which("uni-sync")

    def setup_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        
        style.configure("TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT,
                        indicatorbackground="#222", indicatorforeground=COLOR_ACCENT, indicatormargin=5)
        style.map("TCheckbutton", indicatorbackground=[('selected', COLOR_ACCENT)]) 
        style.configure("Vertical.TScrollbar", background=COLOR_SCROLL, troughcolor=COLOR_BG, 
                        borderwidth=0, arrowcolor=COLOR_TEXT)
        style.map("Vertical.TScrollbar", background=[('active', COLOR_ACCENT)])
        style.configure("TCombobox", fieldbackground="#333", background="#333", 
                        foreground="white", arrowcolor=COLOR_ACCENT, borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", "#333")], 
                  selectbackground=[("readonly", "#333")], selectforeground=[("readonly", "white")])
        style.configure("Horizontal.TScale", background=COLOR_CARD, troughcolor=COLOR_TROUGH, sliderthickness=15)
        style.map("Horizontal.TScale", background=[("active", COLOR_ACCENT), ("!active", COLOR_ACCENT)])

    def set_status_indicator(self, text, color):
        self.status_dot.config(fg=color)
        self.status_text.config(text=text, fg=color)

    def on_frame_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.check_scrollbar()

    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.check_scrollbar()

    def check_scrollbar(self):
        req_height = self.scrollable_frame.winfo_reqheight()
        canvas_height = self.canvas.winfo_height()
        if req_height > canvas_height:
            if not self.scrollbar.winfo_ismapped():
                self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)
        else:
            if self.scrollbar.winfo_ismapped():
                self.scrollbar.pack_forget()

    def clean_json(self, json_text):
        json_text = re.sub(r'//.*', '', json_text)
        json_text = re.sub(r'/\*.*?\*/', '', json_text, flags=re.DOTALL)
        return json_text

    def load_config(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        if not self.binary_location:
             tk.Label(self.scrollable_frame, text="ERROR: uni-sync binary not found!", bg=COLOR_BG, fg=COLOR_ERROR).pack(pady=20)
             self.set_status_indicator("NOT INSTALLED", COLOR_ERROR)
             return

        if not os.path.exists(CONFIG_PATH):
            tk.Label(self.scrollable_frame, text=f"Config not found at {CONFIG_PATH}", bg=COLOR_BG, fg=COLOR_ERROR).pack(pady=20)
            return

        try:
            with open(CONFIG_PATH, 'r') as f:
                raw_data = f.read()
                clean_data = self.clean_json(raw_data)
                self.config_data = json.loads(clean_data)
                self.build_ui()
                self.msg_var.set("Config Loaded")
        except Exception as e:
            self.msg_var.set("JSON Error")

    def build_ui(self):
        if "configs" not in self.config_data:
            tk.Label(self.scrollable_frame, text="No controllers found.", bg=COLOR_BG, fg="red").pack(pady=20)
            return

        for i, controller in enumerate(self.config_data["configs"]):
            self.create_controller_card(i, controller)

    def create_controller_card(self, index, controller):
        card = tk.Frame(self.scrollable_frame, bg=COLOR_CARD, pady=15, padx=15)
        card.pack(fill=tk.X, expand=True, pady=10, padx=5)
        
        title_frame = tk.Frame(card, bg=COLOR_CARD)
        title_frame.pack(fill=tk.X, pady=(0, 15))
        
        dev_id = controller.get('device_id', 'Unknown').split('/')[1] if '/' in controller.get('device_id', '') else "Controller"
        
        tk.Label(title_frame, text=f"CONTROLLER {index+1}", font=("Segoe UI", 12, "bold"), 
                 fg=COLOR_TEXT, bg=COLOR_CARD).pack(side=tk.LEFT)
        tk.Label(title_frame, text=dev_id, font=("Segoe UI", 10), 
                 fg="gray", bg=COLOR_CARD).pack(side=tk.LEFT, padx=10)

        self.create_rgb_checkbox(title_frame, controller)
        tk.Frame(card, height=1, bg="#333").pack(fill=tk.X, pady=(0, 15))

        for j, channel in enumerate(controller.get("channels", [])):
            self.create_channel_row(card, channel, j)

    def create_rgb_checkbox(self, parent, controller_dict):
        var = tk.BooleanVar(value=controller_dict.get("sync_rgb", False))
        def on_change(*args): controller_dict["sync_rgb"] = var.get()
        var.trace_add("write", on_change)
        ttk.Checkbutton(parent, text="MB SYNC", variable=var, style="TCheckbutton").pack(side=tk.RIGHT)

    def create_channel_row(self, parent, channel_dict, index):
        row = tk.Frame(parent, bg=COLOR_CARD, pady=8)
        row.pack(fill=tk.X)
        
        tk.Label(row, text=f"GROUP {index+1}", width=8, anchor="w", 
                 bg=COLOR_CARD, fg=COLOR_TEXT, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)

        mode_var = tk.StringVar(value=channel_dict.get("mode", "Manual"))
        speed_var = tk.IntVar(value=channel_dict.get("speed", 50))

        combo = ttk.Combobox(row, textvariable=mode_var, values=["Manual", "PWM"], state="readonly", width=8)
        combo.pack(side=tk.LEFT, padx=15)

        scale = ttk.Scale(row, from_=0, to=100, orient=tk.HORIZONTAL, variable=speed_var)
        scale.pack(side=tk.LEFT, padx=15, expand=True, fill=tk.X)

        val_frame = tk.Frame(row, bg="#000", width=55, height=30)
        val_frame.pack_propagate(False)
        val_frame.pack(side=tk.LEFT)
        val_lbl = tk.Label(val_frame, text=f"{speed_var.get()}", fg=COLOR_ACCENT, bg="#000", font=("Segoe UI", 12, "bold"))
        val_lbl.pack(expand=True)
        
        unit_lbl = tk.Label(row, text="%", fg="gray", bg=COLOR_CARD, width=2)
        unit_lbl.pack(side=tk.LEFT, padx=(5, 10)) 

        def update_ui_state(*args):
            current_mode = mode_var.get()
            channel_dict["mode"] = current_mode
            if current_mode == "PWM":
                scale.state(["disabled"])
                val_lbl.config(text="AUTO", fg="gray")
                unit_lbl.config(text="")
            else:
                scale.state(["!disabled"])
                val_lbl.config(text=f"{speed_var.get()}", fg=COLOR_ACCENT)
                unit_lbl.config(text="%")

        def on_speed_change(*args):
            if mode_var.get() == "Manual":
                channel_dict["speed"] = speed_var.get()
                val_lbl.config(text=f"{speed_var.get()}")

        mode_var.trace_add("write", update_ui_state)
        speed_var.trace_add("write", on_speed_change)
        update_ui_state()

    def show_flash_message(self, message, color):
        #Displays a message for 3 seconds then resets.
        self.msg_var.set(message)
        self.lbl_msg.config(fg=color)
        self.after(3000, self.reset_flash_message)

    def reset_flash_message(self):
        #Resets the bottom bar to default state.
        self.msg_var.set("System Ready")
        self.lbl_msg.config(fg="gray")

    def save_and_apply(self):
        self.msg_var.set("Applying...")
        self.lbl_msg.config(fg=COLOR_ACCENT)
        self.set_status_indicator("APPLYING...", COLOR_ACCENT)
        self.update_idletasks()
        
        try:
            # 1. Write Config
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self.config_data, f, indent=4)

            # 2. Run Service
            result = subprocess.run(["systemctl", "restart", SERVICE_NAME], 
                                    capture_output=True, text=True)
            
            if result.returncode == 0:
                self.set_status_indicator("APPLIED", COLOR_SUCCESS)
                self.show_flash_message("✔ Settings Applied Successfully", COLOR_SUCCESS)
            else:
                self.set_status_indicator("ERROR", COLOR_ERROR)
                self.show_flash_message("✖ Failed to Apply Settings", COLOR_ERROR)
                print(f"Error: {result.stderr}")
                
        except Exception as e:
            self.show_flash_message("✖ Script Error", COLOR_ERROR)
            print(e)

if __name__ == "__main__":
    if os.geteuid() != 0: print("Run with sudo!")
    app = UniSyncGUI()
    app.mainloop()

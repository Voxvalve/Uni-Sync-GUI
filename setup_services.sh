#!/bin/bash

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./setup_services.sh)"
  exit
fi

echo "--- Installing Uni-Sync Smart Daemon ---"

# 1. Create the NEW Smart Python Daemon
DAEMON_PATH="/usr/local/bin/uni-curve-daemon.py"
echo "Creating daemon at $DAEMON_PATH..."

cat << 'EOF' > $DAEMON_PATH
#!/usr/bin/env python3
import json
import subprocess
import time
import os
import hashlib
import sys

# Paths
CURVE_FILE = "/etc/uni-sync/fan_curves.json"
CONFIG_FILE = "/etc/uni-sync/uni-sync.json"

def get_file_hash(filepath):
    """Returns an MD5 hash of the file to detect changes."""
    try:
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return ""

def get_temp():
    """Reads the highest temperature from CPU or GPU."""
    max_temp = 0
    # CPU
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            t = int(f.read()) / 1000
            if t > max_temp: max_temp = t
    except: pass
    # GPU (Nvidia)
    try:
        res = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'], 
                             capture_output=True, text=True)
        if res.returncode == 0:
            t = float(res.stdout.strip())
            if t > max_temp: max_temp = t
    except: pass
    return max_temp

def calculate_speed(temp, points):
    if not points: return 50
    points.sort(key=lambda x: x[0])
    if temp <= points[0][0]: return points[0][1]
    if temp >= points[-1][0]: return points[-1][1]
    for i in range(len(points) - 1):
        t1, s1 = points[i]
        t2, s2 = points[i+1]
        if t1 < temp <= t2:
            ratio = (temp - t1) / (t2 - t1)
            return int(s1 + (s2 - s1) * ratio)
    return points[-1][1]

def apply_fan_settings():
    """Runs the uni-sync binary."""
    try:
        # We use Popen to fire-and-forget, ensuring this script doesn't block
        subprocess.Popen(['uni-sync'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Failed to run binary: {e}")

def main():
    print("Uni-Sync Smart Daemon Started.")
    
    # Ensure config exists
    if not os.path.exists(CURVE_FILE):
        with open(CURVE_FILE, 'w') as f: json.dump({}, f)

    last_config_hash = get_file_hash(CONFIG_FILE)
    last_curve_run = 0
    
    while True:
        try:
            current_time = time.time()
            current_config_hash = get_file_hash(CONFIG_FILE)
            
            # 1. WATCH FOR GUI CHANGES (INSTANT)
            # If hash changed, the GUI just wrote a new setting. Apply immediately.
            if current_config_hash != last_config_hash:
                print("Config change detected. Applying...")
                apply_fan_settings()
                last_config_hash = current_config_hash
                time.sleep(1) # Debounce
                continue

            # 2. RUN CURVE LOGIC (EVERY 4 SECONDS)
            if current_time - last_curve_run > 4:
                last_curve_run = current_time
                
                if not os.path.exists(CURVE_FILE): continue
                try:
                    with open(CURVE_FILE, 'r') as f: curves = json.load(f)
                except: continue

                if not curves: continue

                current_temp = get_temp()
                
                try:
                    with open(CONFIG_FILE, 'r') as f: uni_conf = json.load(f)
                except: continue # File might be locked
                
                config_changed = False

                for unique_id, points in curves.items():
                    try:
                        dev_idx, chan_idx = map(int, unique_id.split('-'))
                        if dev_idx < len(uni_conf['configs']) and chan_idx < len(uni_conf['configs'][dev_idx]['channels']):
                            channel = uni_conf['configs'][dev_idx]['channels'][chan_idx]
                            
                            # Only control if mode is Manual (Software Control)
                            if channel.get('mode') == 'Manual':
                                target = calculate_speed(current_temp, points)
                                current_speed = channel.get('speed', 0)
                                
                                # Hysteresis: Only write if change > 2%
                                if abs(current_speed - target) > 2:
                                    channel['speed'] = target
                                    config_changed = True
                    except: pass

                if config_changed:
                    # Write new speeds to JSON
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump(uni_conf, f, indent=4)
                    
                    # Apply changes
                    apply_fan_settings()
                    
                    # Update hash so we don't trigger the "GUI Change" logic in the next loop
                    last_config_hash = get_file_hash(CONFIG_FILE)

        except Exception as e:
            print(f"Loop Error: {e}")
        
        time.sleep(1)

if __name__ == "__main__":
    main()
EOF

# Make executable
chmod +x $DAEMON_PATH

# 2. Create Systemd Service
SERVICE_PATH="/etc/systemd/system/uni-curve.service"
echo "Creating service at $SERVICE_PATH..."

cat << EOF > $SERVICE_PATH
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
EOF

# 3. Reload and Start
echo "Reloading systemd..."
systemctl daemon-reload

echo "Enabling and Starting uni-curve.service..."
systemctl enable uni-curve.service
systemctl restart uni-curve.service

# Check status
if systemctl is-active --quiet uni-curve.service; then
    echo "SUCCESS: Service is running!"
else
    echo "ERROR: Service failed to start. Check 'systemctl status uni-curve.service'"
fi
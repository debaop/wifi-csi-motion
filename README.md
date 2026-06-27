# WiFi CSI Motion Detection with ESP32

Detect movement in a room using nothing but a WiFi signal and a cheap ESP32 board. No camera, no PIR sensor, no special hardware — just the way WiFi signals get disturbed when something moves through them.

---

## How it works

Every WiFi packet carries CSI (Channel State Information) — metadata about how the signal traveled through the air. When something moves in the room, it disturbs multipath reflections and the CSI changes. By tracking variance in CSI amplitude over time, you can detect movement in real time.

---

## Hardware

- **ESP32-WROOM-32** (~₹350 on Robu.in) — with CP2102 USB chip
- **Your WiFi router** (tested with TP-Link AC750) — just needs to be on and broadcasting
- **Micro-USB data cable** (not a charge-only cable — this trips everyone up)
- **Ubuntu 24.04 laptop** with Intel AX201 WiFi (though the laptop WiFi isn't used here)

---

## Setup

### 1. Install dependencies

```bash
sudo apt install git wget flex bison gperf python3 python3-pip python3-venv \
  cmake ninja-build ccache libffi-dev libssl-dev dfu-util libusb-1.0-0 \
  build-essential python-is-python3
```

### 2. Install ESP-IDF v5.3

```bash
mkdir -p ~/esp && cd ~/esp
git clone -b v5.3 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
pip install virtualenv --break-system-packages
bash ./install.sh esp32
. ./export.sh
```

Add this to your `~/.bashrc` so you don't have to source it every time:

```bash
echo '. ~/esp/esp-idf/export.sh' >> ~/.bashrc
```

### 3. Clone esp-csi

```bash
cd ~
git clone https://github.com/espressif/esp-csi.git
```

### 4. Configure the project

```bash
cd ~/esp-csi/examples/get-started/csi_recv_router
idf.py menuconfig
```

In the menuconfig TUI (arrow keys to navigate, Space to toggle, S to save, Q to quit):

- `Example Connection Configuration` → set your WiFi SSID and password
- `Component config` → `Wi-Fi` → enable `WiFi CSI (Channel State Information)`

### 5. Build

```bash
idf.py build
```

Takes a few minutes on first run.

### 6. Flash to ESP32

Plug in your ESP32, then:

```bash
sudo chmod 666 /dev/ttyUSB0   # or ttyUSB1 — check with: ls /dev/ttyUSB*
idf.py -p /dev/ttyUSB0 flash monitor
```

You should see it connect to your router and start printing `CSI_DATA` lines.

Make the permission permanent so you don't need sudo every time:

```bash
sudo usermod -aG dialout $USER
# log out and back in after this
```

---

## Viewing CSI data graphically

Install Python dependencies:

```bash
pip install pyqtgraph PyQt5 pandas scipy statsmodels "numpy<2" --break-system-packages
pip install "scipy==1.13.1" --break-system-packages  # downgrade if needed
```

Run the live graph:

```bash
python3 ~/esp-csi/examples/get-started/tools/csi_data_read_parse.py -p /dev/ttyUSB0
```

You'll see three panels — phase data per subcarrier, IQ plot, and subcarrier phase over time. Walk in front of the ESP32 and watch the graphs move.

**Tip:** If the port keeps disconnecting, press the EN (reset) button on the ESP32 after the script opens the port.

**Shortcut:** Create a `csi` command so you can launch it instantly:

```bash
cat > ~/csi << 'EOF'
#!/bin/bash
sudo chmod 666 /dev/ttyUSB1 2>/dev/null
python3 ~/esp-csi/examples/get-started/tools/csi_data_read_parse.py -p /dev/ttyUSB1
EOF
chmod +x ~/csi
sudo mv ~/csi /usr/local/bin/csi
```

Now just type `csi` to launch.

---

## Motion detection (terminal)

This script auto-calibrates a baseline and prints `<<< MOTION` when movement is detected:

```bash
python3 -c "
import serial, json, numpy as np, csv
from io import StringIO
s = serial.Serial()
s.port = '/dev/ttyUSB1'
s.baudrate = 921600
s.timeout = 0.1
s.dtr = False
s.rts = False
s.open()
print('Calibrating... stay still for 10 seconds')
window = []
baseline_samples = []
calibrated = False
threshold = 0

while True:
    line = s.readline().decode('utf-8', errors='ignore').strip()
    if 'CSI_DATA' not in line: continue
    try:
        data = next(csv.reader(StringIO(line)))
        csi_raw = json.loads(data[-1])
        amp = [np.sqrt(csi_raw[i]**2 + csi_raw[i+1]**2) for i in range(0, len(csi_raw)-1, 2)]
        window.append(amp)
        if len(window) > 3:
            window.pop(0)
            v = np.var(np.array(window), axis=0).mean()
            if not calibrated:
                baseline_samples.append(v)
                print(f'Calibrating... {len(baseline_samples)}/100', end='\r', flush=True)
                if len(baseline_samples) >= 100:
                    threshold = np.mean(baseline_samples) + 3 * np.std(baseline_samples)
                    calibrated = True
                    print(f'\nDone! Threshold: {threshold:.2f}')
            else:
                status = '  <<< MOTION' if v > threshold else ''
                print(f'Variance: {v:.2f}{status}', flush=True)
    except: continue
"
```

Stay still during calibration, then walk around. Typical baseline is ~1.5–2.0, motion spikes to 15–30.

---

## Flashing on a new machine (or sharing with someone)

You don't need to clone and build everything from scratch every time. Just copy the compiled binary:

```bash
# The built firmware is here:
~/esp-csi/examples/get-started/csi_recv_router/build/csi_recv_router.bin

# Flash it directly with esptool (no ESP-IDF needed on the target machine):
pip install esptool --break-system-packages
esptool.py --chip esp32 -p /dev/ttyUSB0 -b 460800 \
  --before default_reset --after hard_reset write_flash \
  --flash_mode dio --flash_size 2MB --flash_freq 40m \
  0x1000 build/bootloader/bootloader.bin \
  0x8000 build/partition_table/partition-table.bin \
  0x10000 build/csi_recv_router.bin
```

The three files you need to share/backup:
- `build/bootloader/bootloader.bin`
- `build/partition_table/partition-table.bin`
- `build/csi_recv_router.bin`

Copy these to a USB drive or upload to GitHub releases. Anyone with `esptool` can flash them without installing ESP-IDF.

---

## Troubleshooting

**`Unable to locate package picoscenes-all`** — PicoScenes only supports Ubuntu 22.04. Use FeitCSI or esp-csi instead.

**`DKMS build failed on kernel 6.17`** — FeitCSI's driver doesn't support kernel 6.17 yet. Use esp-csi (hardware approach) instead.

**`device not accepting address, error -71`** — Dead/faulty ESP32 board. Return and replace it.

**Port is `/dev/ttyUSB1` not `/dev/ttyUSB0`** — Check with `ls /dev/ttyUSB*` before running any command.

**Graph is still / no data** — Press the EN button on the ESP32 after the monitoring script opens the port.

**Motion detected when nothing is moving** — Threshold too low. Run the auto-calibrating script above instead of hardcoding a threshold.

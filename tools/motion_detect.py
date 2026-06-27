import serial
import json
import numpy as np

s = serial.Serial()
s.port = '/dev/ttyUSB0'
s.baudrate = 921600
s.timeout = 2
s.dtr = False
s.rts = False
s.open()
print('port open, waiting for CSI data...')
window = []
count = 0

while True:
    try:
        line = s.readline().decode('utf-8', errors='ignore').strip()
        if 'CSI_DATA' not in line:
            continue
        count += 1
        data = line.split(',')
        csi_raw = json.loads(data[-1])
        amp = [np.sqrt(csi_raw[i]**2 + csi_raw[i+1]**2) for i in range(0, len(csi_raw)-1, 2)]
        window.append(amp)
        if len(window) > 10:
            window.pop(0)
            variance = np.var(np.array(window), axis=0).mean()
            status = "  <<< MOTION" if variance > 5 else ""
            print(f"[{count}] Variance: {variance:.2f}{status}")
    except Exception as e:
        continue

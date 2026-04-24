# 📡 NethraLink v2 – Professional Wireless Camera Bridge

NethraLink is a high-performance desktop application designed to bridge the gap between mobile camera optics and professional desktop workflows. Whether you're a streamer, a media professional, or an IT hardware inspector, NethraLink transforms your Android or iPhone device into a state-of-the-art virtual webcam.

---

## ✨ Key Features & Capabilities

### 📸 Advanced Camera Logic
- **Full resolution suite**: Supports 480p, 720p (HD), 1080p (Full HD), and custom cinema ratios (21:9).
- **Pro presets**: Toggle between Portrait (9:16), Landscape (16:9), Square (1:1), and Classic Photography (4:3) ratios.
- **Orientation Control**: Real-time 90° rotation and horizontal mirroring (flip) to match any setup.
- **Ultra-low latency**: Optimized JPEG-over-WebSocket streaming pipeline for smooth 30+ FPS performance.

### 💻 System & Virtual Camera
- **Seamless Integration**: Automatically registers as a Windows Virtual Camera. Compatible with OBS, Zoom, Microsoft Teams, Skype, and Discord.
- **Dynamic Resizing**: The virtual camera driver automatically adapts its resolution when you change settings on the mobile device—no app restart required.
- **Custom Naming**: Support for custom Virtual Camera device names (e.g., "OBS Virtual Camera").

### 🔗 Robust Connectivity Suite
- **SSL/HTTPS Security**: Built-in self-signed certificate generation enables secure browser features (like camera access) in Google Chrome on Android.
- **Wireless ADB**: Connect and launch the camera page over Wi-Fi without needing a USB cable.
- **USB Reverse Proxy**: For the most stable connection, use the "ADB Link" feature to route traffic through a local port.
- **Auto-Handshake**: The PC app instantly detects mobile connections and auto-starts the stream for a "Zero-Click" experience.

---

## 🚀 Installation & Setup

### 1. Prerequisites
- **Windows 10 or 11** (64-bit)
- **Python 3.10+** (if running from source)
- **Virtual Camera Driver**: Install [OBS Virtual Camera](https://obsproject.com/download) for the best results.

### 2. Running from Source
```powershell
# 1. Clone/Extract the project
# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the app
python main.py
```

### 3. Building the Standalone EXE
We use PyInstaller to create a single, portable executable:
```powershell
pyinstaller --noconsole --onefile --name "NethraLink_Pro" --paths "src" --add-data "src/server/camera_page.html;src/server" --add-data "assets;assets" --icon "assets/icon.png" main.py
```

---

## 📱 User Guide: How to Connect

### 📡 Wireless (Standard)
1. Ensure your Phone and PC are on the **same Wi-Fi**.
2. Scan the **QR Code** shown in the PC app.
3. **Important**: Chrome will show a "Your connection is not private" warning. This is normal for local SSL. Click **Advanced** -> **Proceed**.
4. Grant camera permissions. The PC will detect the phone and start streaming!

### 🔗 USB / Pro Link (Stable)
1. Enable **USB Debugging** in your phone's Developer Options.
2. Plug your phone into your PC via USB.
3. In the app, go to the **USB / ADB** tab and click **Detect**.
4. Click **🔗 ADB Link**. Your phone's browser will open and connect automatically at high speed.

---

## 🛠️ Troubleshooting & FAQ

### Q: Why is my camera blocked in Chrome?
**A:** Chrome requires an **HTTPS** connection for camera access. NethraLink provides this automatically, but you must accept the security warning by clicking "Advanced" -> "Proceed."

### Q: Why does the PC say "Disconnected" even when the phone is on?
**A:** Ensure your firewall is not blocking **Port 9000**. You can use the **"Test Server"** button at the bottom of the PC app to verify if the server is reachable locally.

### Q: How do I improve the frame rate?
**A:** Use a **5GHz Wi-Fi** network or connect via **USB (ADB Link)** for the highest possible bandwidth and lowest latency.

---

## 📂 Project Architecture
- `main.py`: The root entry point and resource path manager.
- `src/gui/`: PyQt6-based modern dark-themed interface.
- `src/server/`: Aiohttp server handling SSL, static files, and WebSockets.
- `src/video/`: The "Engine" – handles frame decoding and Virtual Camera output.
- `src/adb/`: Automation scripts for launching the mobile browser and port forwarding.
- `assets/`: UI assets, icons, and SSL certificates.

---

## 📜 Credits & License
Developed by the **IT & Media Department**. 
Specializing in high-performance hardware inspection and media production tools.

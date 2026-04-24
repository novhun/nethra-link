# 📡 NethraLink v2 – Pro Wireless Camera Bridge

NethraLink is a professional-grade desktop application that transforms your Android or iPhone mobile camera into a high-performance virtual camera for your PC. It bridges the gap between mobile high-quality optics and desktop video conferencing/streaming software.

---

## ✨ Key Features

### 📸 Professional Camera Controls
- **Dynamic Resolution**: Supports from 480p up to **Full HD (1080p)**.
- **Aspect Ratio Control**: Choose from **16:9** (Cinema), **9:16** (Portrait/TikTok), **4:3**, **3:2**, and **Square (1:1)**.
- **Live Frame Rate (FPS)**: Real-time display of transmission speed on both phone and PC.
- **Pro View Modes**: Toggle between **"Full Screen" (Cover)** and **"Fit View" (Contain)**.
- **Tools**: Real-time **Horizontal Mirror (Flip)** and **90° Orientation Rotation**.

### 💻 System Integration
- **Auto-Sync Virtual Camera**: Automatically registers as a system webcam (e.g., "OBS Virtual Camera"). Resizes dynamically when you change resolution on the phone.
- **HTTPS Secure Streaming**: Built-in self-signed SSL support allows camera access in **Google Chrome** on Android without security blocks.
- **Thread-Safe UI**: High-performance PyQt6 interface with background processing for zero-lag interaction.

### 🔗 Robust Connectivity
- **Smart ADB Integration**: Auto-detects devices and launches the camera page via **USB** or **Wireless ADB**.
- **Wi-Fi QR Handshake**: Quickly connect by scanning a QR code on the same local network.
- **Auto-Connect**: The PC app instantly detects when a phone connects and starts the stream automatically.

---

## 🚀 Installation & Setup

### 1. Requirements
- **Windows 10/11**
- **Python 3.10+**
- **Virtual Camera Driver**: Install [OBS Virtual Camera](https://obsproject.com/) (recommended) for system-wide camera support.

### 2. Quick Start
1. Clone or extract the project.
2. Create a virtual environment and install dependencies:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Run the application:
   ```powershell
   python src/main.py
   ```

---

## 📱 How to Connect

### Method A: Wi-Fi (QR Code)
1. Ensure your phone and PC are on the **same Wi-Fi network**.
2. Scan the **QR Code** displayed in the app.
3. **SSL Warning**: Chrome will show a "Connection not private" screen. Click **Advanced** -> **Proceed**.
4. Allow camera permissions. The stream will start automatically on your PC!

### Method B: ADB (Pro Link)
1. Enable **USB Debugging** in your phone's Developer Options.
2. Connect via USB.
3. In NethraLink, go to **USB / ADB** -> click **🔍 Detect**.
4. Click **🔗 ADB Link**. Your phone browser will open and connect securely.

---

## ⚙️ Project Architecture
- `src/main.py`: Application entry point.
- `src/gui/`: UI components (Main Window, Connection Panels, Video Canvas).
- `src/server/`: Aiohttp WebSocket server and the phone-side Camera Page (HTML5/JS).
- `src/video/`: Video worker for JPEG decoding and Virtual Camera output.
- `src/adb/`: ADB manager for USB/Wireless device control.
- `src/networking/`: SSL Certificate generation and IP discovery.

---

## 🛠️ Troubleshooting
- **Port Conflict**: If port 9000 is busy, the app will automatically retry and wait for it to release.
- **Camera Blocked**: Ensure you are using `https://`. Chrome blocks cameras on plain `http://`.
- **Low FPS**: Lower the resolution or ensure you are using a 5GHz Wi-Fi network or USB connection.

---

## 📜 License
IT & Media Department - High-Performance Inspection Tools.

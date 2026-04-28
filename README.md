# NethraLink 🚀

Wireless Camera Bridge & Multi-Device Monitor for Mac and Windows. Transform your phone into a professional webcam and screen mirroring source.

---

## 📥 Installation

### Mac / Linux
1. Open Terminal and run setup:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
2. Start the app:
   ```bash
   source .venv/bin/activate
   python main.py
   ```

### Windows
1. Double-click `setup.bat`.
2. Start the app:
   ```powershell
   .venv\Scripts\activate
   python main.py
   ```

---

## 🎥 Virtual Camera Feature
To use your phone as a webcam in Zoom, OBS, or Teams, install one of these:
- **OBS Studio**: Standard "OBS Virtual Camera".
- **UnityVideoCapture**: Best for simultaneous multi-device streams.
- **NDI Tools**: For professional broadcast workflows.

---

## 🛠 Key Features
- **Dashboard Multi-Viewer**: Monitor multiple phones side-by-side.
- **ADB Screen Mirroring**: Low-latency phone screen share via USB/Wi-Fi.
- **High-Stability Engine**: New fixed 1080p resolution and letterboxing to prevent crashes in third-party apps.
- **60 FPS Support**: High-performance video decoding for smooth motion.

---

## 🏗 Technical Highlights
- **Fixed Resolution Buffer**: The virtual camera is locked at 1920x1080 to prevent "Pixel buffer size mismatch" errors on macOS and Windows.
- **Intelligent Scaling**: Automatically adds letterboxing (black bars) to phone feeds to keep the aspect ratio perfect in 1080p outputs.
- **Thread Safety**: 2-second shutdown timeouts for workers to ensure hardware drivers are released cleanly.

---

## 💡 Pro Tips
- **Low Latency**: Use a USB cable for ADB mirroring.
- **Bandwidth**: If the Wi-Fi feed is slow, set the Scale to **50%** in settings.
- **Multi-Camera**: Use the **UnityVideoCapture** backend for the best experience with multiple simultaneous virtual cameras.

---
© 2026 NethraLink

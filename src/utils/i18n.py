# i18n.py - Localization for NethraLink

TRANSLATIONS = {
    "en": {
        "dashboard": "🚀 Dashboard",
        "live_feed": "📷 Live Feed",
        "screen_share": "🖥️ Screen Share",
        "connection": "🔗 Connection",
        "system_live": "SYSTEM LIVE",
        "no_devices": "📡 No Devices Connected",
        "connect_guide": "To connect any device (iPhone, Android, Tablet):",
        "go_to_connection": "1. Go to the Connection tab.",
        "scan_qr": "2. Scan the QR Code on your phone.",
        "auto_appear": "3. Your phone camera will appear automatically!",
        "vcam": "Enable to PC (Virtual Camera)",
        "vcam_name": "VCam Name",
        "fps": "FPS",
        "scale": "Scale",
        "start": "Start",
        "stop": "Stop",
        "screenshot": "Screenshot",
        "refresh": "Refresh",
        "select_device": "Select Device",
        "status_connected": "Connected",
        "status_waiting": "Waiting...",
        "status_disconnected": "Disconnected",
        "language": "Language",
        "settings": "⚙️ Settings",
        "general_settings": "General Settings",
        "server_config": "Server Configuration",
        "save_settings": "Save Settings",
        "port": "Server Port",
        "vcam_backend": "VCam Backend (Unity/OBS)",
        "mirror_title": "Phone Screen Mirror (ADB)",
        "camera_title": "Active Camera Feeds",
        "control_center": "Stream Control Center",
        "test_server": "Test Server",
        "screen_page": "Screen Share Page"
    },
    "km": {
        "dashboard": "🚀 ផ្ទាំងគ្រប់គ្រង",
        "live_feed": "📷 ការផ្សាយបន្តផ្ទាល់",
        "screen_share": "🖥️ ចែករំលែកអេក្រង់",
        "connection": "🔗 ការតភ្ជាប់",
        "system_live": "ប្រព័ន្ធដំណើរការ",
        "no_devices": "📡 មិនមានឧបករណ៍ភ្ជាប់ទេ",
        "connect_guide": "ដើម្បីភ្ជាប់ឧបករណ៍ណាមួយ (iPhone, Android, Tablet):",
        "go_to_connection": "១. ចូលទៅកាន់ផ្ទាំងការតភ្ជាប់។",
        "scan_qr": "២. ស្កេនកូដ QR លើទូរស័ព្ទរបស់អ្នក។",
        "auto_appear": "៣. កាមេរ៉ាទូរស័ព្ទនឹងបង្ហាញដោយស្វ័យប្រវត្តិ!",
        "vcam": "បើកទៅកាន់កុំព្យូទ័រ (Virtual Camera)",
        "vcam_name": "ឈ្មោះ VCam",
        "fps": "ល្បឿនរូបភាព",
        "scale": "ទំហំ",
        "start": "ចាប់ផ្តើម",
        "stop": "បញ្ឈប់",
        "screenshot": "ថតរូបអេក្រង់",
        "refresh": "ធ្វើឱ្យស្រស់",
        "select_device": "ជ្រើសរើសឧបករណ៍",
        "status_connected": "បានភ្ជាប់",
        "status_waiting": "កំពុងរង់ចាំ...",
        "status_disconnected": "បានផ្តាច់",
        "language": "ភាសា",
        "settings": "⚙️ ការកំណត់",
        "general_settings": "ការកំណត់ទូទៅ",
        "server_config": "ការកំណត់ម៉ាស៊ីនបម្រើ",
        "save_settings": "រក្សាទុកការកំណត់",
        "port": "ច្រកម៉ាស៊ីនបម្រើ",
        "vcam_backend": "VCam Backend (Unity/OBS)",
        "mirror_title": "ឆ្លុះអេក្រង់ទូរស័ព្ទ (ADB)",
        "camera_title": "កាមេរ៉ាសកម្ម",
        "control_center": "មជ្ឈមណ្ឌលបញ្ជាការផ្សាយ",
        "test_server": "សាកល្បងម៉ាស៊ីនបម្រើ",
        "screen_page": "ទំព័រចែករំលែកអេក្រង់"
    }
}

class Translator:
    _instance = None
    _lang = "en"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Translator, cls).__new__(cls)
        return cls._instance

    def set_lang(self, lang):
        if lang in TRANSLATIONS:
            self._lang = lang

    def get_lang(self):
        return self._lang

    def t(self, key):
        return TRANSLATIONS.get(self._lang, TRANSLATIONS["en"]).get(key, key)

translator = Translator()
t = translator.t

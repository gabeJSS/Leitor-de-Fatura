import os
BG        = "#0f1117"
PANEL     = "#1a1d27"
ACCENT    = "#4f8ef7"
SUCCESS   = "#2ecc71"
DANGER    = "#e74c3c"
WARNING   = "#f39c12"
TEXT      = "#e8eaf0"
SUBTEXT   = "#8b93a8"
BORDER    = "#2a2d3e"
BTN_BG    = "#252836"
BTN_HOV   = "#2f3347"
ENTRY_BG  = "#12151f"
GREEN_BTN = "#1a6e3c"
GREEN_HOV = "#1f8a4a"

VERO_COLOR  = "#ff8c08"
ALGAR_COLOR = "#138126"
VIVO_COLOR  = "#9b59b6"
CLARO_COLOR = "#e74c3c"
MAIS_COLOR  = "#C5C200"   # laranja Mais Internet

APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MacroNotas")
os.makedirs(APPDATA_DIR, exist_ok=True)
JSON_VERO  = os.path.join(APPDATA_DIR, "vero.json")
JSON_ALGAR = os.path.join(APPDATA_DIR, "algar.json")
JSON_VIVO  = os.path.join(APPDATA_DIR, "vivo.json")
JSON_CLARO = os.path.join(APPDATA_DIR, "claro.json")
JSON_MAIS  = os.path.join(APPDATA_DIR, "mais.json")
SETTINGS_FILE = os.path.join(APPDATA_DIR, "settings.json")

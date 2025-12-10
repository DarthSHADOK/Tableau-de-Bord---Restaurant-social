import sys
import os

# ============================================================================
# 1. VERSIONS ET DEPENDANCES
# ============================================================================
APP_VERSION = "1.1.3-beta"

# URL pour la dernière version STABLE uniquement
UPDATE_URL = "https://api.github.com/repos/DarthSHADOK/Tableau-de-Bord---Restaurant-social/releases/latest"

# URL pour TOUTES les versions (y compris Beta/Pre-release)
ALL_RELEASES_URL = "https://api.github.com/repos/DarthSHADOK/Tableau-de-Bord---Restaurant-social/releases"

try:
    import reportlab
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ============================================================================
# 2. GESTION DES CHEMINS (PATHS)
# ============================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    INTERNAL_RES_DIR = sys._MEIPASS 
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INTERNAL_RES_DIR = BASE_DIR

# Dossiers de données
DB_DIR = os.path.join(BASE_DIR, "db")
ARCHIVE_DIR = os.path.join(BASE_DIR, "Archive") 

# Fichiers spécifiques
DB_FILE = os.path.join(DB_DIR, "database.db")
PDF_FILENAME = "Bilan_Mensuel.pdf"

# --- MODIFICATION ICI : On remet "Images" au lieu de "Assets" ---
IMG_DIR = os.path.join(INTERNAL_RES_DIR, "Images")

LOGO_PATH = os.path.join(IMG_DIR, "jericho.png")
ICON_PATH = os.path.join(IMG_DIR, "logo.ico")
SHADOK_GIF_PATH = os.path.join(IMG_DIR, "shadok.gif")

# ============================================================================
# 3. CONSTANTES UI (ICONES & COULEURS)
# ============================================================================
UNICODE_ICONS = {
    "CONSUME": "🎟️", "RECHARGE": "💶", "HISTORY": "🕒", "EDIT": "✏️", "DELETE": "🗑️"
}

class AppColors:
    MENU_BG = "#2c3e50"
    STATS_BG = "#34495e"
    BTN_NEW_BG = "#27ae60"
    BTN_EXPORT_BG = "#e67e22"
    BTN_PRIX_BG = "#546e7a"
    BTN_H_BG = "#3498db"
    BTN_F_BG = "#e91e63"
    BTN_H_OFFERT = "#1abc9c"
    BTN_F_OFFERT = "#9b59b6"
    
    ROW_PAYE = "#b0dbb3"
    ROW_AVANCE = "#f3a6a8"
    ROW_TUTELLE = "#9bcff9"
    ROW_NOCREDIT = "#ffd68c"
    ROW_OFFERT = "#b8c5cb"
    
    HEADER_BG = "#2c3e50"
    BTN_VALIDER = "#3498db"
    FOCUS_ORANGE = "#e67e22"
    MODAL_BG = "#f4f4f4"
    SEARCH_BG = "#ecf0f1"
    SEARCH_BORDER = "#bdc3c7"
    SEARCH_TEXT = "#34495e"
    SEPARATOR = "#455a64"
    
    SWITCH_ON = "#27ae60"   
    SWITCH_OFF = "#e67e22"  
    SWITCH_CIRCLE = "#ffffff"

# ============================================================================
# 4. FEUILLE DE STYLE GLOBALE
# ============================================================================
GLOBAL_STYLESHEET = f"""
    QMainWindow {{ background-color: #f3f3f3; }}
    QWidget {{ font-family: "Segoe UI", "Arial"; font-size: 11pt; }}
    
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QDateEdit {{ background-color: white; border: 2px solid #bdc3c7; border-radius: 6px; padding: 4px; color: black; min-height: 35px; selection-background-color: {AppColors.FOCUS_ORANGE}; selection-color: white; }}
    QLineEdit:focus, QComboBox:focus, QAbstractItemView:focus, QTableWidget:focus, QTextEdit:focus, QPlainTextEdit:focus, QDateEdit:focus {{ border: 2px solid {AppColors.FOCUS_ORANGE}; }}
    QLineEdit:disabled {{ background-color: #f0f0f0; color: #a0a0a0; border: 2px solid #dcdcdc; }}
    
    QComboBox QAbstractItemView {{ background-color: white; color: black; selection-background-color: {AppColors.FOCUS_ORANGE}; selection-color: white; border: 1px solid #bdc3c7; outline: none; }}
    QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {{ background-color: {AppColors.FOCUS_ORANGE}; color: white; border: none; }}
    
    QMenu {{ background-color: white; color: black; border: 1px solid #bdc3c7; border-radius: 6px; padding: 5px 0px; }}
    QMenu::item {{ padding: 6px 30px 6px 30px; background: transparent; }}
    QMenu::item:selected {{ background-color: {AppColors.FOCUS_ORANGE}; color: white; }}
    QMenu::icon {{ position: absolute; left: 5px; top: 5px; bottom: 5px; }}
    
    QDialog {{ background-color: white; color: black; }}
    QDialog QLabel {{ color: #2c3e50; }}
    
    QTableWidget {{ background-color: white; gridline-color: #ecf0f1; color: black; selection-background-color: {AppColors.FOCUS_ORANGE}; selection-color: white; border: 1px solid #bdc3c7; border-radius: 6px; outline: none; }}
    QTableWidget:focus {{ border: 1px solid #bdc3c7; }}
    
    QScrollBar:vertical {{ border: none; background: #f1f1f1; width: 12px; margin: 0px; border-radius: 0px; }}
    QScrollBar::handle:vertical {{ background: {AppColors.FOCUS_ORANGE}; min-height: 20px; border-radius: 6px; margin: 2px; }}
    QScrollBar::handle:vertical:hover {{ background: #d35400; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; background: none; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
    
    QHeaderView::section {{ background-color: #2c3e50; color: white; padding-left: 4px; padding-top: 4px; padding-bottom: 4px; padding-right: 18px; border: none; border-right: 1px solid #5d6d7e; font-weight: bold; font-size: 10pt; }}
    QHeaderView::section:last {{ border-right: none; }}
    QHeaderView::down-arrow, QHeaderView::up-arrow {{ width: 12px; height: 12px; subcontrol-origin: padding; subcontrol-position: center right; }}
    
    QCheckBox {{ spacing: 8px; }}
    QFrame QCheckBox {{ color: white; }}
    QDialog QCheckBox {{ color: #2c3e50; font-weight: bold; }}
    QToolTip {{ background-color: #fefefe; color: #2c3e50; border: 1px solid #bdc3c7; padding: 5px; border-radius: 4px; opacity: 240; }}
"""
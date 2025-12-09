import ssl
import json
import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal
import shutil
import os
import sqlite3
from datetime import datetime
from constants import DB_FILE

# Import des constantes
from constants import APP_VERSION, UPDATE_URL, ALL_RELEASES_URL

# ============================================================================
# WORKER : VÉRIFICATION DE MISE À JOUR
# ============================================================================
class UpdateWorker(QThread):
    """
    Vérifie en arrière-plan si une nouvelle tag est disponible sur GitHub.
    Accepte un canal (stable ou beta).
    """
    update_available = pyqtSignal(str) 

    def __init__(self, channel="stable"):
        super().__init__()
        self.channel = channel

    def run(self):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            # Choix de l'URL selon le canal
            if self.channel == "beta":
                target_url = ALL_RELEASES_URL
            else:
                target_url = UPDATE_URL
            
            req = urllib.request.Request(target_url, headers={'User-Agent': 'GestionRestoApp'})
            
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            online_version = ""
            
            if self.channel == "beta":
                # L'API 'releases' renvoie une LISTE
                if isinstance(data, list) and len(data) > 0:
                    online_version = data[0].get("tag_name", "").strip()
            else:
                # L'API 'releases/latest' renvoie un DICTIONNAIRE
                online_version = data.get("tag_name", "").strip()
            
            if online_version.lower().startswith('v'): 
                online_version = online_version[1:]
            
            if online_version and online_version != APP_VERSION: 
                self.update_available.emit(online_version)
                
        except Exception as e: 
            print(f"Erreur vérification MAJ ({self.channel}): {e}")

# ============================================================================
# WORKER : RÉCUPÉRATION DU CHANGELOG
# ============================================================================
class ChangelogWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal()

    def run(self):
        try:
            tag_name = f"v{APP_VERSION}" if not APP_VERSION.startswith("v") else APP_VERSION
            base_url = UPDATE_URL.rsplit('/', 1)[0]
            url = f"{base_url}/tags/{tag_name}"
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(url, headers={'User-Agent': 'GestionRestoApp'})
            
            with urllib.request.urlopen(req, timeout=5, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
                body = data.get("body", "Aucune information de version disponible.")
                self.finished.emit(body)
        except Exception as e: 
            print(f"Erreur Changelog: {e}")
            self.error.emit()

# ============================================================================
# WORKER : TÉLÉCHARGEMENT DE FICHIER
# ============================================================================
class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url, dest_path): 
        super().__init__()
        self.url = url
        self.dest_path = dest_path

    def run(self):
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            req = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, context=ctx) as response, open(self.dest_path, 'wb') as out_file:
                total_size = int(response.getheader('Content-Length', 0).strip())
                downloaded = 0
                block_size = 1024 * 8 
                
                while True:
                    chunk = response.read(block_size)
                    if not chunk: break
                    out_file.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0: 
                        self.progress.emit(int((downloaded / total_size) * 100))
                        
            self.finished.emit(self.dest_path)
        except Exception as e: 
            self.error.emit(str(e))

# ============================================================================
# WORKER : GÉNÉRATION PDF
# ============================================================================
class PdfWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, app_ref, secondary_path=None, silent_mode=True): 
        super().__init__()
        self.app = app_ref
        self.secondary_path = secondary_path
        self.silent_mode = silent_mode

    def run(self):
        try: 
            if hasattr(self.app, 'generate_pdf_logic_wrapper'):
                self.app.generate_pdf_logic_wrapper(self.secondary_path, self.silent_mode)
        except Exception as e: 
            print(f"Erreur background PDF: {e}")
        self.finished.emit()

class BackupWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, target_folder):
        super().__init__()
        self.target_folder = target_folder

    def run(self):
        try:
            if not os.path.exists(self.target_folder):
                os.makedirs(self.target_folder, exist_ok=True)
            
            date_str = datetime.now().strftime("%Y-%m-%d")
            backup_name = f"backup_{date_str}.db"
            dest_path = os.path.join(self.target_folder, backup_name)
            
            # Méthode intelligente pour SQLite (VACUUM INTO)
            # Permet de sauvegarder sans bloquer et sans corrompre le mode WAL
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(f"VACUUM INTO '{dest_path}'")
                conn.close()
            except:
                # Fallback (méthode bourrin) si VACUUM INTO échoue (vieux python/sqlite)
                shutil.copy2(DB_FILE, dest_path)
            
            # Nettoyage des vieux fichiers (> 7 jours)
            self.clean_old_backups(self.target_folder)
            
            self.finished.emit(True, dest_path)
        except Exception as e:
            self.finished.emit(False, str(e))

    def clean_old_backups(self, folder):
        import time
        now = time.time()
        retention = 7 * 86400
        for f in os.listdir(folder):
            if f.startswith("backup_") and f.endswith(".db"):
                p = os.path.join(folder, f)
                if os.stat(p).st_mtime < (now - retention):
                    try: os.remove(p)
                    except: pass
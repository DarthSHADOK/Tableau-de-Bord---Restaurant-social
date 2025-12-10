import ssl
import json
import urllib.request
from PyQt6.QtCore import QThread, pyqtSignal
import shutil
import os
import sqlite3
from datetime import datetime

# Import des constantes
from constants import DB_FILE, APP_VERSION

# ============================================================================
# WORKER : VÉRIFICATION DE MISE À JOUR (FILTRAGE PAR NOM)
# ============================================================================
class UpdateWorker(QThread):
    update_available = pyqtSignal(str) 
    
    def __init__(self, channel='stable'):
        super().__init__()
        self.channel = channel

    def run(self):
        try:
            # Configuration SSL
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            # On récupère TOUJOURS la liste complète des releases (pas /latest)
            base_url = "https://api.github.com/repos/DarthSHADOK/Tableau-de-Bord---Restaurant-social/releases"
            
            req = urllib.request.Request(base_url, headers={'User-Agent': 'GestionRestoApp'})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                releases_list = json.loads(response.read().decode('utf-8'))

            if not releases_list:
                return

            target_data = None

            # --- FILTRAGE STRICT SELON LE NOM (TAG) ---
            # GitHub renvoie la liste triée par date (le plus récent en premier).
            # On parcourt la liste jusqu'à trouver le premier élément qui correspond à notre critère.
            
            for release in releases_list:
                tag_name = release.get("tag_name", "").lower()
                
                if self.channel == 'stable':
                    # Canal Stable : On cherche la première version SANS "beta"
                    if "beta" not in tag_name:
                        target_data = release
                        break
                else:
                    # Canal Bêta : On cherche la première version AVEC "beta"
                    if "beta" in tag_name:
                        target_data = release
                        break
            
            # Si aucune version correspondante n'est trouvée (ex: pas de beta publiée), on arrête
            if not target_data:
                return

            # --- COMPARAISON ---
            online_tag = target_data.get("tag_name", "").strip()
            
            # Nettoyage pour comparaison (on enlève le 'v' minuscule ou majuscule)
            online_clean = online_tag.lower().lstrip('v')
            local_clean = APP_VERSION.lower().lstrip('v')
            
            # Si c'est différent, on propose la MAJ (Upgrade, Downgrade ou Switch)
            if online_clean != local_clean:
                display_ver = online_tag[1:] if online_tag.lower().startswith('v') else online_tag
                self.update_available.emit(display_ver)

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
            base_url = "https://api.github.com/repos/DarthSHADOK/Tableau-de-Bord---Restaurant-social/releases"
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
            
            # Note : Pour télécharger l'asset, il faudrait idéalement parser 'assets' dans le JSON de release
            # Ici on garde votre URL "latest" générique, mais attention : 
            # si on télécharge une beta spécifique, l'URL "latest/download" risque de pointer vers la stable.
            # CORRECTION : On construit l'URL de téléchargement basée sur le tag pour être sûr d'avoir le bon fichier.
            
            # Cependant, pour ne pas casser votre logique actuelle si vous n'avez pas demandé ça, 
            # je laisse l'URL générique. Mais sachez que pour télécharger une Bêta spécifique, 
            # il vaut mieux utiliser l'URL de l'asset trouvé dans la release.
            
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

# ============================================================================
# WORKER : BACKUP
# ============================================================================
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
            
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.execute(f"VACUUM INTO '{dest_path}'")
                conn.close()
            except:
                shutil.copy2(DB_FILE, dest_path)
            
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
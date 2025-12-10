import sys
import os
import time
import shutil
import zipfile
import psutil
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon

# --- CONFIGURATION GRAPHIQUE (VOTRE CHARTE) ---
STYLE = """
QWidget {
    background-color: #2c3e50;
    color: white;
    font-family: 'Segoe UI', sans-serif;
}
QProgressBar {
    border: 2px solid #bdc3c7;
    border-radius: 5px;
    text-align: center;
    background-color: #34495e;
    color: white;
}
QProgressBar::chunk {
    background-color: #27ae60;
    width: 10px;
    margin: 0.5px;
}
QLabel {
    font-size: 10pt;
    font-weight: bold;
}
"""

class Worker(QThread):
    progress = pyqtSignal(str, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, zip_path, target_dir, main_exe):
        super().__init__()
        self.zip_path = zip_path
        self.target_dir = target_dir
        self.main_exe = main_exe

    def run(self):
        try:
            # 1. ATTENTE FERMETURE (Kill si nécessaire)
            self.progress.emit("Fermeture de l'application...", 10)
            time.sleep(1)
            
            # On tue le processus principal s'il traîne
            exe_name = os.path.basename(self.main_exe)
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == exe_name:
                    try: proc.kill()
                    except: pass
            time.sleep(1)

            # 2. EXTRACTION / REMPLACEMENT
            self.progress.emit("Préparation des fichiers...", 20)
            
            # On dézippe dans un dossier temporaire
            extract_temp = os.path.join(self.target_dir, "temp_update_extract")
            if os.path.exists(extract_temp):
                shutil.rmtree(extract_temp)
                
            with zipfile.ZipFile(self.zip_path, 'r') as zf:
                total_files = len(zf.infolist())
                extracted = 0
                for file in zf.infolist():
                    zf.extract(file, extract_temp)
                    extracted += 1
                    # Progression de 20% à 80%
                    percent = 20 + int((extracted / total_files) * 60)
                    self.progress.emit(f"Extraction : {file.filename}", percent)

            # 3. COPIE FINALE (Écrasement)
            self.progress.emit("Installation de la mise à jour...", 85)
            
            # On suppose que le ZIP contient directement les fichiers ou un dossier racine
            # Si le zip contient "GestionResto/..." on descend d'un niveau
            source_content = extract_temp
            if len(os.listdir(extract_temp)) == 1 and os.path.isdir(os.path.join(extract_temp, os.listdir(extract_temp)[0])):
                source_content = os.path.join(extract_temp, os.listdir(extract_temp)[0])

            # Copie récursive avec écrasement (shutil.copytree avec dirs_exist_ok=True est dispo en Python 3.8+)
            shutil.copytree(source_content, self.target_dir, dirs_exist_ok=True)
            
            # Nettoyage
            self.progress.emit("Nettoyage...", 95)
            shutil.rmtree(extract_temp)
            try: os.remove(self.zip_path)
            except: pass

            self.progress.emit("Terminé !", 100)
            time.sleep(1)
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))

class UpdaterWindow(QWidget):
    def __init__(self):
        super().__init__()
        # Récupération des arguments (Chemin ZIP, Dossier Install, Nom Exe)
        if len(sys.argv) < 4:
            print("Usage: updater.exe <zip_path> <install_dir> <exe_name>")
            sys.exit(1)
            
        self.zip_path = sys.argv[1]
        self.target_dir = sys.argv[2]
        self.main_exe = sys.argv[3]

        self.setWindowTitle("Mise à jour - GestionResto")
        self.setFixedSize(400, 150)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint) # Pas de bordure moche
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout()
        
        self.lbl_status = QLabel("Démarrage de la mise à jour...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)

        self.bar = QProgressBar()
        self.bar.setValue(0)
        layout.addWidget(self.bar)

        self.setLayout(layout)

        # Lancement du travail
        self.worker = Worker(self.zip_path, self.target_dir, self.main_exe)
        self.worker.progress.connect(self.update_ui)
        self.worker.finished.connect(self.restart_app)
        self.worker.error.connect(lambda e: self.lbl_status.setText(f"Erreur : {e}"))
        self.worker.start()

    def update_ui(self, text, val):
        self.lbl_status.setText(text)
        self.bar.setValue(val)

    def restart_app(self):
        # Relance l'application principale
        subprocess.Popen([self.main_exe], cwd=self.target_dir)
        self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = UpdaterWindow()
    win.show()
    sys.exit(app.exec())
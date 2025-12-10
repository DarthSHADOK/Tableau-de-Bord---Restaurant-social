import sys
import os
import json
import sqlite3
import shutil
import threading
import time
import subprocess
import ctypes
import tempfile
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, date

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QFrame, QLineEdit, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QCheckBox, QMessageBox, QMenu, 
    QSizePolicy, QFileDialog, QDateEdit, QPushButton, QToolTip
)
from PyQt6.QtCore import (
    Qt, QTimer, QByteArray, QSize, QDate
)
from PyQt6.QtGui import (
    QColor, QIcon, QPixmap, QAction, QPalette
)

# --- IMPORTS LOCAUX ---
from constants import (
    APP_VERSION, DB_FILE, ICON_PATH, LOGO_PATH, HAS_PIL, 
    AppColors, UNICODE_ICONS, PDF_FILENAME, ARCHIVE_DIR,
    GLOBAL_STYLESHEET
)
import database as db

# Widgets et Dialogues (Dossier UI)
from UI.widgets import (
    ModernButton, RoundedLabelButton, FilterGroup, 
    IconManager, RingChart, ToggleSwitch, NumericTableWidgetItem,
    StatusSpinner
)
from UI.dialogs import (
    NouveauUsagerDialog, ConsommerTicketDialog, RechargerCompteDialog,
    ModifierUsagerDialog, HistoriqueDialog, ConfirmationDialog,
    ExportSupDialog, ImportMasseDialog, PrixDialog, AProposDialog,
    ChangelogDialog, CustomMessageBox, PdfSuccessDialog,
    RestaurationDialog 
)

# Workers et Logique Métier (Dossier Core)
from Core.workers import (
    UpdateWorker, ChangelogWorker, DownloadWorker, PdfWorker, BackupWorker
)
from Core.stats import StatsService
from Core.pdf_generator import generate_pdf_logic, generate_custom_pdf_logic

try:
    from PIL import Image
    from PIL.ImageQt import ImageQt
except ImportError:
    pass


# ============================================================================
# CLASSE UNDO MANAGER
# ============================================================================
class UndoManager:
    def __init__(self, parent_app):
        self.app = parent_app
        self.undo_stack = []
        self.redo_stack = []

    def record_action(self, action_type, prev_state, new_state, history_ids, history_data=None):
        self.undo_stack.append({
            'type': action_type,
            'prev': prev_state,
            'new': new_state,
            'hist_ids': history_ids,
            'hist_data': history_data 
        })
        self.redo_stack.clear() 
        self.app.update_undo_redo_buttons()

    def undo(self):
        if not self.undo_stack: return
        action = self.undo_stack.pop()
        self.redo_stack.append(action)
        self._apply_state(action['prev'], delete_history_ids=action['hist_ids'])
        self.app.update_undo_redo_buttons()

    def redo(self):
        if not self.redo_stack: return
        action = self.redo_stack.pop()
        self.undo_stack.append(action)
        self._apply_state(action['new'])
        if action.get('hist_data'):
            new_ids = []
            conn = db.get_connection()
            try:
                c = conn.cursor()
                for row_data in action['hist_data']:
                    c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, ?, ?, ?, ?)", row_data)
                    new_ids.append(c.lastrowid)
                conn.commit()
                action['hist_ids'] = new_ids
            except Exception as e: 
                print(f"Erreur Redo History: {e}")
            finally: 
                conn.close()
        self.app.load_data()
        self.app.refresh_counters()
        self.app.update_stats()
        self.app.generate_pdf(silent_mode=True)

    def _apply_state(self, state_data, delete_history_ids=None):
        conn = db.get_connection()
        try:
            c = conn.cursor()
            for uid, data in state_data.items():
                c.execute("UPDATE usagers SET solde=?, ticket=?, statut=? WHERE id=?", (data['solde'], data['ticket'], data['statut'], uid))
            if delete_history_ids:
                for hist_id in delete_history_ids:
                    c.execute("DELETE FROM historique_passages WHERE id=?", (hist_id,))
            conn.commit()
        except Exception as e: 
            print(f"Erreur Undo/Redo Apply: {e}")
        finally: 
            conn.close()
        
        self.app.load_data()
        self.app.refresh_counters()
        self.app.update_stats()
        self.app.generate_pdf(silent_mode=True)


# ============================================================================
# MAIN WINDOW
# ============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tableau de bord - Restaurant Social")
        if os.path.exists(ICON_PATH): 
            self.setWindowIcon(QIcon(ICON_PATH))
        
        self.setMinimumSize(1600, 600)  
        
        # --- INITIALISATION ---
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.icon_manager = IconManager()
        self.ticket_price = db.get_ticket_price()
        self.filter_checkboxes = {}
        self.accordions = {}
        self.filters = {k: True for k in ["Payés", "Avances", "Tutelles", "Pas de crédit", "H", "F", "Positif", "Négatif"]}
        
        self.undo_manager = UndoManager(self)
        
        # --- TIMERS ---
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300) 
        self.search_timer.timeout.connect(self.load_data)
        
        self.blink_timer = QTimer()
        self.blink_timer.setInterval(800)
        self.blink_timer.timeout.connect(self.toggle_update_blink)
        self.blink_state = False
        self.new_version_detected = None
        self.btn_about = None 
        
        # --- CONSTRUCTION DE L'INTERFACE ---
        main = QWidget()
        self.setCentralWidget(main)
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(0,0,0,0)
        main_layout.setSpacing(0)
        
        self.frame_left = QFrame()
        self.frame_left.setFixedWidth(260)
        self.frame_left.setStyleSheet(f"background-color: {AppColors.MENU_BG}; border: none;")
        self.setup_menu()
        main_layout.addWidget(self.frame_left)
        
        self.frame_center = QFrame()
        self.frame_center.setStyleSheet("background-color: white;")
        self.setup_center()
        main_layout.addWidget(self.frame_center)
        
        self.frame_right = QFrame()
        self.frame_right.setFixedWidth(280)
        self.frame_right.setStyleSheet(f"background-color: {AppColors.STATS_BG}; border: none;")
        self.setup_right_stats()
        main_layout.addWidget(self.frame_right)
        
        # --- CHARGEMENT ---
        self.load_settings()
        self.resize(1600, 900)
        
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        self.check_monthly_reset()
        
        self.load_data()
        self.refresh_counters()
        self.update_stats()
        
        QTimer.singleShot(1000, self.check_changelog)
        QTimer.singleShot(3000, self.check_updates)
        
        self.perform_startup_backup()
        self.check_auto_maintenance()

    # --- LOGIQUE BACKUP & MAINTENANCE ---
    def perform_startup_backup(self):
        try:
            backup_enabled = db.get_config('EXPORT_SUP_ENABLED') == '1'
            target_dir = db.get_config('EXPORT_SUP_PATH')
            
            if backup_enabled and target_dir and os.path.exists(target_dir):
                if hasattr(self, 'backup_spinner'):
                    self.backup_spinner.start()
                
                self.backup_worker = BackupWorker(target_dir)
                self.backup_worker.finished.connect(self.on_backup_finished)
                self.backup_worker.start()
        except Exception as e:
            print(f"Erreur lancement backup : {e}")

    def on_backup_finished(self, success, message):
        if hasattr(self, 'backup_spinner'):
            self.backup_spinner.stop()
        if success: print(f"Backup terminé : {message}")
        else: print(f"Echec du backup : {message}")

    def check_auto_maintenance(self):
        if db.get_config('AUTO_CLEAN_ENABLED') == '1':
            try:
                conn = db.get_connection()
                c = conn.cursor()
                c.execute("DELETE FROM historique_passages WHERE date_passage < date('now', '-2 years')")
                if c.rowcount > 0:
                    print(f"Maintenance Auto: {c.rowcount} lignes supprimées.")
                    conn.commit()
                    conn.execute("VACUUM")
                conn.close()
            except Exception as e:
                print(f"Erreur Maintenance Auto: {e}")

    # --- LOGIQUE PDF ---
    def generate_pdf(self, secondary_path=None, silent_mode=False):
        if hasattr(self, 'backup_spinner'):
            self.backup_spinner.start()
            QApplication.processEvents()

        if silent_mode: 
            self.pdf_thread = PdfWorker(self, secondary_path, silent_mode)
            self.pdf_thread.finished.connect(self.on_pdf_finished)
            self.pdf_thread.start()
        else: 
            self.generate_pdf_logic_wrapper(secondary_path, silent_mode)
            self.on_pdf_finished()

    def on_pdf_finished(self):
        if hasattr(self, 'backup_spinner'):
            self.backup_spinner.stop()

    def generate_pdf_logic_wrapper(self, secondary_path=None, silent_mode=False):
        try:
            generate_pdf_logic(self.ticket_price, secondary_path, silent_mode)
            self.on_pdf_finished()
            
            if not silent_mode:
                if PdfSuccessDialog(self, PDF_FILENAME).exec(): 
                    now = datetime.now()
                    pdf_filename = f"{now.strftime('%y-%m')}.pdf"
                    pdf_path_archive = os.path.join(ARCHIVE_DIR, pdf_filename)
                    if sys.platform == 'win32': os.startfile(pdf_path_archive)
                    else: subprocess.call(['xdg-open', pdf_path_archive])
        except Exception as e:
            self.on_pdf_finished()
            if not silent_mode: QMessageBox.critical(self, "Erreur PDF", str(e))
            else: print(f"Erreur PDF (Silent): {e}")

    def generate_custom_pdf(self):
        if hasattr(self, 'backup_spinner'):
            self.backup_spinner.start()
            QApplication.processEvents()

        try:
            d_start = self.date_start.date().toString("yyyy-MM-dd")
            d_end = self.date_end.date().toString("yyyy-MM-dd")
            
            pdf_path = generate_custom_pdf_logic(d_start, d_end, self.ticket_price)
            
            if pdf_path:
                if sys.platform == 'win32': os.startfile(pdf_path)
                else: subprocess.call(['xdg-open', pdf_path])
                
                t = threading.Thread(target=monitor_and_delete, args=(pdf_path,), daemon=True)
                t.start()
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de générer le bilan :\n{e}")
        finally:
            self.on_pdf_finished()

    # --- LOGIQUE MISE A JOUR ---
    def check_updates(self):
        channel = db.get_config('UPDATE_CHANNEL', 'stable')
        self.update_worker = UpdateWorker(channel=channel)
        self.update_worker.update_available.connect(self.on_update_detected)
        self.update_worker.start()

    def on_update_detected(self, new_version):
        self.new_version_detected = new_version
        if hasattr(self, 'btn_about') and self.btn_about and not self.blink_timer.isActive(): 
            self.blink_timer.start()

    def toggle_update_blink(self):
        if not self.btn_about: return
        if self.blink_state: 
            self.btn_about.setStyleSheet("QPushButton { background-color: transparent; color: #bdc3c7; border: 1px solid #7f8c8d; border-radius: 4px; font-size: 9pt; } QPushButton:hover { background-color: #34495e; color: white; }")
        else: 
            self.btn_about.setStyleSheet(f"QPushButton {{ background-color: {AppColors.BTN_EXPORT_BG}; color: white; border: 1px solid {AppColors.BTN_EXPORT_BG}; border-radius: 4px; font-weight: bold; font-size: 9pt; }}")
        self.blink_state = not self.blink_state
    
    def check_changelog(self):
        last_run_version = db.get_config('LAST_RUN_VERSION', '0.0.0')
        if last_run_version != APP_VERSION:
            self.cl_worker = ChangelogWorker()
            self.cl_worker.finished.connect(self.show_changelog_popup)
            self.cl_worker.error.connect(self.update_last_run_version)
            self.cl_worker.start()

    def show_changelog_popup(self, text):
        ChangelogDialog(self, APP_VERSION, text).exec()
        self.update_last_run_version()

    def update_last_run_version(self): 
        db.set_config('LAST_RUN_VERSION', APP_VERSION)

    # --- EVENEMENTS ---
    def keyPressEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Z: 
            self.undo_manager.undo()
        elif event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Y: 
            self.undo_manager.redo()
        else: 
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.table.clearSelection()
        self.table.clearFocus()
        self.setFocus()
        super().mousePressEvent(event)

    def closeEvent(self, event): 
        self.save_settings()
        event.accept()

    def save_settings(self):
        try:
            geo = self.saveGeometry().toBase64().data().decode()
            filters_json = json.dumps(self.filters)
            toggles_state = {'sexe': self.toggle_sexe.isChecked(), 'statut': self.toggle_statut.isChecked(), 'solde': self.toggle_solde.isChecked()}
            toggles_json = json.dumps(toggles_state)
            accordions_state = {key: widget.is_expanded for key, widget in self.accordions.items()}
            accordions_json = json.dumps(accordions_state)
            header = self.table.horizontalHeader()
            sorting_state = {'section': header.sortIndicatorSection(),'order': header.sortIndicatorOrder().value}
            sorting_json = json.dumps(sorting_state)
            
            conn = db.get_connection()
            c = conn.cursor()
            for k, v in [('WINDOW_GEOMETRY', geo), ('FILTERS_STATE', filters_json), ('TOGGLES_STATE', toggles_json), ('ACCORDIONS_STATE', accordions_json), ('SORTING_STATE', sorting_json)]:
                c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (k, v))
            conn.commit()
            conn.close()
        except: pass

    def load_settings(self):
        try:
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM config WHERE key='WINDOW_GEOMETRY'")
            res_geo = c.fetchone()
            if res_geo and res_geo[0]: 
                self.restoreGeometry(QByteArray.fromBase64(res_geo[0].encode()))
            c.execute("SELECT value FROM config WHERE key='FILTERS_STATE'")
            res_fil = c.fetchone()
            if res_fil and res_fil[0]:
                saved_filters = json.loads(res_fil[0])
                self.filters = saved_filters
                for k, v in saved_filters.items():
                    if k in self.filter_checkboxes: 
                        self.filter_checkboxes[k].blockSignals(True)
                        self.filter_checkboxes[k].setChecked(v)
                        self.filter_checkboxes[k].blockSignals(False)
            c.execute("SELECT value FROM config WHERE key='TOGGLES_STATE'")
            res_tog = c.fetchone()
            if res_tog and res_tog[0]:
                saved_toggles = json.loads(res_tog[0])
                self.toggle_sexe.setChecked(saved_toggles.get('sexe', False))
                self.toggle_statut.setChecked(saved_toggles.get('statut', False))
                self.toggle_solde.setChecked(saved_toggles.get('solde', False))
            c.execute("SELECT value FROM config WHERE key='ACCORDIONS_STATE'")
            res_acc = c.fetchone()
            if res_acc and res_acc[0]:
                saved_accordions = json.loads(res_acc[0])
                for key, is_open in saved_accordions.items():
                    if key in self.accordions: 
                        self.accordions[key].set_expanded(is_open)
            c.execute("SELECT value FROM config WHERE key='SORTING_STATE'")
            res_sort = c.fetchone()
            if res_sort and res_sort[0]:
                sort_data = json.loads(res_sort[0])
                self.table.horizontalHeader().setSortIndicator(sort_data['section'], Qt.SortOrder(sort_data['order']))
            conn.close()
        except: pass

    def check_monthly_reset(self):
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM config WHERE key='LAST_RESET'")
        res = c.fetchone()
        current_month = datetime.now().strftime("%Y-%m")
        if not res or res[0] != current_month:
            c.execute("UPDATE usagers SET solde=0, ticket=0 WHERE statut='Tutelles'")
            c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage) SELECT 'RAZ Mensuel', 'Automatique', sexe, id, ? FROM usagers WHERE statut='Tutelles'", (datetime.now().strftime("%Y-%m-%d"),))
            c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", ('LAST_RESET', current_month))
            conn.commit()
        conn.close()

    def open_export_dialog(self): 
        ExportSupDialog(self, PDF_FILENAME).exec()
    
    def trigger_update_download(self, dialog_ref):
        # On peut adapter l'URL ici si besoin, mais workers.py fait le gros du travail
        # L'URL "latest/download/GestionResto.exe" peut être problématique pour un ZIP
        # Le DownloadWorker va recevoir l'URL qui a été trouvée par UpdateWorker ?
        # Ici on hardcode souvent "latest", mais pour un zip il vaut mieux utiliser l'url de l'asset.
        # Pour simplifier et rester compatible avec ton processus manuel :
        # Tu mettras dans ta Release GitHub un "GestionResto.zip" (pour le futur) ou "GestionResto.exe" (pour le passé).
        # L'idéal est de récupérer l'URL de l'asset via l'API, mais restons simple pour l'instant.
        
        # URL générique qui redirige vers le binaire de la dernière release
        # ATTENTION : Si tu passes au ZIP, il faudra changer l'extension ici pour les futures versions.
        # Pour cette version "Pivot", on garde .exe car tu vas compiler en --onefile manuellement une dernière fois.
        # Pour la V1.1.4, tu changeras cette ligne en .zip.
        
        # SI TU VEUX QUE CA MARCHE POUR LE FUTUR ZIP AUTOMATIQUEMENT :
        # Il faudrait interroger l'API pour avoir l'URL du premier asset.
        
        # Pour l'instant, on garde l'URL exe car tes utilisateurs actuels ont besoin de l'exe.
        # Mais le DownloadWorker sait gérer le zip si on lui donne une url zip.
        url = "https://github.com/DarthSHADOK/Tableau-de-Bord---Restaurant-social/releases/latest/download/GestionResto.exe" 
        
        # Astuce : Si tu veux supporter le ZIP plus tard, tu devras peut-être changer cette URL dans le code
        # ou faire une détection dynamique.
        
        temp_path = os.path.join(tempfile.gettempdir(), "GestionResto_update.exe") # Extension temporaire
        
        # Si on détecte que la version distante est un zip (logique complexe sans API), on changerait l'extension.
        # Pour l'instant, le DownloadWorker se fiche de l'extension de destination pour le téléchargement,
        # mais pour le dézippage il regarde si ça finit par .zip.
        
        self.dl_worker = DownloadWorker(url, temp_path)
        self.dl_worker.progress.connect(dialog_ref.update_progress)
        self.dl_worker.finished.connect(self.confirm_install)
        self.dl_worker.error.connect(lambda err: QMessageBox.critical(self, "Erreur", f"Échec du téléchargement: {err}"))
        self.dl_worker.start()

    def confirm_install(self, downloaded_file):
        dlg = CustomMessageBox(self, "Mise à jour prête", "Le téléchargement est terminé.\nVoulez-vous fermer l'application et installer la mise à jour maintenant ?")
        if dlg.exec(): self.apply_update(downloaded_file)

    def apply_update(self, downloaded_path):
        try:
            current_exe = sys.executable
            # Dossier où est installé le logiciel
            install_dir = os.path.dirname(current_exe)
            
            batch_script = os.path.join(install_dir, "update.bat")
            
            # --- LOGIQUE INTELLIGENTE : DOSSIER vs FICHIER ---
            if os.path.isdir(downloaded_path):
                # CAS FUTUR (RAPIDE) : On a reçu un dossier (issu d'un ZIP décompressé)
                # On utilise xcopy pour tout écraser proprement
                # /E = Récursif, /H = Fichiers cachés, /Y = Force écrasement, /Q = Silencieux
                cmd = f"""@echo off
timeout /t 1 /nobreak > NUL
xcopy "{downloaded_path}\\*" "{install_dir}\\" /E /H /Y /Q
start "" "{current_exe}"
rmdir "{downloaded_path}" /S /Q
del "%~f0"
"""
            else:
                # CAS ACTUEL/COMPATIBILITÉ (LENT) : On a reçu un fichier unique .exe
                # On fait le remplacement classique
                cmd = f"""@echo off
timeout /t 1 /nobreak > NUL
del "{current_exe}"
move "{downloaded_path}" "{current_exe}"
start "" "{current_exe}"
del "%~f0"
"""

            with open(batch_script, "w") as f:
                f.write(cmd)
            
            # Lancement du script en tâche de fond (sans fenêtre noire)
            subprocess.Popen([batch_script], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            QApplication.quit()
            
        except Exception as e: 
            QMessageBox.critical(self, "Erreur", f"Impossible de lancer la mise à jour:\n{e}")

    def open_restore_dialog(self):
        if db.get_config('EXPORT_SUP_ENABLED') != '1':
            return CustomMessageBox(self, "Sauvegardes inactives", 
                "Le système de sauvegarde automatique n'est pas activé.\n\n"
                "Allez dans 'Forcer Export PDF' (Clic Droit) pour configurer un dossier de sauvegarde.", 
                error=True).exec()
        
        backup_path = db.get_config('EXPORT_SUP_PATH')
        if not backup_path or not os.path.exists(backup_path):
             return CustomMessageBox(self, "Erreur Dossier", 
                "Le dossier de sauvegarde configuré est introuvable.", 
                error=True).exec()

        RestaurationDialog(self).exec()

    # --- ACTIONS UTILISATEUR & UI HELPERS ---
    def update_undo_redo_buttons(self):
        can_undo = len(self.undo_manager.undo_stack) > 0
        can_redo = len(self.undo_manager.redo_stack) > 0
        c_undo = "#e74c3c" if can_undo else "#95a5a6"
        c_redo = "#27ae60" if can_redo else "#95a5a6"
        for btn, color, active in [(self.btn_undo, c_undo, can_undo), (self.btn_redo, c_redo, can_redo)]:
            btn.setEnabled(active)
            hover_color = btn.adjust_color(color, -45)
            btn.setStyleSheet(f"""QPushButton {{ background-color: {color}; color: white; border-radius: 6px; font-weight: bold; border: none; font-size: 9pt; }} QPushButton:hover {{ background-color: {hover_color}; }} QPushButton:disabled {{ background-color: #95a5a6; color: #bdc3c7; }}""")

    def get_selected_id(self):
        r = self.table.selectionModel().selectedRows()
        return int(self.table.item(r[0].row(), 0).text()) if r else None
    
    def select_row(self, uid):
        for r in range(self.table.rowCount()):
            if int(self.table.item(r, 0).text()) == uid: 
                self.table.selectRow(r)
                self.table.scrollToItem(self.table.item(r, 0))
                break
            
    def action_consommer(self):
        uid = self.get_selected_id()
        if uid: 
            conn=db.get_connection()
            c=conn.cursor()
            c.execute("SELECT nom, prenom, ticket, statut FROM usagers WHERE id=?", (uid,))
            d=c.fetchone()
            conn.close()
            ConsommerTicketDialog(self, uid, f"{d[1]} {d[0]}", d[2], d[3]).exec()
            
    def action_recharger(self):
        uid = self.get_selected_id()
        if uid: 
            conn=db.get_connection()
            c=conn.cursor()
            c.execute("SELECT nom, prenom, solde, statut FROM usagers WHERE id=?", (uid,))
            d=c.fetchone()
            conn.close()
            RechargerCompteDialog(self, uid, f"{d[1]} {d[0]}", d[2], d[3]).exec()
            
    def action_historique(self):
        uid = self.get_selected_id()
        if uid: 
            HistoriqueDialog(self, uid, self.table.item(self.table.currentRow(), 1).text()).exec()
        
    def action_modifier(self):
        uid = self.get_selected_id()
        if uid: 
            ModifierUsagerDialog(self, uid).exec()
        
    def action_supprimer(self):
        uid = self.get_selected_id()
        if not uid: return
        dlg = ConfirmationDialog(self, "Confirmer la suppression", "Voulez-vous vraiment supprimer cet usager ?\nCette action est irréversible.")
        if dlg.exec(): 
            conn=db.get_connection()
            c=conn.cursor()
            c.execute("DELETE FROM usagers WHERE id=?", (uid,))
            conn.commit()
            conn.close()
            self.load_data()
            self.update_stats()
            self.generate_pdf(silent_mode=True)
            
    def open_price_dialog(self): 
        if PrixDialog(self).exec(): 
            self.ticket_price = db.get_ticket_price()
            self.load_data()
            self.refresh_counters()
            
    def open_about(self):
        if self.blink_timer.isActive(): 
            self.blink_timer.stop()
            self.btn_about.setStyleSheet("QPushButton { background-color: transparent; color: #bdc3c7; border: 1px solid #7f8c8d; border-radius: 4px; font-size: 9pt; } QPushButton:hover { background-color: #34495e; color: white; }")
        AProposDialog(self, self.new_version_detected, self.trigger_update_download).exec()

    def flash_button(self, btn):
        if not btn: return
        original_style = btn.styleSheet()
        btn.setStyleSheet("background-color: #2ecc71; color: white; border-radius: 6px; font-weight: bold; border: none;")
        QApplication.processEvents()
        QTimer.singleShot(150, lambda: btn.setStyleSheet(original_style))

    def add_passage(self, t, s):
        sender = self.sender()
        if sender and isinstance(sender, ModernButton): 
            self.flash_button(sender)
        
        conn = db.get_connection()
        try:
            c = conn.cursor()
            status_au_passage = "Payés" if t == "PAYE" else "1ère fois"
            today = datetime.now().strftime("%Y-%m-%d")
            data_tuple = (t, 'Anonyme', s, None, today, status_au_passage)
            c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, ?, ?, ?, ?)", data_tuple)
            created_id = c.lastrowid
            conn.commit()
            
            if hasattr(self, 'undo_manager'): 
                self.undo_manager.record_action('ANONYME', {}, {}, [created_id], [data_tuple])
        finally:
            conn.close()
            
        self.refresh_counters()
        self.update_stats()
        self.generate_pdf(silent_mode=True)

    # --- CONSTRUCTION UI (PARTIES) ---
    def add_sep(self, layout): 
        f=QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background:{AppColors.SEPARATOR}")
        layout.addWidget(f)

    def setup_menu(self):
        l = QVBoxLayout(self.frame_left)
        l.setContentsMargins(20, 20, 20, 20)
        l.setSpacing(3)
        
        h_title = QHBoxLayout()
        h_title.setSpacing(10)
        lbl_title = QLabel("TABLEAU DE BORD", styleSheet="color:white; font-weight:bold; font-size:11pt;")
        self.backup_spinner = StatusSpinner() 
        
        h_title.addWidget(lbl_title)
        h_title.addStretch()
        h_title.addWidget(self.backup_spinner) # A droite
        l.addLayout(h_title)
        
        l.addSpacing(5)
        
        btn_new = ModernButton("+ NOUVEL USAGER", AppColors.BTN_NEW_BG, lambda: NouveauUsagerDialog(self).exec(), 35, 6)
        btn_new.rightClicked.connect(lambda: ImportMasseDialog(self).exec())
        l.addWidget(btn_new)
        
        btn_pdf = ModernButton("📄 FORCER EXPORT PDF", AppColors.BTN_EXPORT_BG, self.generate_pdf, 35, 6)
        btn_pdf.rightClicked.connect(self.open_export_dialog)
        l.addWidget(btn_pdf)
        
        self.add_sep(l)
        l.addSpacing(2) 
        l.addWidget(QLabel("PASSAGE ANONYME", styleSheet="color:#bdc3c7; font-weight:bold; font-size:9pt;"))
        l.addSpacing(2)
        l.addWidget(QLabel("TICKET PAYÉ", styleSheet="color:#bdc3c7; font-size:8pt;", alignment=Qt.AlignmentFlag.AlignRight))
        
        h1 = QHBoxLayout()
        h1.setSpacing(6)
        h1.addWidget(ModernButton("+1 HOMME", AppColors.BTN_H_BG, lambda:self.add_passage("PAYE","H"),30,5))
        h1.addWidget(ModernButton("+1 FEMME", AppColors.BTN_F_BG, lambda:self.add_passage("PAYE","F"),30,5))
        l.addLayout(h1)
        l.addSpacing(2)
        
        l.addWidget(QLabel("TICKET OFFERT", styleSheet="color:#bdc3c7; font-size:8pt;", alignment=Qt.AlignmentFlag.AlignRight))
        h_off = QHBoxLayout()
        h_off.setSpacing(6)
        
        v1 = QVBoxLayout(); v1.setSpacing(2); 
        v1.addWidget(ModernButton("+1 HOMME", AppColors.BTN_H_OFFERT, lambda:self.add_passage("1ERE_FOIS","H"),30,5))
        self.lbl_h = QLabel("H: 0", styleSheet="color:#bdc3c7; font-weight:bold;")
        self.lbl_h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v1.addWidget(self.lbl_h)
        
        v2 = QVBoxLayout(); v2.setSpacing(2); 
        v2.addWidget(ModernButton("+1 FEMME", AppColors.BTN_F_OFFERT, lambda:self.add_passage("1ERE_FOIS","F"),30,5))
        self.lbl_f = QLabel("F: 0", styleSheet="color:#bdc3c7; font-weight:bold;")
        self.lbl_f.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v2.addWidget(self.lbl_f)
        
        h_off.addLayout(v1)
        h_off.addLayout(v2)
        l.addLayout(h_off)
        
        l.addSpacing(4)
        self.add_sep(l)
        l.addSpacing(3)
        
        h_undo = QHBoxLayout()
        h_undo.setSpacing(5)
        self.btn_undo = ModernButton("↩ ANNULER", "#7f8c8d", self.undo_manager.undo, 30, 5)
        self.btn_redo = ModernButton("↪ RÉTABLIR", "#7f8c8d", self.undo_manager.redo, 30, 5)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)
        for btn in [self.btn_undo, self.btn_redo]: 
            btn.setStyleSheet(btn.styleSheet().replace("font-size: 10pt;", "font-size: 9pt;"))
        h_undo.addWidget(self.btn_undo)
        h_undo.addWidget(self.btn_redo)
        l.addLayout(h_undo)
        
        l.addSpacing(4)
        self.add_sep(l)
        l.addSpacing(3)
        l.addWidget(ModernButton("⚙ PRIX", AppColors.BTN_PRIX_BG, self.open_price_dialog, 30, 5))
        l.addSpacing(4)
        self.add_sep(l)
        l.addSpacing(2)
        
        group_statut = FilterGroup("FILTRER PAR STATUT", self.frame_left)
        self.accordions["statut"] = group_statut
        self.add_filter_row(group_statut.content_layout, "Payés", AppColors.ROW_PAYE, "Payés")
        self.add_filter_row(group_statut.content_layout, "Avances", AppColors.ROW_AVANCE, "Avances")
        self.add_filter_row(group_statut.content_layout, "Tutelles", AppColors.ROW_TUTELLE, "Tutelles")
        self.add_filter_row(group_statut.content_layout, "Pas de crédit", AppColors.ROW_NOCREDIT, "Pas de crédit")
        l.addWidget(group_statut)
        
        group_sexe = FilterGroup("FILTRER PAR SEXE", self.frame_left)
        self.accordions["sexe"] = group_sexe
        self.add_filter_row(group_sexe.content_layout, "Hommes", AppColors.ROW_TUTELLE, "H") 
        self.add_filter_row(group_sexe.content_layout, "Femmes", AppColors.ROW_AVANCE, "F")
        l.addWidget(group_sexe)
        
        group_solde = FilterGroup("FILTRER PAR SOLDE", self.frame_left)
        self.accordions["solde"] = group_solde
        self.add_filter_row(group_solde.content_layout, "Positif ≥ 0", AppColors.ROW_PAYE, "Positif")
        self.add_filter_row(group_solde.content_layout, "Négatif < 0", AppColors.ROW_AVANCE, "Négatif")
        l.addWidget(group_solde)
        
        l.addStretch()
        
        if HAS_PIL and os.path.exists(LOGO_PATH): 
            il=QLabel()
            i=Image.open(LOGO_PATH)
            i.thumbnail((110,110)) 
            il.setPixmap(QPixmap.fromImage(ImageQt(i)))
            il.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.addWidget(il)
            
        self.lbl_count = QLabel("0 usager(s) visible(s)", styleSheet="color:#bdc3c7;")
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(self.lbl_count)
        
        l.addSpacing(10)
        
        self.btn_about = RoundedLabelButton("À PROPOS", "#34495e", "white", self.open_about, 30, 4, centered=True)
        self.btn_about.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_about.customContextMenuRequested.connect(self.open_restore_dialog)
        
        l.addWidget(self.btn_about)

    def add_filter_row(self, layout, text, color, key=None):
        k = key if key else text
        row = QHBoxLayout()
        row.setContentsMargins(0,0,0,0)
        row.setSpacing(2)
        chk = QCheckBox()
        chk.setChecked(True)
        chk.setCursor(Qt.CursorShape.PointingHandCursor)
        chk.setFixedWidth(20)
        chk.setFixedHeight(26)
        chk.toggled.connect(lambda c: self.toggle_filter(k,c))
        self.filter_checkboxes[k] = chk
        btn = RoundedLabelButton(text, color, command=chk.toggle)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(chk)
        row.addWidget(btn)
        layout.addLayout(row)

    def toggle_filter(self, k, c): 
        self.filters[k] = c
        self.load_data()

    def setup_center(self):
        l = QVBoxLayout(self.frame_center)
        h = QHBoxLayout()
        h.addWidget(QLabel("LISTE DES USAGERS", styleSheet="font-size:14pt; font-weight:bold; color:#2c3e50;"))
        h.addStretch()
        
        f = QFrame()
        f.setStyleSheet(f"background:{AppColors.SEARCH_BG}; border-radius:6px;")
        sl = QHBoxLayout(f)
        sl.setContentsMargins(5,0,5,0)
        
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Rechercher...")
        
        self.search.setStyleSheet(f"""
            QLineEdit {{
                border: none; 
                background: transparent; 
                padding: 5px; 
                color: #2c3e50;
            }}
            QMenu {{
                background-color: {AppColors.MENU_BG};
                color: white;
                border: 1px solid #bdc3c7;
                border-radius: 6px;
                padding: 5px 0px;
            }}
            QMenu::item {{
                padding: 6px 30px;
                background: transparent;
            }}
            QMenu::item:selected {{
                background-color: {AppColors.FOCUS_ORANGE};
                color: white;
            }}
            QMenu::item:disabled {{
                color: #95a5a6; /* Gris clair pour les options désactivées (Couper/Copier vides) */
                background-color: transparent;
                font-style: italic;
            }}
            QMenu::separator {{
                height: 1px;
                background: {AppColors.SEPARATOR};
                margin: 5px 0px;
            }}
        """)
        self.search.textChanged.connect(self.search_timer.start)
        
        bc = QPushButton("✖")
        bc.setCursor(Qt.CursorShape.PointingHandCursor)
        bc.setStyleSheet("border:none; color:#e74c3c; font-weight:bold;")
        bc.clicked.connect(self.search.clear)
        
        sl.addWidget(self.search)
        sl.addWidget(bc)
        h.addWidget(f)
        l.addLayout(h)
        
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["ID","NOM","PRENOM","SEXE","STATUT","SOLDE","TICKET", "COMMENTAIRE", "DERNIER PASSAGE"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.setStyleSheet(f"QHeaderView::section {{ background:{AppColors.HEADER_BG}; color:white; padding:4px; border:none; border-right:1px solid #5d6d7e; font-weight:bold; font-size: 10pt; }}")
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.doubleClicked.connect(self.action_consommer)
        self.table.setMouseTracking(True)
        self.table.setSortingEnabled(True)
        l.addWidget(self.table)

    def show_context_menu(self, pos):
        if not self.table.indexAt(pos).isValid(): return
        self.table.selectRow(self.table.indexAt(pos).row())
        m = QMenu(self)
        m.addAction(self.icon_manager.get_icon(UNICODE_ICONS["CONSUME"], "#e74c3c"), "Consommer Ticket(s)", self.action_consommer)
        m.addAction(self.icon_manager.get_icon(UNICODE_ICONS["RECHARGE"], "#27ae60"), "Recharger Compte", self.action_recharger)
        m.addAction(self.icon_manager.get_icon(UNICODE_ICONS["HISTORY"], "#3498db"), "Voir Historique", self.action_historique)
        m.addSeparator()
        m.addAction(self.icon_manager.get_icon(UNICODE_ICONS["EDIT"], "#f39c12"), "Modifier Usager", self.action_modifier)
        m.addSeparator()
        m.addAction(self.icon_manager.get_icon(UNICODE_ICONS["DELETE"], "#c0392b"), "Supprimer Usager", self.action_supprimer)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def setup_right_stats(self):
        l = QVBoxLayout(self.frame_right)
        l.setContentsMargins(15,20,15,20)
        lbl_stats = QLabel("STATISTIQUES DU JOUR", styleSheet="color:#bdc3c7; font-weight:bold; font-size:9pt;")
        lbl_stats.setAlignment(Qt.AlignmentFlag.AlignRight)
        l.addWidget(lbl_stats)
        l.addSpacing(10)
        self.add_sep(l)
        
        style_label = "color:#bdc3c7; font-size:9pt; font-weight:bold;"
        style_value = "color:white; font-size:9pt; font-weight:bold; margin-left: 2px;" 
        
        h1 = QHBoxLayout(); h1.setSpacing(5); 
        hc = QHBoxLayout(); hc.setContentsMargins(0,0,0,0); hc.setSpacing(2); 
        hc.addWidget(QLabel("Tickets Carte:", styleSheet=style_label))
        self.stat_carte = QLabel("0", styleSheet=style_value)
        hc.addWidget(self.stat_carte)
        h1.addLayout(hc, 1)
        h1.addStretch(1)
        
        ha = QHBoxLayout(); ha.setContentsMargins(0,0,0,0); ha.setSpacing(2); 
        ha.addWidget(QLabel("Avance:", styleSheet=style_label))
        self.stat_avance = QLabel("0", styleSheet=style_value)
        ha.addWidget(self.stat_avance)
        h1.addLayout(ha, 1)
        h1.addStretch()
        l.addLayout(h1)
        
        h2 = QHBoxLayout(); h2.setSpacing(5); h2.addStretch(1); 
        hf = QHBoxLayout(); hf.setContentsMargins(0,0,0,0); hf.setSpacing(2); 
        hf.addWidget(QLabel("Tickets 1ère fois:", styleSheet=style_label))
        self.stat_first = QLabel("0", styleSheet=style_value)
        hf.addWidget(self.stat_first)
        h2.addLayout(hf)
        h2.addStretch(1)
        l.addLayout(h2)
        
        h3 = QHBoxLayout(); h3.setSpacing(5); 
        hh = QHBoxLayout(); hh.setContentsMargins(0,0,0,0); hh.setSpacing(2); 
        hh.addWidget(QLabel("Hommes:", styleSheet=style_label))
        self.stat_h = QLabel("0", styleSheet=style_value)
        hh.addWidget(self.stat_h)
        h3.addLayout(hh, 1)
        h3.addStretch(1)
        
        hff = QHBoxLayout(); hff.setContentsMargins(0,0,0,0); hff.setSpacing(2); 
        hff.addWidget(QLabel("Femmes:", styleSheet=style_label))
        self.stat_f = QLabel("0", styleSheet=style_value)
        hff.addWidget(self.stat_f)
        h3.addLayout(hff, 1)
        h3.addStretch()
        l.addLayout(h3)
        
        h4 = QHBoxLayout(); h4.setSpacing(5); h4.addStretch(1); 
        ht = QHBoxLayout(); ht.setContentsMargins(0,0,0,0); ht.setSpacing(2); 
        ht.addWidget(QLabel("Total:", styleSheet=style_label))
        self.stat_total_passages = QLabel("0", styleSheet=style_value)
        ht.addWidget(self.stat_total_passages)
        h4.addLayout(ht)
        h4.addStretch(1)
        l.addLayout(h4)
        self.add_sep(l)
        
        h_cash = QHBoxLayout(); h_cash.setSpacing(5); h_cash.addStretch(1)
        hcash_in = QHBoxLayout(); hcash_in.setContentsMargins(0,0,0,0); hcash_in.setSpacing(5)
        hcash_in.addWidget(QLabel("Montant encaissé ≃", styleSheet=style_label))
        self.lbl_caisse = QLabel("0.00 €", styleSheet=style_value)
        hcash_in.addWidget(self.lbl_caisse)
        h_cash.addLayout(hcash_in)
        h_cash.addStretch(1)
        l.addLayout(h_cash)
        self.add_sep(l)
        
        def create_chart_block(title, chart_widget):
            v = QVBoxLayout()
            h_top = QHBoxLayout()
            lbl = QLabel(title, styleSheet="color:#bdc3c7; font-weight:bold; font-size:9pt;")
            toggle = ToggleSwitch(width=40, height=22)
            lbl_j = QLabel("J", styleSheet="color:white; font-size:8pt; font-weight:bold;")
            lbl_m = QLabel("M", styleSheet="color:#7f8c8d; font-size:8pt; font-weight:bold;")
            
            def update_labels(checked):
                if checked: 
                    lbl_j.setStyleSheet("color:#7f8c8d; font-size:8pt; font-weight:bold;")
                    lbl_m.setStyleSheet("color:white; font-size:8pt; font-weight:bold;")
                else: 
                    lbl_j.setStyleSheet("color:white; font-size:8pt; font-weight:bold;")
                    lbl_m.setStyleSheet("color:#7f8c8d; font-size:8pt; font-weight:bold;")
            
            toggle.toggled.connect(update_labels)
            h_top.addWidget(lbl_j)
            h_top.addWidget(toggle)
            h_top.addWidget(lbl_m)
            h_top.addStretch()
            h_top.addWidget(lbl)
            v.addLayout(h_top)
            
            h_chart = QHBoxLayout()
            h_chart.addStretch()
            h_chart.addWidget(chart_widget)
            h_chart.addStretch()
            v.addLayout(h_chart)
            l.addLayout(v)
            l.addSpacing(10)
            return toggle
        
        self.chart_sexe = RingChart(self, size=130)
        self.toggle_sexe = create_chart_block("RÉPARTITION SEXE", self.chart_sexe)
        self.toggle_sexe.toggled.connect(self.update_charts)
        
        self.chart_statut = RingChart(self, size=130)
        self.toggle_statut = create_chart_block("RÉPARTITION STATUT", self.chart_statut)
        self.toggle_statut.toggled.connect(self.update_charts)
        
        self.chart_solde = RingChart(self, size=130)
        self.toggle_solde = create_chart_block("RÉPARTITION SOLDE", self.chart_solde)
        self.toggle_solde.toggled.connect(self.update_charts)
        
        self.add_sep(l)
        
        lbl_per = QLabel("BILAN PÉRIODIQUE", styleSheet="color:#bdc3c7; font-weight:bold; font-size:9pt;")
        lbl_per.setAlignment(Qt.AlignmentFlag.AlignRight)
        l.addWidget(lbl_per)
        l.addSpacing(5)
        
        today = date.today()
        first_day = date(today.year, today.month, 1)
        date_style = "QDateEdit { background-color: white; color: black; border: 1px solid #bdc3c7; border-radius: 4px; padding: 2px; }"
        
        h_start = QHBoxLayout()
        lbl_du = QLabel("Du :", styleSheet="color:white;")
        self.date_start = QDateEdit()
        self.date_start.setDisplayFormat("dd/MM/yyyy")
        self.date_start.setCalendarPopup(True)
        self.date_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_start.setDate(QDate(first_day.year, first_day.month, first_day.day))
        self.date_start.setStyleSheet(date_style)
        h_start.addWidget(lbl_du)
        h_start.addWidget(self.date_start)
        l.addLayout(h_start)
        
        h_end = QHBoxLayout()
        lbl_au = QLabel("Au :", styleSheet="color:white;")
        self.date_end = QDateEdit()
        self.date_end.setDisplayFormat("dd/MM/yyyy")
        self.date_end.setCalendarPopup(True)
        self.date_end.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_end.setDate(QDate(today.year, today.month, today.day))
        self.date_end.setStyleSheet(date_style)
        h_end.addWidget(lbl_au)
        h_end.addWidget(self.date_end)
        l.addLayout(h_end)
        
        btn_calc = ModernButton("GÉNÉRER BILAN", AppColors.BTN_VALIDER, self.generate_custom_pdf, 35, 6)
        l.addWidget(btn_calc)
        l.addSpacing(10)
        self.update_charts()

    def update_charts(self):
        today = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")
        
        def get_query_params(is_month_mode): 
            return ("strftime('%Y-%m', date_passage) = ?", [current_month]) if is_month_mode else ("date_passage = ?", [today])
        
        conn = db.get_connection()
        try:
            c = conn.cursor()
            
            clause, params = get_query_params(self.toggle_sexe.isChecked())
            c.execute(f"SELECT sexe, SUM(quantite) FROM view_conso_nettoyees WHERE {clause} GROUP BY sexe", params)
            data_sexe = {k: int(v) if v else 0 for k, v in c.fetchall()}
            self.chart_sexe.set_data(data_sexe, {"H": AppColors.ROW_TUTELLE, "F": AppColors.ROW_AVANCE})
            
            clause, params = get_query_params(self.toggle_statut.isChecked())
            c.execute(f"SELECT statut_au_passage, SUM(quantite) FROM view_conso_nettoyees WHERE {clause} GROUP BY statut_au_passage", params)
            raw_data = {k: int(v) if v else 0 for k, v in c.fetchall()}
            
            data_statut = {"Payés": 0, "Avances": 0, "Tutelles": 0, "1ère fois": 0}
            for key, val in raw_data.items():
                if key in ["Payés", "Pas de crédit", "Anonyme"]: data_statut["Payés"] += val
                elif key == "Avances": data_statut["Avances"] += val
                elif key == "Tutelles": data_statut["Tutelles"] += val
                elif key in ["Offert", "1ère fois"]: data_statut["1ère fois"] += val
                
            self.chart_statut.set_data(data_statut, {"Payés": AppColors.ROW_PAYE, "Avances": AppColors.ROW_AVANCE, "Tutelles": AppColors.ROW_TUTELLE, "1ère fois": AppColors.ROW_OFFERT})
            
            clause, params = get_query_params(self.toggle_solde.isChecked())
            c.execute(f"""SELECT CASE WHEN u.statut = 'Tutelles' THEN 'Négatif' WHEN u.solde >= 0 THEN 'Positif' ELSE 'Négatif' END, COUNT(DISTINCT u.id) FROM usagers u JOIN view_conso_nettoyees v ON u.id = v.usager_id WHERE {clause} GROUP BY CASE WHEN u.statut = 'Tutelles' THEN 'Négatif' WHEN u.solde >= 0 THEN 'Positif' ELSE 'Négatif' END""", params)
            data_solde = dict(c.fetchall())
            c.execute(f"SELECT COUNT(*) FROM view_conso_nettoyees WHERE {clause} AND action IN ('PAYE', '1ERE_FOIS')", params)
            res_anon = c.fetchone()
            nb_anonymes = int(res_anon[0]) if res_anon and res_anon[0] else 0
            data_solde['Positif'] = data_solde.get('Positif', 0) + nb_anonymes
            self.chart_solde.set_data(data_solde, {"Positif": AppColors.ROW_PAYE, "Négatif": AppColors.ROW_AVANCE})
        finally:
            conn.close()

    def update_stats(self): 
        self.update_charts()
    
    def refresh_counters(self):
        today = datetime.now().strftime("%Y-%m-%d")
        stats = StatsService.get_stats_range(today, today)
        
        self.lbl_h.setText(f"H: {stats['total_h']}")
        self.lbl_f.setText(f"F: {stats['total_f']}")
        self.stat_carte.setText(str(stats['tickets_carte'] + stats['tickets_tutelle']))
        self.stat_avance.setText(str(stats['tickets_avance']))
        self.stat_first.setText(str(stats['tickets_1ere_fois']))
        self.stat_h.setText(str(stats['total_h']))
        self.stat_f.setText(str(stats['total_f']))
        self.stat_total_passages.setText(str(stats['total_passages']))
        
        conn = db.get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT detail FROM historique_passages WHERE action='Recharge Compte' AND date_passage=?", (today,))
            total_recharge = 0.0
            for row in c.fetchall():
                try: 
                    total_recharge += float(row[0].replace('€', '').replace('+', '').strip())
                except: 
                    pass
            
            c.execute("SELECT COUNT(*) FROM historique_passages WHERE action='PAYE' AND detail='Anonyme' AND date_passage=?", (today,))
            nb_anon_paye = c.fetchone()[0]
            total_anon = nb_anon_paye * self.ticket_price
            total_caisse = total_recharge + total_anon
            self.lbl_caisse.setText(f"{total_caisse:.2f} €")
        finally:
            conn.close()

    def remove_accents(self, input_str): 
        return "".join([c for c in unicodedata.normalize('NFD', input_str) if not unicodedata.combining(c)]).upper() if input_str else ""

    def calculate_match_score(self, search_text, uid, nom, prenom):
        if not search_text: return 100
        
        search_clean = search_text
        if str(uid) == search_clean: return 100
            
        n_clean = self.remove_accents(nom)
        p_clean = self.remove_accents(prenom)
        full_name = f"{n_clean} {p_clean}"
        inv_name = f"{p_clean} {n_clean}"
        
        if n_clean.startswith(search_clean) or p_clean.startswith(search_clean): return 95
        if full_name.startswith(search_clean) or inv_name.startswith(search_clean): return 90
        if search_clean in full_name or search_clean in inv_name: return 70
            
        ratio_n = SequenceMatcher(None, search_clean, n_clean).ratio()
        ratio_p = SequenceMatcher(None, search_clean, p_clean).ratio()
        ratio_f = SequenceMatcher(None, search_clean, full_name).ratio()
        best_ratio = max(ratio_n, ratio_p, ratio_f)
        
        if best_ratio > 0.6: return int(best_ratio * 60)
        return 0

    def load_data(self):
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        
        try:
            raw_search = self.search.text().strip()
            search_clean = self.remove_accents(raw_search)
            is_searching = len(search_clean) > 0
            
            conn = db.get_connection()
            try:
                c = conn.cursor()
                c.execute("SELECT * FROM usagers")
                rows = c.fetchall()
            finally:
                conn.close()
            
            bg_map = {"Payés": AppColors.ROW_PAYE, "Avances": AppColors.ROW_AVANCE, "Tutelles": AppColors.ROW_TUTELLE, "Pas de crédit": AppColors.ROW_NOCREDIT}
            display_list = []
            
            for r in rows:
                uid, n, p, s, st, sol, tick, passg = r[:8]
                comment = r[9] if len(r) > 9 else ""
                
                calc_sol = tick * self.ticket_price
                real_st = st
                if st in ["Payés", "Avances"]:
                    if tick < 0: real_st = "Avances"
                    elif tick > 0: real_st = "Payés"
                
                if not self.filters.get(real_st, True): continue
                if not self.filters.get(s, True): continue
                
                is_positive = calc_sol >= 0
                is_negative = calc_sol < 0
                if not self.filters.get("Positif", True) and is_positive: continue
                if not self.filters.get("Négatif", True) and is_negative: continue
                
                score = self.calculate_match_score(search_clean, uid, n, p)
                if is_searching and score == 0: continue
                    
                display_list.append((score, n, r, real_st, calc_sol, bg_map.get(real_st, "white")))
            
            display_list.sort(key=lambda x: (-x[0], x[1]))
            
            vis = 0
            for score, name_sort, r, real_st, calc_sol, bg_color in display_list:
                vis += 1
                uid, n, p, s, st, sol, tick, passg = r[:8]
                comment = r[9] if len(r) > 9 else ""
                
                idx = self.table.rowCount()
                self.table.insertRow(idx)
                bg = QColor(bg_color)
                
                tooltip_text = f"<b>{n} {p}</b> ({s})<br>Statut: {real_st}<br>Solde: {calc_sol:.2f} € ({tick} tickets)<br>Dernier passage: {passg}<br>-----------------<br><i>{comment if comment else 'Aucun commentaire'}</i>"
                
                items_list = [uid, n, p, s, real_st, f"{calc_sol:.2f} €", tick, comment, passg]
                
                for i, val in enumerate(items_list):
                    if i in [0, 5, 6]: it = NumericTableWidgetItem(str(val))
                    else: it = QTableWidgetItem(str(val))
                    
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    it.setBackground(bg)
                    it.setToolTip(tooltip_text)
                    self.table.setItem(idx, i, it)
            
            self.lbl_count.setText(f"{vis} usager(s) visible(s)")
            self.refresh_counters()
            self.table.setSortingEnabled(not is_searching)
            
        finally:
            self.table.setUpdatesEnabled(True)

# ============================================================================
# FONCTION UTILITAIRE (HORS CLASSE)
# ============================================================================
def monitor_and_delete(file_path):
    """Surveille un fichier temporaire et le supprime quand il est libéré."""
    time.sleep(2)
    start_time = time.time()
    while time.time() - start_time < 3600:
        try:
            if os.path.exists(file_path): 
                os.remove(file_path)
                break
            else: 
                break
        except PermissionError: 
            time.sleep(1)
        except Exception: 
            break

# ============================================================================
# POINT D'ENTRÉE (EXECUTION)
# ============================================================================
if __name__ == "__main__":
    if sys.platform == 'win32': 
        myappid = 'shadok.gestionresto.version.1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)    
    
    db.init_db()
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    app.setStyleSheet(GLOBAL_STYLESHEET)
    
    # --- DOUBLE VERIFICATION : Forçage de la Palette pour QToolTip ---
    # Cette étape garantit que le fond est sombre et le texte blanc, même si le CSS échoue
    palette = QToolTip.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(AppColors.MENU_BG))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(Qt.GlobalColor.white))
    QToolTip.setPalette(palette)
    # ----------------------------------------------------------------
    
    if os.path.exists(ICON_PATH): 
        app.setWindowIcon(QIcon(ICON_PATH))
    
    window = MainWindow()    
    window.show()    
    sys.exit(app.exec())
import sqlite3
import random
import os
import sys
import subprocess
import shutil
import glob
from datetime import datetime

from Core.workers import UpdateWorker

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, 
    QGridLayout, QFileDialog, QFrame, QMessageBox, QSizePolicy, QLayout,
    QCheckBox 
)
from PyQt6.QtCore import Qt, QTimer, QSize, QEvent
from PyQt6.QtGui import QMovie, QPixmap, QIcon

import database as db
from constants import (
    AppColors, DB_FILE, SHADOK_GIF_PATH, APP_VERSION, PDF_FILENAME
)

from UI.widgets import ModernButton, ToggleSwitch

class BaseDialog(QDialog):
    def __init__(self, parent, title=None, w=None, h=None):
        super().__init__(parent)
        self.parent_app = parent
        if title: 
            self.setWindowTitle(title)
        if w and h: 
            self.setFixedSize(w, h)
        
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(25, 25, 25, 25)
        self.layout.setSpacing(15)

class CustomMessageBox(BaseDialog):
    def __init__(self, parent, title, message, error=False, success=False):
        super().__init__(parent, title, 400, 200)
        
        lbl_msg = QLabel(message)
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet(f"font-size: 11pt; color: #2c3e50; font-weight: bold;")
        lbl_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl_msg)
        self.layout.addStretch()
        
        h_btns = QHBoxLayout()
        
        if success:
            btn_ok = ModernButton("OK", "#27ae60", self.accept, 35, 6)
            h_btns.addWidget(btn_ok)
        elif error:
            btn_ok = ModernButton("OK", "#e74c3c", self.accept, 35, 6)
            h_btns.addWidget(btn_ok)
        else:
            btn_no = ModernButton("NON", "#95a5a6", self.reject, 35, 6)
            btn_yes = ModernButton("OUI", "#27ae60", self.accept, 35, 6)
            h_btns.addWidget(btn_no)
            h_btns.addWidget(btn_yes)
        
        self.layout.addLayout(h_btns)

class ConfirmationDialog(BaseDialog):
    def __init__(self, parent, title, message):
        super().__init__(parent, title, 350, 180)
        
        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 11pt; color: #2c3e50; margin-bottom: 10px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl)
        
        h_btns = QHBoxLayout()
        btn_no = ModernButton("ANNULER", "#95a5a6", self.reject, 35, 6)
        btn_yes = ModernButton("SUPPRIMER", "#e74c3c", self.accept, 35, 6)
        h_btns.addWidget(btn_no)
        h_btns.addWidget(btn_yes)
        self.layout.addLayout(h_btns)

class PdfSuccessDialog(BaseDialog):
    def __init__(self, parent, filename):
        super().__init__(parent, "Export PDF Réussi", 400, 200)
        self.layout.addWidget(QLabel("✅ Le fichier PDF a été généré avec succès.", styleSheet="color: #27ae60; font-weight: bold; font-size: 11pt;"))
        self.layout.addWidget(QLabel(f"Fichier : {filename}", styleSheet="color: #2c3e50;"))
        
        h = QHBoxLayout()
        btn_no = ModernButton("NON", "#95a5a6", self.reject, 35, 6)
        btn_yes = ModernButton("OUI", AppColors.BTN_NEW_BG, self.accept, 35, 6)
        btn_yes.setDefault(True)
        h.addWidget(btn_no)
        h.addWidget(btn_yes)
        self.layout.addLayout(h)

class ChangelogDialog(BaseDialog):
    def __init__(self, parent, version, text):
        super().__init__(parent, f"Quoi de neuf en v{version} ?", 500, 400)
        
        lbl_title = QLabel("🎉 MISE À JOUR EFFECTUÉE !")
        lbl_title.setStyleSheet(f"font-size: 14pt; font-weight: bold; color: {AppColors.BTN_NEW_BG};")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl_title)
        
        lbl_sub = QLabel(f"Voici les nouveautés de la version {version} :")
        lbl_sub.setStyleSheet(f"color: {AppColors.STATS_BG}; font-style: italic;")
        self.layout.addWidget(lbl_sub)
        
        self.txt_display = QTextEdit()
        self.txt_display.setReadOnly(True)
        self.txt_display.setPlainText(text)
        
        self.txt_display.setStyleSheet(f"""
            QTextEdit {{ 
                background-color: white; 
                border: 2px solid {AppColors.SEARCH_BORDER}; 
                border-radius: 6px; 
                padding: 10px; 
                font-family: 'Segoe UI', sans-serif; 
                font-size: 10pt;
                color: {AppColors.MENU_BG};
            }}
            QTextEdit:focus {{
                border: 2px solid {AppColors.SEARCH_BORDER};
            }}
        """)
        self.layout.addWidget(self.txt_display)
        
        btn_ok = ModernButton("SUPER !", AppColors.BTN_NEW_BG, self.accept, 40, 6)
        self.layout.addWidget(btn_ok)

class AProposDialog(BaseDialog):
    def __init__(self, parent, update_available=None, download_callback=None):
        super().__init__(parent, "À Propos", 420, 650)
        self.download_callback = download_callback
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(0)
        
        self.img_container = QLabel()
        self.img_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_container.setFixedSize(340, 250)
        self.img_container.setCursor(Qt.CursorShape.PointingHandCursor)
        self.img_container.installEventFilter(self)
        self.img_container.setStyleSheet(f"QLabel {{ background-color: white; border-radius: 12px; border: 1px solid #ecf0f1; }}")
        
        if os.path.exists(SHADOK_GIF_PATH):
            self.movie = QMovie(SHADOK_GIF_PATH)
            self.movie.setScaledSize(QSize(180, 240))
            self.img_container.setMovie(self.movie)
            self.movie.start()
        else:
            self.img_container.setText("🦆")
            
        h_img = QHBoxLayout(); h_img.addStretch(); h_img.addWidget(self.img_container); h_img.addStretch()
        self.layout.addLayout(h_img); self.layout.addSpacing(25)
        
        lbl_title = QLabel(f"<div style='line-height: 120%;'><span style='font-size: 16pt; font-weight: 800; color: {AppColors.MENU_BG};'>TABLEAU DE BORD</span><br><span style='font-size: 13pt; font-weight: 600; color: {AppColors.STATS_BG};'>RESTAURANT SOCIAL</span></div>")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl_title); self.layout.addSpacing(15)
        
        lbl_channel = QLabel("Canal de mise à jour :")
        lbl_channel.setStyleSheet("color: #7f8c8d; font-size: 10pt;")
        
        self.combo_channel = QComboBox()
        self.combo_channel.addItems(["Stable (Recommandé)", "Bêta (Test)"])
        self.combo_channel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_channel.setStyleSheet(f"QComboBox {{ border: 1px solid #bdc3c7; border-radius: 4px; padding: 2px 10px; color: {AppColors.MENU_BG}; }} QComboBox:focus {{ border: 2px solid {AppColors.BTN_EXPORT_BG}; }}")
        
        current_channel = db.get_config('UPDATE_CHANNEL', 'stable')
        if current_channel == 'beta': self.combo_channel.setCurrentIndex(1)
        else: self.combo_channel.setCurrentIndex(0)
            
        self.combo_channel.currentIndexChanged.connect(self.on_channel_change)
        
        h_chan = QHBoxLayout(); h_chan.addStretch(); h_chan.addWidget(lbl_channel); h_chan.addWidget(self.combo_channel); h_chan.addStretch()
        self.layout.addLayout(h_chan); self.layout.addSpacing(15)
        
        h_ver = QHBoxLayout(); h_ver.setSpacing(10); h_ver.addStretch()
        
        self.lbl_ver = QLabel(f"Version {APP_VERSION}")
        self.lbl_ver.setStyleSheet("background-color: #ecf0f1; color: #7f8c8d; border-radius: 10px; padding: 4px 15px; font-size: 10pt; font-weight: bold;")
        h_ver.addWidget(self.lbl_ver)
        
        self.lbl_arrow = QLabel("➜")
        self.lbl_arrow.setStyleSheet("color: #95a5a6; font-size: 14pt; font-weight: bold;")
        h_ver.addWidget(self.lbl_arrow)
        
        self.btn_update = QPushButton("") 
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.setStyleSheet(f"background-color: {AppColors.BTN_NEW_BG}; color: white; border-radius: 10px; padding: 4px 15px; font-size: 10pt; font-weight: bold; border: none;")
        self.btn_update.clicked.connect(self.start_download)
        h_ver.addWidget(self.btn_update)
        
        if update_available:
            self.btn_update.setText(f"v{update_available}")
            self.lbl_arrow.setVisible(True)
            self.btn_update.setVisible(True)
        else:
            self.lbl_arrow.setVisible(False)
            self.btn_update.setVisible(False)
            
        h_ver.addStretch(); self.layout.addLayout(h_ver); self.layout.addSpacing(20)
        
        self.progress_bar = QLabel(""); self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter); self.progress_bar.setStyleSheet("color: #27ae60; font-weight: bold;"); self.progress_bar.setVisible(False)
        self.layout.addWidget(self.progress_bar); sep = QFrame(); sep.setFixedHeight(1); sep.setStyleSheet("background-color: #e0e0e0;"); self.layout.addWidget(sep); self.layout.addSpacing(15)
        
        v_credits = QVBoxLayout(); v_credits.setSpacing(4)
        lbl_dev = QLabel("Développement & Conception"); lbl_dev.setStyleSheet("color: #95a5a6; font-size: 8pt; text-transform: uppercase; letter-spacing: 1px;"); lbl_dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_dev_name = QLabel("SHaDoK"); lbl_dev_name.setStyleSheet(f"color: {AppColors.MENU_BG}; font-size: 11pt; font-weight: bold; margin-bottom: 2px;"); lbl_dev_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sujet = "Demande de support pour l'application Tableau de bord - Restaurant Social"; sujet_encoded = sujet.replace(" ", "%20").replace("'", "%27")
        lbl_support = QLabel(f"Support : <a href='mailto:jesthp@gmail.com?subject={sujet_encoded}' style='color: #3498db; text-decoration: none; font-weight:bold;'>jesthp@gmail.com</a>"); lbl_support.setOpenExternalLinks(True); lbl_support.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl_support.setStyleSheet("font-size: 10pt; color: #7f8c8d;")
        v_credits.addWidget(lbl_dev); v_credits.addWidget(lbl_dev_name); v_credits.addWidget(lbl_support); self.layout.addLayout(v_credits); self.layout.addStretch()
        
        btn_close = ModernButton("FERMER", "#95a5a6", self.accept, 40, 6); h_btn = QHBoxLayout(); h_btn.setContentsMargins(60, 0, 60, 0); h_btn.addWidget(btn_close); self.layout.addLayout(h_btn)
        
        self.shake_timer = QTimer(self); self.shake_timer.timeout.connect(self.do_shake); self.shake_duration_timer = QTimer(self); self.shake_duration_timer.setSingleShot(True); self.shake_duration_timer.timeout.connect(self.stop_shake); self.start_vibration_sequence()

    def on_channel_change(self, index):
        channel = 'beta' if index == 1 else 'stable'
        db.set_config('UPDATE_CHANNEL', channel)
        self.lbl_arrow.setVisible(False)
        self.btn_update.setVisible(False)
        self.lbl_ver.setText("Recherche en cours...")
        self.lbl_ver.setStyleSheet("background-color: #f39c12; color: white; border-radius: 10px; padding: 4px 15px; font-size: 10pt; font-weight: bold;")
        self.temp_worker = UpdateWorker(channel=channel)
        self.temp_worker.update_available.connect(self.on_new_version_found)
        self.temp_worker.finished.connect(self.on_search_finished)
        self.temp_worker.start()

    def on_new_version_found(self, version):
        self.lbl_arrow.setVisible(True)
        self.btn_update.setText(f"v{version}")
        self.btn_update.setVisible(True)

    def on_search_finished(self):
        self.lbl_ver.setText(f"Version {APP_VERSION}")
        self.lbl_ver.setStyleSheet("background-color: #ecf0f1; color: #7f8c8d; border-radius: 10px; padding: 4px 15px; font-size: 10pt; font-weight: bold;")

    def start_download(self): self.progress_bar.setVisible(True); self.progress_bar.setText("Initialisation..."); self.download_callback(self) if self.download_callback else None
    def update_progress(self, percent): self.progress_bar.setText(f"Téléchargement : {percent}%")
    def eventFilter(self, source, event): 
        if source == self.img_container and event.type() == QEvent.Type.MouseButtonDblClick:
            self.start_vibration_sequence(); return True
        return super().eventFilter(source, event)
    def start_vibration_sequence(self): self.shake_timer.stop(); self.shake_duration_timer.stop(); self.shake_timer.start(40); self.shake_duration_timer.start(1500)
    def do_shake(self): range_px = 4; x_off = random.randint(-range_px, range_px); y_off = random.randint(-range_px, range_px); self.img_container.setStyleSheet(f"QLabel {{ background-color: white; border-radius: 12px; border: 1px solid #ecf0f1; padding: {10+y_off}px {10-x_off}px {10-y_off}px {10+x_off}px; }}")
    def stop_shake(self): self.shake_timer.stop(); self.img_container.setStyleSheet("QLabel { background-color: white; border-radius: 12px; border: 1px solid #ecf0f1; padding: 10px; }")

class PrixDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Configuration Prix", 350, 200)
        self.layout.addWidget(QLabel("PRIX ACTUEL DU TICKET (€) :", styleSheet="font-weight:bold; font-size:11pt;"))
        self.entry = QLineEdit(f"{db.get_ticket_price():.2f}")
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.entry)
        self.entry.returnPressed.connect(self.save)
        
        self.layout.addSpacing(20)
        btn = ModernButton("ENREGISTRER", AppColors.BTN_NEW_BG, self.save, 35, 6)
        btn.setDefault(True)
        self.layout.addWidget(btn)

    def save(self):
        try:
            p = float(self.entry.text().replace(',', '.'))
            if p <= 0: raise ValueError
            db.set_ticket_price(p)
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("UPDATE usagers SET solde = ticket * ?", (p,))
            conn.commit()
            conn.close()
            self.parent_app.load_data()
            self.accept()
        except ValueError: 
            CustomMessageBox(self, "Erreur", "Le prix doit être un nombre valide supérieur à 0.", error=True).exec()

class ExportSupDialog(BaseDialog):
    def __init__(self, parent, filename):
        super().__init__(parent, "Export Supplémentaire", 500, 250)
        self.filename = filename
        self.selected_path = ""
        self.layout.setSpacing(20)
        self.layout.setContentsMargins(30, 30, 30, 30)
        
        h_toggle = QHBoxLayout()
        h_toggle.setSpacing(15)
        h_toggle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        self.toggle_switch = ToggleSwitch(inactive_color="#bdc3c7")
        
        # --- MODIFICATION ICI ---
        # On garde le bouton pour le texte cliquable, mais on le stocke dans self pour le modifier
        self.btn_label = QPushButton("Activer la copie de sauvegarde (ex: Clé USB)")
        self.btn_label.setCursor(Qt.CursorShape.PointingHandCursor)
        # Le clic sur le texte active le toggle
        self.btn_label.clicked.connect(self.toggle_switch.toggle)
        
        h_toggle.addWidget(self.toggle_switch)
        h_toggle.addWidget(self.btn_label)
        self.layout.addLayout(h_toggle)
        
        lbl_dest = QLabel("Dossier de destination :")
        lbl_dest.setStyleSheet("color: #34495e; font-size: 10pt;")
        self.layout.addWidget(lbl_dest)
        
        h_path = QHBoxLayout()
        h_path.setSpacing(5)
        self.inp_path = QLineEdit(db.get_config('EXPORT_SUP_PATH'))
        self.inp_path.setPlaceholderText("Chemin du dossier...")
        self.inp_path.setFixedHeight(45)
        
        self.btn_browse = QPushButton("📂")
        self.btn_browse.setFixedSize(60, 45)
        self.btn_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_browse.clicked.connect(self.browse)
        
        h_path.addWidget(self.inp_path)
        h_path.addWidget(self.btn_browse)
        self.layout.addLayout(h_path)
        self.layout.addStretch()
        
        h_btns = QHBoxLayout()
        h_btns.setSpacing(15)
        btn_cancel = ModernButton("ANNULER", "#95a5a6", self.reject, 40, 6)
        self.btn_valid = ModernButton("VALIDER", "#27ae60", self.save_and_accept, 40, 6)
        self.btn_valid.setDefault(True)
        h_btns.addWidget(btn_cancel)
        h_btns.addWidget(self.btn_valid)
        self.layout.addLayout(h_btns)
        
        # Connexion du signal toggled
        self.toggle_switch.toggled.connect(self.toggle_inputs)
        
        # Initialisation de l'état
        is_enabled = db.get_config('EXPORT_SUP_ENABLED') == '1'
        self.toggle_switch.setChecked(is_enabled)
        # Force la mise à jour visuelle immédiate
        self.toggle_inputs(is_enabled)

    def toggle_inputs(self, checked):
        self.inp_path.setEnabled(checked)
        self.btn_browse.setEnabled(checked)
        
        # --- GESTION COULEUR DU TEXTE ---
        if checked:
            # ACTIF : Texte foncé, Input blanc
            self.btn_label.setStyleSheet("QPushButton { text-align: left; border: none; background: transparent; font-weight: bold; color: #2c3e50; font-size: 10pt; }")
            self.inp_path.setStyleSheet("QLineEdit { border: 1px solid #bdc3c7; border-radius: 4px; padding-left: 10px; background-color: white; color: black; } QLineEdit:focus { border: 2px solid #27ae60; }")
            self.btn_browse.setStyleSheet("QPushButton { background-color: #3498db; border: none; border-radius: 4px; font-size: 16px; color: white; } QPushButton:hover { background-color: #2980b9; }")
        else:
            # INACTIF : Texte gris, Input grisé
            self.btn_label.setStyleSheet("QPushButton { text-align: left; border: none; background: transparent; font-weight: bold; color: #bdc3c7; font-size: 10pt; }")
            self.inp_path.setStyleSheet("QLineEdit { border: 1px solid #dcdcdc; border-radius: 4px; padding-left: 10px; background-color: #f0f0f0; color: #a0a0a0; }")
            self.btn_browse.setStyleSheet("QPushButton { background-color: #e0e0e0; border: none; border-radius: 4px; font-size: 16px; color: #a0a0a0; }")

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choisir un dossier")
        if d: 
            self.selected_path = d
            self.inp_path.setText(d)

    def save_and_accept(self):
        if self.toggle_switch.isChecked() and not self.inp_path.text().strip(): 
            return CustomMessageBox(self, "Erreur", "Veuillez sélectionner un dossier.", error=True).exec()
        
        db.set_config('EXPORT_SUP_ENABLED', '1' if self.toggle_switch.isChecked() else '0')
        db.set_config('EXPORT_SUP_PATH', self.inp_path.text().strip())
        self.accept()

class ImportMasseDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Importation en masse", 500, 500)
        self.ticket_price = db.get_ticket_price()
        
        self.layout.addWidget(QLabel("IMPORTATION UTILISATEURS", styleSheet="font-weight:bold; font-size:12pt; color:#2c3e50;"))
        self.layout.addWidget(QLabel("Coller la liste (NOM [PRENOM] TICKET [COMMENTAIRE]) :"))
        
        self.txt_input = QPlainTextEdit()
        self.txt_input.setPlaceholderText("DUPONT JEAN 5\nMARTIN 2\nDURAND PIERRE 3 TUTEUR UDAF\n...")
        self.txt_input.setStyleSheet("font-size:11pt;")
        self.txt_input.setMinimumHeight(250)
        self.layout.addWidget(self.txt_input)
        
        h_stat = QHBoxLayout()
        h_stat.addWidget(QLabel("Statut pour nouveaux :"))
        self.combo_statut = QComboBox()
        self.combo_statut.addItems(["Payés", "Avances", "Tutelles", "Pas de crédit"])
        h_stat.addWidget(self.combo_statut)
        self.layout.addLayout(h_stat)
        
        h_btns = QHBoxLayout()
        h_btns.addWidget(ModernButton("ANNULER", "#95a5a6", self.reject, 35, 6))
        btn_ok = ModernButton("IMPORTER", AppColors.BTN_NEW_BG, self.process_import, 35, 6)
        btn_ok.setDefault(True)
        h_btns.addWidget(btn_ok)
        self.layout.addLayout(h_btns)
    
    def detect_gender(self, prenom): 
        return 'F' if prenom.lower().endswith(('e', 'a', 'ine', 'ette')) else 'H'
    
    def process_import(self):
        text = self.txt_input.toPlainText().strip()
        if not text: 
            return CustomMessageBox(self, "Erreur", "La zone de saisie est vide.", error=True).exec()
            
        dropdown_statut = self.combo_statut.currentText()
        lines = text.split('\n')
        
        conn = db.get_connection()
        c = conn.cursor()
        
        count_created = 0
        count_updated = 0
        
        try:
            for line in lines:
                parts = line.split()
                if len(parts) < 2: continue
                
                ticket_index = -1
                ticket_quantity = 0
                for i in range(1, len(parts)):
                    if parts[i].lstrip('-').isdigit(): 
                        ticket_index = i
                        ticket_quantity = abs(int(parts[i]))
                        break 
                
                if ticket_index == -1: continue 
                
                name_parts = parts[:ticket_index]
                comment_parts = parts[ticket_index+1:]
                comment = " ".join(comment_parts)
                
                if not name_parts: continue
                
                if len(name_parts) == 1: 
                    nom = name_parts[0].upper()
                    prenom = ""
                else: 
                    nom = name_parts[0].upper()
                    prenom = " ".join(name_parts[1:]).capitalize()
                
                sexe = self.detect_gender(prenom if prenom else nom)
                
                c.execute("SELECT id, ticket, solde, statut, commentaire FROM usagers WHERE nom=? AND prenom=?", (nom, prenom))
                existing = c.fetchone()
                
                final_tickets = 0
                user_statut = ""
                
                if existing:
                    uid, old_t, old_s, current_statut, old_com = existing
                    user_statut = current_statut
                    new_com = comment if comment else old_com
                    
                    if current_statut in ["Avances", "Tutelles"]: 
                        final_tickets = -ticket_quantity
                    else: 
                        final_tickets = ticket_quantity
                    
                    new_t = old_t + final_tickets
                    new_s = old_s + (final_tickets * self.ticket_price)
                    
                    c.execute("UPDATE usagers SET ticket=?, solde=?, commentaire=? WHERE id=?", (new_t, new_s, new_com, uid))
                    count_updated += 1
                    action_txt = f"Import (Ajout {final_tickets})"
                    
                else:
                    user_statut = dropdown_statut
                    if user_statut in ["Avances", "Tutelles"]: 
                        final_tickets = -ticket_quantity
                    else: 
                        final_tickets = ticket_quantity
                    
                    solde_val = final_tickets * self.ticket_price
                    nid = db.get_next_usager_id(c)
                    
                    c.execute("INSERT INTO usagers (id, nom, prenom, sexe, statut, solde, ticket, passage, photo_filename, commentaire) VALUES (?,?,?,?,?,?,?,?,?,?)", (nid, nom, prenom, sexe, user_statut, solde_val, final_tickets, "", "", comment))
                    db.set_config('LAST_USED_ID', str(nid))
                    uid = nid
                    count_created += 1
                    action_txt = "Import (Création)"
                
                c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, ?, ?, ?, ?)", (action_txt, str(final_tickets), sexe, uid, datetime.now().strftime("%Y-%m-%d"), user_statut))
            
            conn.commit()
            
            CustomMessageBox(self, "Succès", f"Import terminé.\nCréés : {count_created}\nMis à jour : {count_updated}", error=False).exec()
            
            self.parent_app.load_data()
            self.parent_app.refresh_counters()
            self.parent_app.update_stats()
            self.parent_app.generate_pdf(silent_mode=True)
            self.accept()
            
        except Exception as e: 
            conn.rollback()
            QMessageBox.critical(self, "Erreur", str(e))
        finally: 
            conn.close()

class NouveauUsagerDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Nouvel Usager", 400, 400)
        
        grid = QGridLayout()
        grid.setVerticalSpacing(15)
        grid.setColumnStretch(1, 1)
        
        self.i_nom = QLineEdit()
        self.i_nom.setPlaceholderText("Ex: DUPONT")
        self.i_pre = QLineEdit()
        self.i_pre.setPlaceholderText("Ex: Jean")
        self.i_sex = QComboBox()
        self.i_sex.addItems(["H", "F"])
        self.i_sta = QComboBox()
        self.i_sta.addItems(["Payés", "Avances", "Tutelles", "Pas de crédit"])
        self.i_com = QLineEdit()
        self.i_com.setPlaceholderText("Ex: Tuteur M. X")
        
        for w in [self.i_nom, self.i_pre, self.i_sex, self.i_sta, self.i_com]: 
            w.setStyleSheet("QLineEdit, QComboBox { padding: 5px; background: #ffffff; border: 2px solid #bdc3c7; color: black; border-radius: 6px; } QLineEdit:focus, QComboBox:focus { border: 2px solid #e67e22; }")
        
        def add_row(row_idx, label_text, widget):
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row_idx, 0, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(widget, row_idx, 1)

        add_row(0, "Nom :", self.i_nom)
        add_row(1, "Prénom :", self.i_pre)
        add_row(2, "Sexe :", self.i_sex)
        add_row(3, "Statut :", self.i_sta)
        add_row(4, "Commentaire :", self.i_com)
        
        self.layout.addLayout(grid)
        
        self.i_nom.returnPressed.connect(self.i_pre.setFocus)
        self.i_pre.returnPressed.connect(self.save)
        self.i_com.returnPressed.connect(self.save)
        
        self.layout.addSpacing(20)
        h_btns = QHBoxLayout()
        h_btns.addWidget(ModernButton("ANNULER", "#95a5a6", self.reject, 35, 6))
        btn = ModernButton("ENREGISTRER", AppColors.BTN_NEW_BG, self.save, 35, 6)
        btn.setDefault(True)
        h_btns.addWidget(btn)
        self.layout.addLayout(h_btns)

    def save(self):
        n = self.i_nom.text().upper().strip()
        p = self.i_pre.text().capitalize().strip()
        if not n and not p: 
            return CustomMessageBox(self, "Attention", "Nom ou Prénom requis.", error=True).exec()
        
        conn = None
        try:
            conn = db.get_connection()
            c = conn.cursor()
            
            # Vérification doublon
            c.execute("SELECT id FROM usagers WHERE nom=? AND prenom=?", (n,p))
            if c.fetchone(): 
                return CustomMessageBox(self, "Doublon", "Usager existant", error=True).exec()
            
            # Récupération ID
            nid = db.get_next_usager_id(c)
            user_statut = self.i_sta.currentText()
            
            # 1. Insertion de l'usager
            c.execute("INSERT INTO usagers (id,nom,prenom,sexe,statut,solde,ticket,passage,photo_filename, commentaire) VALUES (?,?,?,?,?,0,0,'','',?)", (nid, n, p, self.i_sex.currentText(), user_statut, self.i_com.text()))
            
            # 2. Mise à jour config
            c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", ('LAST_USED_ID', str(nid)))
            
            # 3. Historique
            c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, ?, ?, ?, ?)", ('Création usager', 'Initialisation', self.i_sex.currentText(), nid, datetime.now().strftime("%Y-%m-%d"), user_statut))
            
            conn.commit()
            
            # Actions UI différées
            QTimer.singleShot(50, lambda: self.post_save_actions(nid))
            
        except Exception as e: 
            if conn: conn.rollback()
            CustomMessageBox(self, "Erreur", str(e), error=True).exec()
        finally:
            if conn:
                conn.close()

    def post_save_actions(self, nid):
        self.parent_app.load_data()
        self.parent_app.select_row(nid)
        self.parent_app.update_stats()
        self.parent_app.generate_pdf(silent_mode=True)
        self.accept()

class ModifierUsagerDialog(BaseDialog):
    def __init__(self, parent, uid):
        super().__init__(parent, "Modifier Usager", 400, 500)
        self.uid = uid
        self.ticket_price = db.get_ticket_price()
        
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT nom, prenom, sexe, statut, solde, commentaire FROM usagers WHERE id=?", (uid,))
        self.data = c.fetchone()
        conn.close()
        
        if not self.data: 
            self.reject()
            return
        
        lbl = QLabel(f"MODIFIER: {self.data[1]} {self.data[0]}")
        lbl.setStyleSheet("font-size: 14pt; font-weight: bold; color: #2c3e50;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl)
        self.layout.addSpacing(10)
        
        grid = QGridLayout()
        grid.setVerticalSpacing(15)
        grid.setColumnStretch(1, 1)

        self.inp_nom = QLineEdit(self.data[0])
        self.inp_prenom = QLineEdit(self.data[1])
        self.inp_sexe = QComboBox()
        self.inp_sexe.addItems(["H", "F"])
        self.inp_sexe.setCurrentText(self.data[2])
        
        self.inp_statut = QComboBox()
        self.inp_statut.addItems(["Payés", "Avances", "Tutelles", "Pas de crédit"])
        self.inp_statut.setCurrentText(self.data[3])
        
        self.inp_solde = QLineEdit(f"{self.data[4]:.2f}")
        self.inp_com = QLineEdit(self.data[5] if self.data[5] else "")
        
        for w in [self.inp_nom, self.inp_prenom, self.inp_sexe, self.inp_statut, self.inp_solde, self.inp_com]: 
            w.setStyleSheet("QLineEdit, QComboBox { padding: 5px; background: #ffffff; border: 2px solid #bdc3c7; color: black; border-radius: 6px; } QLineEdit:focus, QComboBox:focus { border: 2px solid #e67e22; }")
        
        def add_row(row_idx, label_text, widget):
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, row_idx, 0, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(widget, row_idx, 1)

        add_row(0, "Nom :", self.inp_nom)
        add_row(1, "Prénom :", self.inp_prenom)
        add_row(2, "Sexe :", self.inp_sexe)
        add_row(3, "Statut :", self.inp_statut)
        add_row(4, "Solde (€) :", self.inp_solde)
        add_row(5, "Commentaire :", self.inp_com)
        
        self.layout.addLayout(grid)
        
        self.inp_nom.returnPressed.connect(self.save)
        self.inp_prenom.returnPressed.connect(self.save)
        self.inp_solde.returnPressed.connect(self.save)
        
        self.layout.addSpacing(20)
        btn = ModernButton("ENREGISTRER", AppColors.BTN_NEW_BG, self.save, 35, 6)
        btn.setDefault(True)
        self.layout.addWidget(btn)

    def save(self):
        nn = self.inp_nom.text().upper().strip()
        np = self.inp_prenom.text().capitalize().strip()
        ns = self.inp_sexe.currentText()
        nst = self.inp_statut.currentText()
        
        try: 
            nsol = float(self.inp_solde.text().replace(',', '.'))
        except ValueError: 
            return CustomMessageBox(self, "Erreur", "Le solde doit être un nombre valide.", error=True).exec()
            
        ntick = round(nsol / self.ticket_price)
        
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("UPDATE usagers SET nom=?, prenom=?, sexe=?, statut=?, solde=?, ticket=?, commentaire=? WHERE id=?", (nn, np, ns, nst, nsol, ntick, self.inp_com.text(), self.uid))
        c.execute("UPDATE historique_passages SET sexe=? WHERE usager_id=?", (ns, self.uid))
        c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, ?, ?, ?, ?)", ('Modification usager', "Edition fiche", ns, self.uid, datetime.now().strftime("%Y-%m-%d"), self.data[3]))
        
        conn.commit()
        conn.close()
        
        self.parent_app.load_data()
        self.parent_app.update_stats()
        self.parent_app.generate_pdf(silent_mode=True)
        self.accept()

class ConsommerTicketDialog(BaseDialog):
    def __init__(self, parent, uid, name, tickets, status):
        super().__init__(parent, "Consommation", 300, 250)
        self.uid = uid
        self.tickets = tickets
        self.status = status
        
        lbl = QLabel(f"Ticket pour : {name}")
        lbl.setStyleSheet("font-weight: bold; font-size: 10pt;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl)
        
        self.layout.addWidget(QLabel("Nombre de tickets :"))
        self.entry = QLineEdit("1")
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.entry)
        
        self.entry.returnPressed.connect(self.process)
        self.layout.addSpacing(20)
        
        btn = ModernButton("VALIDER", AppColors.BTN_VALIDER, self.process, 35, 6)
        btn.setDefault(True)
        self.layout.addWidget(btn)
        
        self.entry.setFocus()
        QTimer.singleShot(0, self.entry.selectAll)

    def process(self):
        try:
            txt = self.entry.text().strip()
            if not txt.isdigit(): raise ValueError
            num = int(txt)
            if num <= 0: raise ValueError
            if self.status == "Pas de crédit" and (self.tickets - num) < 0: 
                return CustomMessageBox(self, "Attention", "Solde insuffisant pour ce statut.", error=True).exec()
            
            # --- UNDO : Capture Etat AVANT ---
            prev_state = {self.uid: {'solde': self.tickets * db.get_ticket_price(), 'ticket': self.tickets, 'statut': self.status}}
            
            nt = self.tickets - num
            current = self.tickets
            tickets_to_record = []
            
            if self.status == "Tutelles": 
                tickets_to_record.append((num, "Tutelles"))
            elif self.status == "Pas de crédit": 
                tickets_to_record.append((num, "Pas de crédit"))
            elif self.status in ["Payés", "Avances"]:
                if current > 0: 
                    nb_paye = min(num, current)
                    nb_avance = num - nb_paye
                    tickets_to_record.extend([(nb_paye, "Payés"), (nb_avance, "Avances")] if nb_avance > 0 else [(nb_paye, "Payés")])
                else: 
                    tickets_to_record.append((num, "Avances"))
            
            conn = db.get_connection()
            c = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            
            c.execute("SELECT sexe FROM usagers WHERE id=?", (self.uid,))
            user_sexe = c.fetchone()[0]

            created_hist_ids = [] 
            history_data_to_save = []

            for qty, st in tickets_to_record: 
                data_tuple = ('Consommation ticket(s)', str(qty), user_sexe, self.uid, today, st)
                c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, ?, ?, ?, ?)", data_tuple)
                created_hist_ids.append(c.lastrowid)
                history_data_to_save.append(data_tuple)

            nst = self.status
            if self.status in ["Payés", "Avances"]: 
                nst = "Avances" if nt < 0 else "Payés"
            
            new_solde = nt * db.get_ticket_price()
            c.execute("UPDATE usagers SET ticket=?, solde=?, statut=?, passage=? WHERE id=?", (nt, new_solde, nst, datetime.now().strftime("%d/%m/%Y %H:%M:%S"), self.uid))
            
            conn.commit()
            conn.close()
            
            # --- UNDO : Enregistrement complet ---
            new_state = {self.uid: {'solde': new_solde, 'ticket': nt, 'statut': nst}}
            
            if hasattr(self.parent_app, 'undo_manager'):
                self.parent_app.undo_manager.record_action('CONSUME', prev_state, new_state, created_hist_ids, history_data_to_save)
            
            self.parent_app.load_data()
            self.parent_app.refresh_counters()
            self.parent_app.update_stats()
            self.parent_app.generate_pdf(silent_mode=True)
            self.accept()
            
        except ValueError: 
            CustomMessageBox(self, "Saisie incorrecte", "Veuillez entrer un nombre entier positif.", error=True).exec()
        except Exception as e: 
            CustomMessageBox(self, "Erreur", f"{str(e)}", error=True).exec()

class RechargerCompteDialog(BaseDialog):
    def __init__(self, parent, uid, name, solde, status):
        super().__init__(parent, "Recharger Compte", 300, 250)
        self.uid = uid
        self.solde = solde
        self.status = status
        self.price = db.get_ticket_price()
        
        lbl = QLabel(f"Recharge pour : {name}")
        lbl.setStyleSheet("font-weight: bold;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl)
        
        self.layout.addWidget(QLabel("Montant (€) :"))
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Ex: 10.00")
        self.entry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.entry.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.layout.addWidget(self.entry)
        
        self.entry.returnPressed.connect(self.process)
        self.layout.addSpacing(20)
        
        btn = ModernButton("VALIDER", AppColors.BTN_VALIDER, self.process, 35, 6)
        btn.setDefault(True)
        self.layout.addWidget(btn)

    def process(self):
        try:
            m = float(self.entry.text().replace(',', '.'))
            if m < 0: raise ValueError 
            
            ns = self.solde + m
            nt = round(ns / self.price)
            old_status = self.status
            nst = self.status
            
            if self.status in ["Payés", "Avances"]: 
                nst = "Avances" if ns < 0 else "Payés"
            
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO historique_passages (action, detail, sexe, usager_id, date_passage, statut_au_passage) VALUES (?, ?, (SELECT sexe FROM usagers WHERE id=?), ?, ?, ?)", ('Recharge Compte', f"+{m:.2f} €", self.uid, self.uid, datetime.now().strftime("%Y-%m-%d"), old_status))
            c.execute("UPDATE usagers SET solde=?, ticket=?, statut=? WHERE id=?", (ns, nt, nst, self.uid))
            conn.commit()
            conn.close()
            
            self.parent_app.load_data()
            self.parent_app.update_stats()
            self.parent_app.generate_pdf(silent_mode=True)
            self.accept()
        except ValueError: 
            CustomMessageBox(self, "Saisie incorrecte", "Veuillez entrer un montant valide (positif).", error=True).exec()

class HistoriqueDialog(BaseDialog):
    def __init__(self, parent, uid, name):
        super().__init__(parent, f"Historique - {name}", 800, 450)
        
        lbl = QLabel("HISTORIQUE DES ACTIONS")
        lbl.setStyleSheet("font-size: 14pt; font-weight: bold; color: #2c3e50;")
        self.layout.addWidget(lbl)
        
        self.table = QTableWidget(0, 3) 
        self.table.setHorizontalHeaderLabels(["DATE/HEURE", "ACTION", "DÉTAIL"])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed) 
        header.resizeSection(0, 160) 
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 150)
        
        self.table.verticalHeader().setVisible(False) 
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.layout.addWidget(self.table)
        
        conn = db.get_connection()
        c = conn.cursor()
        c.execute("SELECT date_passage, heure_passage, action, detail FROM historique_passages WHERE usager_id=? ORDER BY id DESC", (uid,))
        
        for r in c.fetchall():
            date_p, heure_p, action, detail = r
            datetime_str = f"{date_p.replace('-', '/')} {heure_p}"
            
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            it_dt = QTableWidgetItem(datetime_str)
            it_dt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 0, it_dt)
            
            it_act = QTableWidgetItem(action)
            it_act.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, it_act)
            
            it_det = QTableWidgetItem(detail)
            it_det.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, it_det)
            
        conn.close()

        self.layout.addSpacing(20)
        btn_close = ModernButton("FERMER", "#95a5a6", self.reject, 35, 6)
        self.layout.addWidget(btn_close)

# ============================================================================
# DIALOGUE DE RESTAURATION
# ============================================================================
class RestaurationDialog(BaseDialog):
    def __init__(self, parent):
        super().__init__(parent, "Gestion Base de Données & Maintenance", 600, 650)
        self.parent_app = parent
        
        # ... (Le début de la classe reste identique jusqu'à la section Toggle Auto) ...
        # (Copiez le code existant pour la liste des backups et le bouton restaurer)
        lbl_titre_rest = QLabel("RESTAURATION DE SAUVEGARDE")
        lbl_titre_rest.setStyleSheet("color: #2c3e50; font-weight: 800; font-size: 12pt; margin-top: 5px;")
        lbl_titre_rest.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl_titre_rest)

        lbl_warn = QLabel("⚠️ Attention : Restaurer une sauvegarde écrasera les données actuelles.")
        lbl_warn.setStyleSheet("color: #e74c3c; font-style: italic; margin-bottom: 5px;")
        lbl_warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl_warn)

        self.list_widget = QTableWidget(0, 2)
        self.list_widget.setHorizontalHeaderLabels(["Date", "Fichier"])
        self.list_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.list_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_widget.verticalHeader().setVisible(False)
        self.list_widget.setFixedHeight(200)
        self.layout.addWidget(self.list_widget)

        self.backup_dir = db.get_config('EXPORT_SUP_PATH') 
        self.backups = []
        self.load_backups()

        btn_restore = ModernButton("RESTAURER LA SÉLECTION", "#e74c3c", self.perform_restore, 35, 6)
        self.layout.addWidget(btn_restore)

        self.layout.addSpacing(15)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #bdc3c7;")
        self.layout.addWidget(line)
        self.layout.addSpacing(15)

        lbl_titre_maint = QLabel("MAINTENANCE & NETTOYAGE")
        lbl_titre_maint.setStyleSheet("color: #2c3e50; font-weight: 800; font-size: 12pt;")
        lbl_titre_maint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(lbl_titre_maint)
        
        lbl_desc = QLabel(
            "Cette option supprime l'historique vieux de plus de 2 ans pour accélérer le logiciel.\n"
            "Les comptes usagers et les soldes actuels ne sont PAS touchés."
        )
        lbl_desc.setStyleSheet("color: #7f8c8d; font-size: 10pt;")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)
        self.layout.addWidget(lbl_desc)

        # --- SECTION TOGGLE MODIFIÉE ---
        h_auto = QHBoxLayout()
        h_auto.addStretch()
        
        self.toggle_auto = ToggleSwitch(inactive_color="#bdc3c7") # On s'assure que le toggle inactif est gris
        self.lbl_auto_text = QLabel("Effectuer ce nettoyage automatiquement au démarrage")
        self.lbl_auto_text.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # ASTUCE : Rendre le QLabel cliquable en surchargeant mousePressEvent à la volée
        # Cela évite de créer une sous-classe juste pour ça
        self.lbl_auto_text.mousePressEvent = lambda event: self.toggle_auto.toggle()
        
        # Charger l'état actuel
        is_auto = db.get_config('AUTO_CLEAN_ENABLED') == '1'
        self.toggle_auto.setChecked(is_auto)
        
        # Connecter le toggle
        self.toggle_auto.toggled.connect(self.on_toggle_auto)
        
        # Appliquer le style initial
        self.update_auto_label_style(is_auto)

        h_auto.addWidget(self.toggle_auto)
        h_auto.addWidget(self.lbl_auto_text)
        h_auto.addStretch()
        self.layout.addLayout(h_auto)

        self.layout.addSpacing(10)

        btn_clean = ModernButton("LANCER LE NETTOYAGE MAINTENANT", "#e67e22", lambda: self.clean_db(silent=False), 35, 6)
        self.layout.addWidget(btn_clean)

        self.layout.addStretch()
        
        btn_close = ModernButton("FERMER", "#95a5a6", self.reject, 40, 6)
        self.layout.addWidget(btn_close)

    # ... (Méthodes load_backups et perform_restore inchangées) ...
    def load_backups(self):
        # (Garder le code existant)
        if not self.backup_dir or not os.path.exists(self.backup_dir):
            self.list_widget.setRowCount(0)
            return
        files = glob.glob(os.path.join(self.backup_dir, "backup_*.db"))
        files.sort(key=os.path.getmtime, reverse=True)
        self.list_widget.setRowCount(0)
        self.backups = files
        for f in files:
            row = self.list_widget.rowCount()
            self.list_widget.insertRow(row)
            filename = os.path.basename(f)
            try:
                ts = os.path.getmtime(f)
                display_date = datetime.fromtimestamp(ts).strftime("%d/%m/%Y à %Hh%M")
            except: display_date = "Date inconnue"
            self.list_widget.setItem(row, 0, QTableWidgetItem(display_date))
            self.list_widget.setItem(row, 1, QTableWidgetItem(filename))

    def perform_restore(self):
        # (Garder le code existant)
        sel = self.list_widget.selectionModel().selectedRows()
        if not sel: return CustomMessageBox(self, "Erreur", "Veuillez sélectionner une ligne.", error=True).exec()
        idx = sel[0].row()
        selected_file = self.backups[idx]
        if ConfirmationDialog(self, "Attention", "Toutes les données actuelles seront remplacées par cette sauvegarde.\nLe logiciel va redémarrer.\n\nContinuer ?").exec():
            try:
                if os.path.exists(DB_FILE): shutil.move(DB_FILE, f"{DB_FILE}.pre_restore")
                shutil.copy2(selected_file, DB_FILE)
                CustomMessageBox(self, "Succès", "Restauration terminée.\nLe logiciel va redémarrer.", success=True).exec()
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit()
            except Exception as e:
                if os.path.exists(f"{DB_FILE}.pre_restore"): shutil.move(f"{DB_FILE}.pre_restore", DB_FILE)
                CustomMessageBox(self, "Erreur", f"Échec de la restauration : {e}", error=True).exec()

    def on_toggle_auto(self, checked):
        val = '1' if checked else '0'
        db.set_config('AUTO_CLEAN_ENABLED', val)
        self.update_auto_label_style(checked)

    def update_auto_label_style(self, checked):
        # --- MODIFICATION DE STYLE ICI ---
        base_style = "font-size: 10pt; font-weight: bold;"
        
        if checked:
            # ACTIF : Noir / Foncé
            self.lbl_auto_text.setStyleSheet(f"{base_style} color: #2c3e50;")
        else:
            # INACTIF : Gris (Même couleur que le toggle inactif)
            self.lbl_auto_text.setStyleSheet(f"{base_style} color: #bdc3c7;")

    def clean_db(self, silent=False):
        # (Garder le code existant)
        try:
            conn = db.get_connection()
            c = conn.cursor()
            c.execute("DELETE FROM historique_passages WHERE date_passage < date('now', '-2 years')")
            deleted_count = c.rowcount 
            conn.commit()
            conn.execute("VACUUM")
            conn.close()
            if not silent:
                if deleted_count > 0:
                    CustomMessageBox(self, "Maintenance Terminée", f"Nettoyage effectué avec succès.\n{deleted_count} anciennes lignes supprimées.", success=True).exec()
                else:
                    CustomMessageBox(self, "Information", "La base de données est déjà propre.\nAucune donnée vieille de plus de 2 ans.", success=True).exec()
            else:
                print(f"[Auto-Clean] {deleted_count} lignes supprimées.")
        except Exception as e:
            if not silent:
                CustomMessageBox(self, "Erreur", f"Erreur lors de la maintenance : {e}", error=True).exec()
            else:
                print(f"[Auto-Clean Error] {e}")
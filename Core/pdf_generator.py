import os
import sys
import shutil
import calendar
import tempfile
import sqlite3
from datetime import datetime, date, timedelta

# Imports locaux
from constants import (
    DB_FILE, ARCHIVE_DIR, HAS_REPORTLAB, AppColors
)
from database import get_connection, get_config

# Import du service de stats
from Core.stats import StatsService

# Imports ReportLab (Gestion de l'absence de la librairie)
if HAS_REPORTLAB:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape, portrait
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm

# ============================================================================
# UTILITAIRES DATES
# ============================================================================
def get_french_holidays(year):
    """Calcule les jours fériés en France pour une année donnée."""
    holidays = [
        date(year, 1, 1), date(year, 5, 1), date(year, 5, 8), 
        date(year, 7, 14), date(year, 8, 15), date(year, 11, 1), 
        date(year, 11, 11), date(year, 12, 25)
    ]
    # Calcul de Pâques (Algorithme de Meeus/Jones/Butcher)
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    
    # Lundi de Pâques, Ascension, Pentecôte
    holidays.extend([
        easter + timedelta(days=1), 
        easter + timedelta(days=39), 
        easter + timedelta(days=50)
    ])
    return holidays

# ============================================================================
# GÉNÉRATION DU BILAN MENSUEL (ARCHIVE)
# ============================================================================
def generate_pdf_logic(ticket_price, secondary_path=None, silent_mode=False):
    """
    Génère le PDF complet du mois en cours avec le détail par jour.
    Sauvegarde dans 'Archive/' et éventuellement un dossier secondaire (clé USB).
    """
    if not HAS_REPORTLAB:
        raise ImportError("La librairie 'reportlab' est manquante.")

    # 1. Préparation des chemins
    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)
        
    now = datetime.now()
    pdf_filename = f"{now.strftime('%y-%m')}.pdf"
    pdf_path_archive = os.path.join(ARCHIVE_DIR, pdf_filename)
    
    # Gestion du path secondaire (si activé dans les options)
    if not secondary_path:
        if get_config('EXPORT_SUP_ENABLED') == '1':
            path_config = get_config('EXPORT_SUP_PATH')
            if path_config and os.path.exists(path_config): 
                secondary_path = path_config

    # 2. Initialisation du document
    doc = SimpleDocTemplate(
        pdf_path_archive, 
        pagesize=landscape(A4), 
        rightMargin=10*mm, leftMargin=10*mm, 
        topMargin=10*mm, bottomMargin=10*mm
    )
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading2']
    title_style.alignment = 1 # Center
    
    # 3. Préparation des données temporelles
    month_names = {
        1:"JANVIER", 2:"FÉVRIER", 3:"MARS", 4:"AVRIL", 5:"MAI", 6:"JUIN", 
        7:"JUILLET", 8:"AOÛT", 9:"SEPTEMBRE", 10:"OCTOBRE", 11:"NOVEMBRE", 12:"DÉCEMBRE"
    }
    m_name = month_names[now.month]
    year = now.year
    _, num_days = calendar.monthrange(year, now.month)
    holidays = get_french_holidays(year)
    
    # En-têtes du tableau
    h_row = ["Nom / Prénom"]
    n_row = [""]
    weekend_indices = []
    holiday_indices = []
    
    for d in range(1, num_days + 1):
        dt = datetime(year, now.month, d)
        day_fr = ["Lu","Ma","Me","Je","Ve","Sa","Di"][dt.weekday()]
        h_row.append(day_fr)
        n_row.append(str(d))
        
        if dt.weekday() >= 5: 
            weekend_indices.append(d)
        if dt.date() in holidays: 
            holiday_indices.append(d)
    
    h_row.append("Dépense")
    h_row.append("Solde")
    n_row.append("")
    n_row.append("")
    
    # 4. Récupération des données
    conn = get_connection()
    c = conn.cursor()
    
    # Mise à jour rétroactive des statuts pour l'affichage cohérent
    c.execute("""
        UPDATE historique_passages 
        SET statut_au_passage = 'Tutelles' 
        WHERE usager_id IN (SELECT id FROM usagers WHERE statut = 'Tutelles') 
        AND statut_au_passage = 'Avances' 
        AND strftime('%Y-%m', date_passage) = ?
    """, (now.strftime("%Y-%m"),))
    conn.commit()
    
    groups = [
        ("Payés", ["Payés", "Pas de crédit"]), 
        ("Avances", ["Avances"]), 
        ("Tutelles", ["Tutelles"]), 
        ("Tickets Offerts", ["1ère fois"])
    ]
    
    # 5. Boucle de génération des tableaux par groupe
    for group_name, subtypes in groups:
        elements.append(Paragraph(f"<b>BILAN DU MOIS DE {m_name} {year} - {group_name.upper()}</b>", title_style))
        elements.append(Spacer(1, 3*mm))
        
        placeholders = ",".join("?" for _ in subtypes)
        query_users = f"""
            SELECT DISTINCT u.id, u.nom, u.prenom, u.sexe, u.solde 
            FROM usagers u 
            JOIN historique_passages h ON u.id = h.usager_id 
            WHERE h.statut_au_passage IN ({placeholders}) 
            AND strftime('%Y-%m', h.date_passage) = ? 
            AND h.action = 'Consommation ticket(s)' 
            ORDER BY u.nom
        """
        c.execute(query_users, subtypes + [now.strftime("%Y-%m")])
        users = c.fetchall()
        
        table_data = [h_row, n_row]
        
        # Totaux colonnes
        col_sums_tickets = [0]*num_days
        tot_h_tickets = [0]*num_days
        tot_f_tickets = [0]*num_days
        
        total_exp = 0.0
        total_bal = 0.0
        
        total_exp_h = 0.0
        total_bal_h = 0.0
        total_exp_f = 0.0
        total_bal_f = 0.0
        
        # Remplissage par Usager
        for u in users:
            uid, nm, pr, sx, sl = u
            row = [f"{nm} {pr}"]
            
            c2 = conn.cursor()
            c2.execute(f"""
                SELECT date_passage, quantite 
                FROM view_conso_nettoyees 
                WHERE usager_id=? 
                AND statut_au_passage IN ({placeholders}) 
                AND strftime('%Y-%m', date_passage)=?
            """, [uid] + subtypes + [now.strftime("%Y-%m")])
            
            consos = {}
            sec_t = 0
            for r in c2.fetchall(): 
                d = int(r[0].split('-')[2]) - 1
                try: 
                    q=int(r[1])
                    consos[d]=consos.get(d,0)+q
                    sec_t+=q
                except: pass
            
            for i in range(num_days):
                q = consos.get(i, 0)
                row.append(str(q) if q > 0 else "")
                if q > 0: 
                    col_sums_tickets[i]+=q
                    tot_h_tickets[i]+=q if sx=="H" else 0
                    tot_f_tickets[i]+=q if sx=="F" else 0
            
            val = 0.0 if group_name == "Tickets Offerts" else sec_t * ticket_price
            row.append(f"{val:.2f}€")
            row.append(f"{sl:.2f}€")
            
            total_exp += val
            total_bal += sl
            if sx == "H": 
                total_exp_h += val
                total_bal_h += sl
            else: 
                total_exp_f += val
                total_bal_f += sl
            
            table_data.append(row)
        
        # Gestion des ANONYMES (Lignes ajoutées en bas du tableau Payés ou Offerts)
        target = "PAYE" if group_name=="Payés" else ("1ERE_FOIS" if group_name=="Tickets Offerts" else "")
        if target:
            for g, l in [('H', 'Anonymes Hommes'), ('F', 'Anonymes Femmes')]:
                ar = [l]
                c2 = conn.cursor()
                c2.execute(f"""
                    SELECT date_passage 
                    FROM view_conso_nettoyees 
                    WHERE action='{target}' 
                    AND sexe=? 
                    AND strftime('%Y-%m', date_passage)=?
                """, (g, now.strftime("%Y-%m")))
                
                am = {}
                for r in c2.fetchall(): 
                    d=int(r[0].split('-')[2])-1
                    am[d]=am.get(d,0)+1
                    col_sums_tickets[d]+=1
                    tot_h_tickets[d]+=1 if g=='H' else 0
                    tot_f_tickets[d]+=1 if g=='F' else 0
                
                for i in range(num_days): 
                    ar.append(str(am.get(i,"")) if am.get(i,0)>0 else "")
                
                va = 0.0 if group_name == "Tickets Offerts" else sum(am.values())*ticket_price
                ar.append(f"{va:.2f}€")
                ar.append("-")
                
                total_exp += va
                if g=='H': total_exp_h += va
                else: total_exp_f += va
                
                if group_name != "Tickets Offerts": 
                    table_data.append(ar)
        
        # Lignes de Totaux finaux
        ft_h = ["Total Hommes"] + [str(x) if x>0 else "" for x in tot_h_tickets] + [f"{total_exp_h:.2f}€", f"{total_bal_h:.2f}€"]
        ft_f = ["Total Femmes"] + [str(x) if x>0 else "" for x in tot_f_tickets] + [f"{total_exp_f:.2f}€", f"{total_bal_f:.2f}€"]
        fs = [h+f for h,f in zip(tot_h_tickets, tot_f_tickets)]
        ft_s = ["TOTAL"] + [str(x) if x>0 else "" for x in fs] + [f"{total_exp:.2f}€", f"{total_bal:.2f}€"]
        
        table_data.append(ft_h)
        table_data.append(ft_f)
        table_data.append(ft_s)
        
        # Mise en forme du tableau
        col_w = [40*mm] + [6*mm]*num_days + [20*mm, 20*mm]
        
        # Couleurs dynamiques selon le groupe
        bg_hex = "#ffffff"
        if group_name == "Payés": bg_hex = AppColors.ROW_PAYE
        elif group_name == "Avances": bg_hex = AppColors.ROW_AVANCE
        elif group_name == "Tutelles": bg_hex = AppColors.ROW_TUTELLE
        elif group_name == "Tickets Offerts": bg_hex = AppColors.ROW_OFFERT
        
        # Styles ReportLab
        ts = [
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTSIZE', (0,0), (-1,-1), 7),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'), 
            ('ALIGN', (0,0), (0,-1), 'LEFT'), 
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,1), colors.HexColor(bg_hex)), 
            ('FONTNAME', (0,0), (-1,1), 'Helvetica-Bold')
        ]
        
        # Coloration Weekends et Fériés
        for idx in weekend_indices: 
            ts.append(('BACKGROUND', (idx, 2), (idx, -1), colors.HexColor("#f0f0f0")))
        for idx in holiday_indices: 
            ts.append(('BACKGROUND', (idx, 2), (idx, -1), colors.HexColor("#e0e0e0")))
        
        # Style des 3 dernières lignes (Totaux)
        ts.extend([
            ('BACKGROUND', (0,-3), (-1,-3), colors.HexColor("#d1ecf1")), # Bleu clair (H)
            ('BACKGROUND', (0,-2), (-1,-2), colors.HexColor("#f8d7da")), # Rouge clair (F)
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#d4edda")), # Vert clair (Tot)
            ('FONTNAME', (0,-3), (-1,-1), 'Helvetica-Bold')
        ])
        
        t = Table(table_data, colWidths=col_w)
        t.setStyle(TableStyle(ts))
        elements.append(t)
        elements.append(PageBreak())
    
    conn.close()
    
    # Génération physique du fichier
    doc.build(elements)
    
    # 6. Copie de sauvegarde si demandée
    if secondary_path and os.path.exists(secondary_path):
        try: 
            shutil.copy2(pdf_path_archive, os.path.join(secondary_path, pdf_filename))
            print(f"Copie sauvegarde effectuée vers : {secondary_path}")
        except Exception as e:
            print(f"Erreur copie sauvegarde : {e}")

# ============================================================================
# GÉNÉRATION DU BILAN PERSONNALISÉ (DATE A DATE)
# ============================================================================
def generate_custom_pdf_logic(d_start, d_end, ticket_price):
    """
    Génère un PDF temporaire pour une plage de dates spécifique.
    Retourne le chemin du fichier généré.
    """
    if not HAS_REPORTLAB:
        raise ImportError("La librairie 'reportlab' est manquante.")
        
    stats = StatsService.get_stats_range(d_start, d_end)
    
    temp_dir = tempfile.gettempdir()
    pdf_filename = f"Bilan_{d_start}_au_{d_end}.pdf"
    pdf_path = os.path.join(temp_dir, pdf_filename)
    
    doc = SimpleDocTemplate(pdf_path, pagesize=portrait(A4))
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    title_style.alignment = 1
    normal_style_centered = styles['Normal']
    normal_style_centered.alignment = 1
    
    # Calculs financiers additionnels
    conn = get_connection()
    c = conn.cursor()
    
    # Somme des recharges
    c.execute("""
        SELECT detail FROM historique_passages 
        WHERE action='Recharge Compte' 
        AND date_passage BETWEEN ? AND ?
    """, (d_start, d_end))
    
    total_recharges = 0.0
    for r in c.fetchall(): 
        try: 
            total_recharges += float(r[0].replace('€', '').replace('+', '').strip())
        except: pass
    
    # Ventes directes anonymes
    c.execute("""
        SELECT COUNT(*) FROM historique_passages 
        WHERE action='PAYE' AND detail='Anonyme' 
        AND date_passage BETWEEN ? AND ?
    """, (d_start, d_end))
    
    nb_ventes_directes = c.fetchone()[0]
    valeur_ventes_directes = nb_ventes_directes * ticket_price
    
    total_encaisse_reel = total_recharges + valeur_ventes_directes
    valeur_conso_theorique = (stats['tickets_carte'] + stats['tickets_avance'] + stats['tickets_tutelle'] + stats['tickets_1ere_fois']) * ticket_price
    
    conn.close()
    
    # --- Construction du document ---
    elements.append(Paragraph(f"<b>BILAN PÉRIODIQUE</b>", title_style))
    elements.append(Paragraph(f"Du {d_start} au {d_end}", normal_style_centered))
    elements.append(Spacer(1, 10*mm))
    
    # Tableau 1: Volumes
    data_vol = [
        ["Catégorie", "Quantité"], 
        ["Tickets Carte", str(stats['tickets_carte'] + stats['tickets_tutelle'])], 
        ["Tickets Avance", str(stats['tickets_avance'])], 
        ["Tickets 1ère fois", str(stats['tickets_1ere_fois'])], 
        ["TOTAL TICKETS", str(stats['total_passages'])]
    ]
    
    t_vol = Table(data_vol, colWidths=[100*mm, 50*mm])
    t_vol.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(AppColors.HEADER_BG)), 
        ('TEXTCOLOR', (0,0), (-1,0), colors.white), 
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), 
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), 
        ('GRID', (0,0), (-1,-1), 1, colors.black), 
        # Ligne "TOTAL TICKETS" en gris
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey), 
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold')
    ]))
    elements.append(Paragraph("<b>Volumes de consommation</b>", styles['Heading3']))
    elements.append(t_vol)
    elements.append(Spacer(1, 10*mm))
    
    # Tableau 2: Fréquentation
    data_freq = [
        ["Public", "Passages"], 
        ["Hommes", str(stats['total_h'])], 
        ["Femmes", str(stats['total_f'])], 
        ["TOTAL", str(stats['total_passages'])]
    ]
    t_freq = Table(data_freq, colWidths=[100*mm, 50*mm])
    t_freq.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(AppColors.HEADER_BG)), 
        ('TEXTCOLOR', (0,0), (-1,0), colors.white), 
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), 
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), 
        ('GRID', (0,0), (-1,-1), 1, colors.black), 
        ('BACKGROUND', (0,-1), (-1,-1), colors.lightgrey)
    ]))
    elements.append(Paragraph("<b>Fréquentation</b>", styles['Heading3']))
    elements.append(t_freq)
    elements.append(Spacer(1, 10*mm))
    
    # Tableau 3: Finances
    data_fin = [
        ["Poste", "Montant (€)"], 
        ["Valeur Consommée (Théorique)", f"{valeur_conso_theorique:.2f} €"], 
        ["Total Encaissé (Tickets payés + Recharges)", f"{total_encaisse_reel:.2f} €"]
    ]
    t_fin = Table(data_fin, colWidths=[100*mm, 50*mm])
    t_fin.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor(AppColors.HEADER_BG)), 
        ('TEXTCOLOR', (0,0), (-1,0), colors.white), 
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), 
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), 
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(Paragraph("<b>Finances</b>", styles['Heading3']))
    elements.append(t_fin)
    
    doc.build(elements)
    return pdf_path
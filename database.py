import sqlite3
import os
import re  # <--- INDISPENSABLE pour la fonction REGEXP
from constants import DB_DIR, DB_FILE

# ============================================================================
# FONCTION PYHTON POUR REGEX SQLITE
# ============================================================================
def regexp(expr, item):
    """Fonction qui permet d'utiliser REGEXP dans les requêtes SQL."""
    try:
        # Si l'item est vide ou None, ça ne matche pas
        if item is None:
            return False
        reg = re.compile(expr)
        return reg.search(str(item)) is not None
    except Exception:
        return False

# ============================================================================
# GESTION CONNEXION
# ============================================================================
def get_connection():
    """
    Crée et retourne une connexion à la base de données.
    TIMEOUT=10 : Attend 10s avant de planter si la base est occupée.
    """
    # SÉCURITÉ : On s'assure que le dossier existe avant de se connecter
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)
        
    conn = sqlite3.connect(DB_FILE, timeout=10)
    
    # --- C'EST ICI LA RÉPARATION ---
    # On "apprend" à SQLite comment utiliser la fonction REGEXP
    conn.create_function("REGEXP", 2, regexp)
    
    return conn

# ============================================================================
# INITIALISATION DB
# ============================================================================
def init_db():
    # SÉCURITÉ : Création du dossier si inexistant
    if not os.path.exists(DB_DIR):
        os.makedirs(DB_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    # On ajoute aussi la fonction ici pour éviter les erreurs lors de la création de vues
    conn.create_function("REGEXP", 2, regexp)
    
    c = conn.cursor()
    
    # Création de la table Usagers
    c.execute("""CREATE TABLE IF NOT EXISTS usagers (
        id INTEGER PRIMARY KEY,
        nom TEXT,
        prenom TEXT,
        sexe TEXT,
        statut TEXT,
        solde REAL,
        ticket INTEGER,
        passage TEXT,
        photo_filename TEXT,
        commentaire TEXT
    )""")
    
    # Création de la table Historique
    c.execute("""CREATE TABLE IF NOT EXISTS historique_passages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT,
        detail TEXT,
        sexe TEXT,
        usager_id INTEGER,
        date_passage DATE,
        heure_passage TEXT DEFAULT (time('now', 'localtime')),
        statut_au_passage TEXT,
        FOREIGN KEY(usager_id) REFERENCES usagers(id)
    )""")
    
    # Création de la table Config
    c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
    
    # --- MISE A JOUR DES VALEURS PAR DÉFAUT ---
    defaults = [
        ('TICKET_PRICE', '0.5'),
        ('LAST_RESET', ''),
        ('EXPORT_SUP_ENABLED', '0'),
        ('EXPORT_SUP_PATH', ''),
        ('LAST_USED_ID', '0'),
        ('LAST_RUN_VERSION', '0.0.0'),
        ('UPDATE_CHANNEL', 'stable'),
        ('AUTO_CLEAN_ENABLED', '0')
    ]
    
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    
    # --- CRÉATION DES VUES (Optimisation) ---
    # Vue pour simplifier les calculs de stats et graphiques
    # Elle utilise REGEXP pour distinguer si "detail" est un nombre (quantité de tickets) ou du texte
    c.execute("DROP VIEW IF EXISTS view_conso_nettoyees")
    c.execute("""
    CREATE VIEW view_conso_nettoyees AS
    SELECT 
        h.id,
        h.date_passage,
        h.sexe,
        h.action,
        h.statut_au_passage,
        h.usager_id,
        CASE 
            WHEN h.detail REGEXP '^-?[0-9]+$' THEN CAST(h.detail AS INTEGER)
            ELSE 1 
        END as quantite
    FROM historique_passages h
    WHERE h.action IN ('Consommation ticket(s)', 'PAYE', '1ERE_FOIS', 'Offert')
    """)
    
    conn.commit()
    conn.close()

# ============================================================================
# HELPERS
# ============================================================================
def get_config(key, default=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key=?", (key,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else default

def set_config(key, value):
    conn = get_connection()
    c = conn.cursor()
    c.execute("REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_ticket_price():
    return float(get_config('TICKET_PRICE', '0.5'))

def set_ticket_price(price):
    set_config('TICKET_PRICE', str(price))

def get_next_usager_id(cursor):
    cursor.execute("SELECT value FROM config WHERE key='LAST_USED_ID'")
    res = cursor.fetchone()
    config_last = int(res[0]) if res else 0
    cursor.execute("SELECT MAX(id) FROM usagers")
    res_db = cursor.fetchone()
    db_max = res_db[0] if res_db[0] is not None else 0
    return max(config_last, db_max) + 1
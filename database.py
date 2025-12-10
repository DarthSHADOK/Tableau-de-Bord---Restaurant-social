import sqlite3
import os
from constants import DB_DIR, DB_FILE

def get_connection():
    """
    Crée et retourne une connexion à la base de données.
    TIMEOUT=10 : Attend 10s avant de planter si la base est occupée.
    """
    return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    conn = sqlite3.connect(DB_FILE)
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
    # J'ai ajouté 'AUTO_CLEAN_ENABLED' à la fin de la liste
    defaults = [
        ('TICKET_PRICE', '0.5'),
        ('LAST_RESET', ''),
        ('EXPORT_SUP_ENABLED', '0'),
        ('EXPORT_SUP_PATH', ''),
        ('LAST_USED_ID', '0'),
        ('LAST_RUN_VERSION', '0.0.0'),
        ('UPDATE_CHANNEL', 'stable'),
        ('AUTO_CLEAN_ENABLED', '0')  # <--- NOUVELLE CLÉ
    ]
    
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))
    
    conn.commit()
    conn.close()

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
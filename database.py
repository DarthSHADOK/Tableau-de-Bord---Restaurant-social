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
    os.makedirs(DB_DIR, exist_ok=True)
    
    conn = get_connection()
    c = conn.cursor()
    
    # --- ACTIVATION DU MODE WAL (Magie anti-blocage) ---
    # Permet la lecture et l'écriture simultanées
    try:
        c.execute("PRAGMA journal_mode=WAL")
    except:
        pass # Si échoue, on reste en mode classique
        
    c.execute("""
        CREATE TABLE IF NOT EXISTS usagers (
            id INTEGER PRIMARY KEY, nom TEXT, prenom TEXT, sexe TEXT, 
            statut TEXT, solde REAL, ticket INTEGER, passage TEXT, 
            photo_filename TEXT
        )
    """)
    
    # Migrations colonnes
    c.execute("PRAGMA table_info(usagers)")
    cols = [col[1] for col in c.fetchall()]
    if 'commentaire' not in cols:
        try: c.execute("ALTER TABLE usagers ADD COLUMN commentaire TEXT DEFAULT ''")
        except: pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS historique_passages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, 
            sexe TEXT, date_passage DATE DEFAULT (date('now')), 
            heure_passage TIME DEFAULT (time('now')), usager_id INTEGER
        )
    """)
    
    c.execute("PRAGMA table_info(historique_passages)")
    columns = [info[1] for info in c.fetchall()]
    if 'statut_au_passage' not in columns:
        try: c.execute("ALTER TABLE historique_passages ADD COLUMN statut_au_passage TEXT DEFAULT 'INCONNU'")
        except: pass

    c.execute("DROP VIEW IF EXISTS view_conso_nettoyees")
    c.execute("""
        CREATE VIEW view_conso_nettoyees AS 
        SELECT id, usager_id, date_passage, sexe, statut_au_passage, action, 
        CASE WHEN action = 'Consommation ticket(s)' THEN CAST(detail AS INTEGER) ELSE 1 END as quantite 
        FROM historique_passages 
        WHERE action IN ('Consommation ticket(s)', 'PAYE', '1ERE_FOIS')
    """)

    c.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)") 
    
    default_configs = [
        ('TICKET_PRICE', '0.5'), ('LAST_RESET', ''), 
        ('EXPORT_SUP_ENABLED', '0'), ('EXPORT_SUP_PATH', ''), 
        ('LAST_USED_ID', '0'), ('LAST_RUN_VERSION', '0.0.0'),
        ('UPDATE_CHANNEL', 'stable')
    ]
    for k, v in default_configs:
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (k, v))

    c.execute("""
        UPDATE historique_passages SET statut_au_passage = 'Tutelles' 
        WHERE usager_id IN (SELECT id FROM usagers WHERE statut = 'Tutelles') 
        AND statut_au_passage = 'Avances'
    """)

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
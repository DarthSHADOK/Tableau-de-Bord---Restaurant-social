from database import get_connection

class StatsService:
    @staticmethod
    def get_stats_range(date_start_str, date_end_str):
        conn = get_connection(); c = conn.cursor()
        where_clause = "WHERE date_passage BETWEEN ? AND ?"
        params = (date_start_str, date_end_str)
        stats = {'total_h': 0, 'total_f': 0, 'tickets_carte': 0, 'tickets_avance': 0, 'tickets_tutelle': 0, 'tickets_1ere_fois': 0, 'total_passages': 0}
        
        c.execute(f"SELECT sexe, SUM(quantite) FROM view_conso_nettoyees {where_clause} GROUP BY sexe", params)
        for row in c.fetchall():
            if row[0] == 'H': stats['total_h'] = row[1] if row[1] else 0
            elif row[0] == 'F': stats['total_f'] = row[1] if row[1] else 0
        stats['total_passages'] = stats['total_h'] + stats['total_f']
        
        c.execute(f"""SELECT CASE WHEN statut_au_passage IN ('Payés', 'Pas de crédit', 'Anonyme') THEN 'Carte' WHEN statut_au_passage = 'Avances' THEN 'Avance' WHEN statut_au_passage = 'Tutelles' THEN 'Tutelle' WHEN statut_au_passage IN ('1ère fois', 'Offert') THEN '1ere_fois' ELSE 'Autre' END as cat, SUM(quantite) FROM view_conso_nettoyees {where_clause} GROUP BY cat""", params)
        for row in c.fetchall():
            if row[0] == 'Carte': stats['tickets_carte'] = row[1]
            elif row[0] == 'Avance': stats['tickets_avance'] = row[1]
            elif row[0] == 'Tutelle': stats['tickets_tutelle'] = row[1]
            elif row[0] == '1ere_fois': stats['tickets_1ere_fois'] = row[1]
        conn.close()
        return stats
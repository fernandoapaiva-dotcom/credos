import sqlite3
import json
import os

def analyze_dauto_patterns():
    db_path = "/app/data/db_54804458000122.db"
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Busca um grupo de documentos do Dauto (pagador com 284 no CNPJ ou nome parecido)
    # 24934648000284 é o CNPJ do Dauto
    cnpj_dauto = "24934648000284"
    
    print(f"--- Documentos para CNPJ {cnpj_dauto} ---")
    query = """
        SELECT num_nf, tipo, email_uid, created_at, fpath_local 
        FROM documentos_fiscais 
        WHERE cnpj_cliente = ? 
        ORDER BY created_at DESC 
        LIMIT 50
    """
    c.execute(query, (cnpj_dauto,))
    rows = c.fetchall()
    
    for r in rows:
        print(f"NF: {r[0]} | Tipo: {r[1]} | UID: {r[2]} | Data: {r[3]} | Path: {r[4]}")
        
    conn.close()

if __name__ == "__main__":
    analyze_dauto_patterns()

import sqlite3
import os

def analyze_indexing():
    db_path = "/app/data/db_54804458000122.db"
    if not os.path.exists(db_path):
        print("DB not found")
        return
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 24934648000284 é o CNPJ do Dauto
    cnpj_dauto = "24934648000284"
    
    print(f"--- Documentos 382 e 1334 (Dauto) ---")
    query = """
        SELECT id, num_nf, tipo, fpath_local, created_at, email_uid 
        FROM documentos_fiscais 
        WHERE cnpj_cliente = ? 
        AND (fpath_local LIKE '%382%' OR fpath_local LIKE '%1334%')
        ORDER BY created_at DESC
    """
    c.execute(query, (cnpj_dauto,))
    rows = c.fetchall()
    
    for r in rows:
        print(f"ID: {r[0]} | NF: {r[1]} | Tipo: {r[2]} | Data: {r[4]} | UID: {r[5]} | Path: {r[3]}")
        
    conn.close()

if __name__ == "__main__":
    analyze_indexing()

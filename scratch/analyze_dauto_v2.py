import sqlite3
import os

def analyze_dauto_sets():
    db_path = "/app/data/db_54804458000122.db"
    if not os.path.exists(db_path):
        print("DB not found")
        return
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Busca um range maior de documentos do Dauto para ver os 'sets'
    cnpj_dauto = "24934648000284"
    print(f"--- Documentos para CNPJ {cnpj_dauto} ---")
    
    query = """
        SELECT num_nf, tipo, email_uid, created_at, fpath_local 
        FROM documentos_fiscais 
        WHERE cnpj_cliente = ? 
        ORDER BY created_at DESC 
        LIMIT 30
    """
    c.execute(query, (cnpj_dauto,))
    rows = c.fetchall()
    
    for r in rows:
        nf, tipo, uid, data, path = r
        basename = os.path.basename(path) if path else "N/A"
        print(f"NF: {nf} | Tipo: {tipo} | UID: {uid} | Data: {data} | File: {basename}")
        
    conn.close()

if __name__ == "__main__":
    analyze_dauto_sets()

import sqlite3
import os
import json

def final_research():
    db_path = "/app/data/db_54804458000122.db"
    if not os.path.exists(db_path):
        print("DB Not Found")
        return
        
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 1. Check Titulos Columns
    print("--- SCHEMA titulos ---")
    c.execute("PRAGMA table_info(titulos)")
    cols_t = [r[1] for r in c.fetchall()]
    print(cols_t)
    
    # 2. Check Documentos Fiscais Columns
    print("\n--- SCHEMA documentos_fiscais ---")
    c.execute("PRAGMA table_info(documentos_fiscais)")
    cols_df = [r[1] for r in c.fetchall()]
    print(cols_df)
    
    # 3. Get Dauto Titles
    print("\n--- DAUTO TITLES ---")
    # Finding Dauto by pagador partial match
    c.execute("SELECT * FROM titulos WHERE pagador LIKE '%DAUTO%' AND status != 'Pago'")
    titles = c.fetchall()
    for t in titles:
        print(dict(zip(cols_t, t)))
        
    # 4. Get Dauto Notes
    print("\n--- DAUTO NOTES ---")
    # CNPJ Dauto: 24934648000284
    c.execute("SELECT * FROM documentos_fiscais WHERE cnpj_cliente = '24934648000284' ORDER BY emissao DESC LIMIT 10")
    notes = c.fetchall()
    for n in notes:
        row = dict(zip(cols_df, n))
        # Remove potentially large paths for clarity in log if needed, but let's keep it for now
        print(row)
        
    conn.close()

if __name__ == "__main__":
    final_research()

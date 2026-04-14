import sqlite3
import os

def check_everything():
    db_path = "/app/data/db_54804458000122.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("--- SCHEMA documentos_fiscais ---")
    c.execute("PRAGMA table_info(documentos_fiscais)")
    for r in c.fetchall():
        print(r)
        
    print("\n--- TITULOS DAUTO ---")
    c.execute("SELECT id, numero_nf, valor, pagador, created_at FROM titulos WHERE pagador LIKE '%DAUTO%' AND status != 'Pago'")
    for r in c.fetchall():
        print(f"ID: {r[0]} | NF: {r[1]} | Valor: {r[2]} | Pagador: {r[3]} | Data: {r[4]}")
        
    print("\n--- NOTAS DAUTO (Recentes) ---")
    # CNPJ Dauto: 24934648000284
    c.execute("SELECT id, num_nf, tipo, created_at, fpath_local FROM documentos_fiscais WHERE cnpj_cliente = '24934648000284' ORDER BY created_at DESC LIMIT 20")
    for r in c.fetchall():
        print(f"ID: {r[0]} | NF: {r[1]} | Tipo: {r[2]} | Data: {r[3]} | Path: {r[4]}")
        
    conn.close()

if __name__ == "__main__":
    check_everything()

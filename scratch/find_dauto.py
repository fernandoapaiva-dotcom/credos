import sqlite3
import os

db_path = r'c:\Antigravity\credos\data\54804458000122.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("--- PESQUISANDO CLIENTE ---")
    query = "SELECT * FROM clientes WHERE nome LIKE '%Dauto%'"
    rows = cursor.execute(query).fetchall()
    for row in rows:
        print(dict(row))
        
    print("\n--- PESQUISANDO TITULOS ---")
    query_tit = "SELECT * FROM titulos WHERE pagador LIKE '%Dauto%' ORDER BY vencimento DESC LIMIT 5"
    rows_tit = cursor.execute(query_tit).fetchall()
    for row in rows_tit:
        print(dict(row))
        
    # Search for documents in documentos_fiscais
    print("\n--- PESQUISANDO DOCUMENTOS INDEXADOS ---")
    query_doc = "SELECT * FROM documentos_fiscais WHERE cliente_nome LIKE '%Dauto%' ORDER BY data_indexacao DESC LIMIT 10"
    rows_doc = cursor.execute(query_doc).fetchall()
    for row in rows_doc:
        print(dict(row))
        
    conn.close()
else:
    print("DB não encontrado.")

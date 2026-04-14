import sqlite3
import os

db_path = "/home/ubuntu/credos/data/db_54804458000122.db"
if not os.path.exists(db_path):
    print(f"Error: DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Search client
query_cli = "SELECT cnpj, nome, whatsapp FROM clientes WHERE nome LIKE '%DAUTO%' OR whatsapp LIKE '%998334833%'"
cur.execute(query_cli)
clients = cur.fetchall()

print("--- CLIENTES ENCONTRADOS ---")
for c in clients:
    print(f"CNPJ: {c[0]} | Nome: {c[1]} | Zap: {c[2]}")
    
    # Search titles
    cur.execute("SELECT id, numero_nf, valor, vencimento FROM titulos WHERE pagador = ? ORDER BY vencimento DESC LIMIT 5", (c[1],))
    titles = cur.fetchall()
    print("  Últimos Títulos:")
    for t in titles:
        print(f"    ID: {t[0]} | NF: {t[1]} | Valor: {t[2]} | Venc: {t[3]}")
        
    # Search indexed documents
    cnpj_limpo = str(c[0]).replace('.', '').replace('/', '').replace('-', '').strip() if c[0] else ""
    cur.execute("SELECT tipo, num_nf, fpath_local, created_at FROM documentos_fiscais WHERE cnpj_cliente = ? ORDER BY created_at DESC LIMIT 10", (cnpj_limpo,))
    docs = cur.fetchall()
    print("  Documentos Indexados:")
    for d in docs:
        print(f"    Tipo: {d[0]} | NF: {d[1]} | Path: {d[2]} | Indexado: {d[3]}")

conn.close()

import sqlite3

db_path = '/app/data/db_54804458000122.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== BUSCA POR SPLIT BUNDLES (NF-E e NF-S SEPARADAS) ===")

query = """
    SELECT cnpj_cliente, DATE(created_at) as data, COUNT(DISTINCT email_uid) as uids, GROUP_CONCAT(DISTINCT tipo) as tipos
    FROM documentos_fiscais 
    GROUP BY cnpj_cliente, DATE(created_at)
    HAVING uids > 1
    LIMIT 20
"""
cur.execute(query)
rows = cur.fetchall()

if not rows:
    print("Nenhum split bundle encontrado ainda.")
else:
    for r in rows:
        print(f"\nCliente: {r[0]} | Data: {r[1]} | UIDs: {r[2]}")
        print(f"Tipos encontrados no dia: {r[3]}")
        
        # Detalha os documentos desse dia
        cur.execute("SELECT tipo, num_nf, email_uid, created_at FROM documentos_fiscais WHERE cnpj_cliente = ? AND DATE(created_at) = ?", (r[0], r[1]))
        docs = cur.fetchall()
        for d in docs:
            print(f"   - {d[0]} | NF: {d[1]} | UID: {d[2]} | Criado em: {d[3]}")

conn.close()

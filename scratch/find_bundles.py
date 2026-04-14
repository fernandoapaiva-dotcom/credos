import sqlite3

db_path = '/app/data/db_54804458000122.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== BUSCA POR BUNDLES (NF-E + NF-S) ===")

# Busca clientes com mais de um tipo de documento
query = """
    SELECT cnpj_cliente, COUNT(DISTINCT tipo) as ct, GROUP_CONCAT(DISTINCT tipo) as tipos
    FROM documentos_fiscais 
    GROUP BY cnpj_cliente 
    HAVING ct > 1 
    LIMIT 10
"""
cur.execute(query)
rows = cur.fetchall()

if not rows:
    print("Nenhum bundle encontrado no BD ainda.")
else:
    for r in rows:
        print(f"CNPJ: {r[0]} | Qtd Tipos: {r[1]} | Tipos: {r[2]}")
        # Pega as NFs desse cliente
        cur.execute("SELECT num_nf, tipo, email_uid FROM documentos_fiscais WHERE cnpj_cliente = ? LIMIT 5", (r[0],))
        nfs = cur.fetchall()
        for nf in nfs:
            print(f"   - NF: {nf[0]} | Tipo: {nf[1]} | Email_UID: {nf[2]}")

conn.close()

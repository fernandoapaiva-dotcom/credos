import sqlite3
db_path = "/app/data/db_54804458000122.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("=== BUSCA GLOBAL POR '382' NO BANCO DE DADOS ===")
cur.execute("SELECT id, num_nf, cnpj_cliente, filename, email_uid FROM documentos_fiscais WHERE num_nf LIKE '%382%' OR filename LIKE '%382%'")
rows = cur.fetchall()

if not rows:
    print("Nenhuma menção a '382' encontrada no banco.")
else:
    for r in rows:
        print(f"ID: {r[0]} | NF: {r[1]} | CNPJ: {r[2]} | File: {r[3]} | UID: {r[4]}")

print("\n=== CONFIGURED EMAILS ===")
cur.execute("SELECT config_key, config_value FROM configuracoes WHERE config_key LIKE '%mail_user%'")
[print(f"{r[0]}: {r[1]}") for r in cur.fetchall()]

conn.close()

import sqlite3, os
DB_DIR = os.getenv('DATABASE_DIR', '.')
db_path = os.path.join(DB_DIR, 'db_54804458000122.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT nome, cnpj, whatsapp, email FROM clientes WHERE nome LIKE '%DAUTO%'")
cliente = c.fetchone()
if cliente:
    nome, cnpj, wa, em = cliente
    print(f"CLIENTE: {nome} | CNPJ: {cnpj} | WA: {wa} | EM: {em}")
    c.execute("SELECT numero_nf, valor, vencimento, status, acao FROM titulos WHERE pagador = ?", (nome,))
    rows = c.fetchall()
    print(f"TITULOS ({len(rows)}):")
    for r in rows:
        print(f" - NF {r[0]} | R$ {r[1]:.2f} | Venc: {r[2]} | Status: {r[3]} | Acao: {r[4]}")
else:
    print("DAUTO não encontrado.")

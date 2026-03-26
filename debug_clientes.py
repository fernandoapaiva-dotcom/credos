from src.database import conectar
conn = conectar('11504286000169')
cursor = conn.cursor()
cursor.execute("SELECT nome, whatsapp, email FROM clientes")
for row in cursor.fetchall():
    print(f"Nome: {row[0]} | WA: {repr(row[1])} | Email: {repr(row[2])}")
conn.close()

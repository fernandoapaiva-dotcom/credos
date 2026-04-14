import sqlite3

db_file = "db_11504286000169.db"
conn = sqlite3.connect(db_file)
cur = conn.cursor()

print("--- Clientes CPC* ---")
cur.execute("SELECT nome FROM clientes WHERE nome LIKE 'CPC%'")
print(cur.fetchall())

print("\n--- Títulos CPC* ---")
cur.execute("SELECT id, pagador, valor, status, acao FROM titulos WHERE pagador LIKE 'CPC%'")
print(cur.fetchall())

conn.close()

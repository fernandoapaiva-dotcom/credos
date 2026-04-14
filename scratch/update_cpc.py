import sqlite3

db_file = "db_11504286000169.db"
conn = sqlite3.connect(db_file)
cur = conn.cursor()

print("--- Atualizando Títulos CPC para acao='Cobrar' ---")
cur.execute("UPDATE titulos SET acao = 'Cobrar' WHERE pagador LIKE 'CPC%'")
conn.commit()
print("Atualização concluída.")

conn.close()

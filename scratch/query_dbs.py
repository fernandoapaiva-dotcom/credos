import sqlite3
import os

def query_db(path, sql):
    if not os.path.exists(path):
        return f"Path {path} not found"
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute(sql)
        res = cur.fetchall()
        conn.close()
        return res
    except Exception as e:
        return str(e)

print("--- CENTRAL DB ---")
print(query_db('/app/data/credos_central.db', 'SELECT cnpj, nome FROM empresas'))

print("\n--- DB 54804458000122 ---")
print(query_db('/app/data/db_54804458000122.db', "SELECT pagador, numero_nf, valor_total FROM titulos WHERE status = 'Aberto' LIMIT 3"))

print("\n--- DB 11504286000169 ---")
print(query_db('/app/data/db_11504286000169.db', "SELECT pagador, numero_nf, valor_total FROM titulos WHERE status = 'Aberto' LIMIT 3"))

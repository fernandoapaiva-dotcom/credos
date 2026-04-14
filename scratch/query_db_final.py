import sqlite3
import os

def list_tables(db_path):
    if not os.path.exists(db_path): return f"{db_path} not found"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    res = cur.fetchall()
    conn.close()
    return res

def query(db_path, sql):
    if not os.path.exists(db_path): return f"{db_path} not found"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        cur.execute(sql)
        res = cur.fetchall()
        conn.close()
        return res
    except Exception as e:
        conn.close()
        return str(e)

print("--- CENTRAL DB ---")
print("Tables:", list_tables("/app/data/credos_central.db"))
# Trying common table names if 'empresas' fails
print("Data sample (if tables exist):", query("/app/data/credos_central.db", "SELECT * FROM empresas LIMIT 1"))

print("\n--- DB 54804458000122 ---")
print("Tables:", list_tables("/app/data/db_54804458000122.db"))
print("Titles sample:", query("/app/data/db_54804458000122.db", "SELECT pagador, numero_nf, status FROM titulos LIMIT 5"))

print("\n--- DB 11504286000169 ---")
print("Tables:", list_tables("/app/data/db_11504286000169.db"))
print("Titles sample:", query("/app/data/db_11504286000169.db", "SELECT pagador, numero_nf, status FROM titulos LIMIT 5"))

import sqlite3
import os

db_path = '/app/data/credos_central.db'
if not os.path.exists(db_path):
    print(f"ERROR: DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

print("--- USERS ---")
# Get admin user or first active user
c.execute("SELECT login, password FROM usuarios WHERE status='Ativo' OR login LIKE 'admin%'")
users = c.fetchall()
for u in users:
    print(f"{u[0]} | {u[1]}")

conn.close()

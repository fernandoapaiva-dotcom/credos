import sqlite3
import os

db_path = '/app/src/db_11504286000169.db'
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT login, password, perfil FROM usuarios")
users = c.fetchall()
conn.close()

print("USERS_LIST_START")
for u in users:
    print(f"{u[0]}|{u[1]}|{u[2]}")
print("USERS_LIST_END")

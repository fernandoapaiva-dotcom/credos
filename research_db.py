import sqlite3
import os

db_path = '/app/src/db_11504286000169.db'
if not os.path.exists(db_path):
    print(f"ERROR: DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

print("--- TABLES ---")
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
for t in c.fetchall():
    print(t[0])

print("--- USERS ---")
# Try multiple common table names for users
for table in ['usuarios', 'users', 'usuarios_sistema']:
    try:
        c.execute(f"SELECT login, password FROM {table}")
        for u in c.fetchall():
            print(f"{table}: {u[0]} | {u[1]}")
    except sqlite3.OperationalError:
        continue

conn.close()

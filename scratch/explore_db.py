import sqlite3
import os

DB_PATH = "/app/data/db_54804458000122.db"

def list_all():
    if not os.path.exists(DB_PATH):
        print(f"DB NOT FOUND: {DB_PATH}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print("--- TABLES ---")
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(tables)
    
    for table in tables:
        print(f"\n--- SCHEMA: {table} ---")
        c.execute(f"PRAGMA table_info({table})")
        for r in c.fetchall():
            print(r)
            
    # If there is a config table, check content
    if 'config' in tables:
        print("\n--- CONFIG CONTENT ---")
        c.execute("SELECT * FROM config")
        for r in c.fetchall():
            print(r)
            
    conn.close()

if __name__ == "__main__":
    list_all()

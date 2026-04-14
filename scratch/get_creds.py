import sqlite3
import os

DB_PATH = "/app/data/db_54804458000122.db"

def get_creds():
    if not os.path.exists(DB_PATH):
        print(f"DB NOT FOUND: {DB_PATH}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check table existence and columns again to be safe
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
    if not c.fetchone():
        print("Table 'config' not found.")
        return
        
    c.execute("SELECT base_mail_user, base_mail_pass, imap_server FROM config LIMIT 1")
    row = c.fetchone()
    if row:
        print(f"USER: {row[0]}")
        print(f"PASS: {row[1]}")
        print(f"IMAP: {row[2]}")
    else:
        print("No rows in config table.")
        
    conn.close()

if __name__ == "__main__":
    get_creds()

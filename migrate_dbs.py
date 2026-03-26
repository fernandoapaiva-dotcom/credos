import sqlite3
import os

def migrate_db(db_name):
    print(f"--- Migrating {db_name} ---")
    if not os.path.exists(db_name):
        return
    
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    
    # 1. Check/Add columns to config
    try:
        c.execute("PRAGMA table_info(config)")
        cols = [col[1] for col in c.fetchall()]
        
        if 'multa_fixed' not in cols:
            print("Adding multa_fixed...")
            c.execute("ALTER TABLE config ADD COLUMN multa_fixed REAL DEFAULT 2.0")
        if 'juros_mensal' not in cols:
            print("Adding juros_mensal...")
            c.execute("ALTER TABLE config ADD COLUMN juros_mensal REAL DEFAULT 1.0")
        if 'dias_para_cartorio' not in cols:
            print("Adding dias_para_cartorio...")
            c.execute("ALTER TABLE config ADD COLUMN dias_para_cartorio INTEGER DEFAULT 10")
        
        # Check if we have at least one config row to update if needed
        c.execute("SELECT COUNT(*) FROM config")
        if c.fetchone()[0] == 0:
            print("Initializing default config row...")
            c.execute("INSERT INTO config (multa_fixed, juros_mensal, dias_para_cartorio) VALUES (2.0, 1.0, 10)")
            
        conn.commit()
    except Exception as e:
        print(f"Error migrating {db_name}: {e}")
        
    conn.close()

# List databases
dbs = [f for f in os.listdir('.') if f.startswith('db_') and f.endswith('.db')]
for db in dbs:
    migrate_db(db)
print("Migration check complete.")

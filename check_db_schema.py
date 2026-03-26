import sqlite3
import os

def check_db(db_name):
    print(f"--- Checking {db_name} ---")
    if not os.path.exists(db_name):
        print("File not found.")
        return
    
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    
    # Check config schema
    print("\nConfig Schema:")
    try:
        c.execute("PRAGMA table_info(config)")
        cols = c.fetchall()
        for col in cols:
            print(col)
    except Exception as e:
        print(f"Error checking config: {e}")
        
    # Check titulos schema
    print("\nTitulos Schema:")
    try:
        c.execute("PRAGMA table_info(titulos)")
        cols = c.fetchall()
        for col in cols:
            print(col)
    except Exception as e:
        print(f"Error checking titulos: {e}")
        
    # Check sample data from titulos
    print("\nSample titles data:")
    try:
        c.execute("SELECT * FROM titulos LIMIT 5")
        rows = c.fetchall()
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error checking titles data: {e}")
    
    conn.close()

# List databases
dbs = [f for f in os.listdir('.') if f.startswith('db_') and f.endswith('.db')]
for db in dbs:
    check_db(db)

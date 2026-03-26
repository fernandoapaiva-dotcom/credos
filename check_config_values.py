import sqlite3
import os

def check_config_values(db_name):
    print(f"--- Values in {db_name} ---")
    if not os.path.exists(db_name):
        return
    
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    try:
        row = c.execute("SELECT * FROM config LIMIT 1").fetchone()
        if row:
            d = dict(row)
            print(f"multa_fixed: {d.get('multa_fixed')}")
            print(f"juros_mensal: {d.get('juros_mensal')}")
            print(f"dias_para_cartorio: {d.get('dias_para_cartorio')}")
        else:
            print("No config row found.")
    except Exception as e:
        print(f"Error: {e}")
        
    conn.close()

# List databases
dbs = [f for f in os.listdir('.') if f.startswith('db_') and f.endswith('.db')]
for db in dbs:
    check_config_values(db)

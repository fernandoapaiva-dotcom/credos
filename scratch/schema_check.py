import sqlite3
conn = sqlite3.connect('/app/data/db_54804458000122.db')
cur = conn.cursor()
cur.execute('PRAGMA table_info(documentos_fiscais)')
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()

import sqlite3, json

db_path = 'db_11504286000169.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

print('=== TABLES ===')
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
for t in tables:
    print(t[0])

print()
print('=== TITULO COLUMNS ===')
cols = conn.execute("PRAGMA table_info(titulos)").fetchall()
for c in cols:
    print(dict(c))

print()
print('=== TITULO SAMPLE ===')
rows = conn.execute('SELECT * FROM titulos LIMIT 5').fetchall()
for r in rows:
    print(dict(r))

print()
print('=== STATUS DISTRIBUTION ===')
rows = conn.execute('SELECT status, COUNT(*) as cnt FROM titulos GROUP BY status').fetchall()
for r in rows:
    print(dict(r))

print()
print('=== AUDITORIA SAMPLE ===')
try:
    rows = conn.execute('SELECT * FROM auditoria_titulos LIMIT 3').fetchall()
    for r in rows:
        print(dict(r))
except Exception as e:
    print('NO AUDITORIA:', e)

conn.close()

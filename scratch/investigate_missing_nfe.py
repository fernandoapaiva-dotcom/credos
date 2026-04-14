import sqlite3
import os

DB_PATH = "/app/data/db_54804458000122.db"

def investigate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    print("=== TODOS OS DOCUMENTOS DO DAUTO (24934648000284) ordenados por UID ===")
    c.execute("""
        SELECT id, num_nf, tipo, email_uid, created_at, fpath_local
        FROM documentos_fiscais
        WHERE cnpj_cliente = '24934648000284'
        ORDER BY email_uid
    """)
    for r in c.fetchall():
        fname = os.path.basename(r[5]) if r[5] else "N/A"
        print(f"ID:{r[0]} | NF:{r[1]} | Tipo:{r[2]} | UID:{r[3]} | Indexed:{r[4]}")
        print(f"  → {fname}")

    print("\n=== BUSCANDO NFe DE MARÇO 2026 (chave com '2603') PARA QUALQUER CLIENTE ===")
    c.execute("""
        SELECT id, cnpj_cliente, num_nf, email_uid, created_at, fpath_local
        FROM documentos_fiscais
        WHERE fpath_local LIKE '%2603%'
        OR fpath_local LIKE '%532603%'
        ORDER BY created_at DESC
        LIMIT 20
    """)
    rows = c.fetchall()
    if rows:
        for r in rows:
            print(f"ID:{r[0]} | CNPJ:{r[1]} | NF:{r[2]} | UID:{r[3]} | {r[5]}")
    else:
        print("(nenhuma NFe de março 2026 encontrada no banco)")

    print("\n=== UIDs DO ENVIADOS PRÓXIMOS A 1240 (para achar NFe companheira) ===")
    c.execute("""
        SELECT id, num_nf, tipo, email_uid, fpath_local
        FROM documentos_fiscais
        WHERE email_uid LIKE '%E-mails enviados_124%'
           OR email_uid LIKE '%E-mails enviados_125%'
           OR email_uid LIKE '%E-mails enviados_126%'
        ORDER BY email_uid
    """)
    for r in c.fetchall():
        print(f"UID:{r[3]} | NF:{r[1]} | Tipo:{r[2]} | file:{os.path.basename(r[4]) if r[4] else 'N/A'}")

    conn.close()

if __name__ == "__main__":
    investigate()

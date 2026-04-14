import sqlite3
import os
import re

db_path = '/app/data/db_54804458000122.db'
repo_path = '/app/data/repository'
cnpj_dauto = '24934648000284'

def diag():
    print("=== DIAGNÓSTICO PROFUNDO DAUTO ===")
    
    # 1. Busca no Banco
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("\n1. Verificando Banco de Dados:")
    cur.execute("SELECT num_nf, tipo, email_uid, fpath_local FROM documentos_fiscais WHERE cnpj_cliente LIKE ?", (f"%{cnpj_dauto}%",))
    rows = cur.fetchall()
    if rows:
        print(f"✅ Encontrados {len(rows)} documentos no banco para o CNPJ {cnpj_dauto}")
        for r in rows:
            print(f" - NF: {r[0]} | Tipo: {r[1]} | UID: {r[2]} | Path: {r[3]}")
    else:
        print(f"❌ Nenhum documento encontrado no banco para o CNPJ {cnpj_dauto}")

    # 2. Verifica se existem e-mails associados ao nome DAUTO nas sessões
    print("\n2. Verificando Sessões de Webhook:")
    cur.execute("SELECT id, numero_whatsapp, cliente_nome FROM webhook_sessions WHERE cliente_nome LIKE '%DAUTO%'")
    sessions = cur.fetchall()
    for s in sessions:
        print(f" - Sessão ID: {s[0]} | Whats: {s[1]} | Nome: {s[2]}")

    # 3. Busca no Sistema de Arquivos (Broad search)
    print("\n3. Buscando arquivos no Repositório (por nome):")
    matches = []
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if '382' in file or 'dauto' in file.lower():
                matches.append(os.path.join(root, file))
    
    if matches:
        print(f"✅ Encontrados {len(matches)} arquivos suspeitos no FS:")
        for m in matches[:10]:
            print(f" - {m}")
    else:
        print("❌ Nenhum arquivo com '382' ou 'dauto' encontrado via varredura simples.")

    # 4. Verifica Bundles Existentes (Geral)
    print("\n4. Verificando se existem Bundles (email_uid duplicado) gerais:")
    cur.execute("SELECT email_uid, COUNT(*) as ct FROM documentos_fiscais GROUP BY email_uid HAVING ct > 1 LIMIT 5")
    bundles = cur.fetchall()
    if bundles:
        print(f"✅ Exemplos de Bundles encontrados no sistema:")
        for b in bundles:
            print(f" - UID: {b[0]} | Qtd Docs: {b[1]}")
    else:
        print("❌ Nenhum bundle (email_uid compartilhado) encontrado no banco.")

    conn.close()

if __name__ == "__main__":
    diag()

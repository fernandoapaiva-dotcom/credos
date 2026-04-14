import sqlite3
import os

db_dir = "/app/data"
dbs = [f for f in os.listdir(db_dir) if f.startswith('db_') and f.endswith('.db')]

print(f"=== IDENTIFICADOS {len(dbs)} BANCOS DE DADOS ===")

for db_name in dbs:
    try:
        path = os.path.join(db_dir, db_name)
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        
        cnpj_unidade = db_name.replace('db_', '').replace('.db', '')
        print(f"\n📂 UNIDADE: {cnpj_unidade}")
        
        # 1. Busca Configurações de E-mail
        cur.execute("SELECT config_key, config_value FROM configuracoes WHERE config_key LIKE '%mail_user%'")
        configs = cur.fetchall()
        for k, v in configs:
            print(f"   ⚙️ {k}: {v}")
            
        # 2. Busca Documentos Pendentes do Dauto (para conferência)
        # O Fernando mencionou Dauto, vamos procurar por qualquer vestígio
        cur.execute("SELECT num_nf, cnpj_cliente, fpath_local FROM documentos_fiscais WHERE cnpj_cliente LIKE '%24934648%' OR num_nf = '382'")
        docs = cur.fetchall()
        if docs:
            print(f"   📄 Documentos encontrados: {len(docs)}")
            for d in docs[:3]:
                print(f"      - NF: {d[0]} | CNPJ: {d[1]} | Path: {d[2]}")
        
        conn.close()
    except Exception as e:
        print(f"   ❌ Erro lendo {db_name}: {e}")

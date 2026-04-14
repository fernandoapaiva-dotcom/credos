import sqlite3
import os
import sys

def migrate_schema():
    print("=== INICIANDO MIGRAÇÃO DO SCHEMA (REPOSITÓRIO FISCAL) ===")
    db_dir = "/app/data"
    dbs = [f for f in os.listdir(db_dir) if f.startswith('db_') and f.endswith('.db')]
    
    queries = [
        "ALTER TABLE documentos_fiscais ADD COLUMN nome_cliente TEXT;",
        "ALTER TABLE documentos_fiscais ADD COLUMN pasta_repo TEXT;",
        "ALTER TABLE documentos_fiscais ADD COLUMN nfs_vinculada TEXT;"
    ]

    for db_name in dbs:
        db_path = os.path.join(db_dir, db_name)
        print(f"\n📂 UNIDADE: {db_name}")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        for idx, q in enumerate(queries):
            try:
                cur.execute(q)
                print(f"   ✅ Coluna {idx+1} adicionada.")
            except sqlite3.OperationalError as e:
                # "duplicate column name" é o erro esperado se a coluna já existir, podemos ignorar.
                if "duplicate column name" in str(e).lower():
                    print(f"   ℹ️  Coluna {idx+1} já existe.")
                else:
                    print(f"   ❌ Erro na Coluna {idx+1}: {e}")
            except Exception as e:
                print(f"   ❌ Erro inesperado na Coluna {idx+1}: {e}")
        
        conn.commit()
        conn.close()

if __name__ == "__main__":
    migrate_schema()

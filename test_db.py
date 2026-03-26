from src.database import inicializar_banco, conectar, cadastrar_unidade_central, carregar_todas_unidades_db
import os

def test_multi_tenancy():
    print("🚀 Iniciando Teste Multi-Tenancy...")
    
    # 1. Limpa bancos antigos para teste limpo (opcional se quiser resetar)
    # os.remove("credos_central.db") if os.path.exists("credos_central.db") else None
    
    # 2. Inicializa central
    inicializar_banco()
    print("✅ Banco Central Inicializado.")
    
    # 3. Cadastra duas empresas
    cadastrar_unidade_central("Empresa A", "12345678000199")
    cadastrar_unidade_central("Empresa B", "98765432000100")
    print("✅ Unidades A e B cadastradas.")
    
    # 4. Verifica se arquivos foram criados
    unids = carregar_todas_unidades_db()
    print(f"📊 Unidades encontradas: {[u['empresa_nome'] for u in unids]}")
    
    for u in unids:
        cnpj = u['empresa_cnpj']
        db_file = f"db_{cnpj}.db"
        if os.path.exists(db_file):
            print(f"✅ Arquivo para {u['empresa_nome']} ({cnpj}) existe: {db_file}")
            # Tenta conectar e ver se a tabela config existe
            conn = conectar(cnpj)
            c = conn.cursor()
            c.execute("SELECT count(*) FROM config")
            print(f"   ℹ️ Tabela config inicializada com sucesso em {db_file}")
            conn.close()
        else:
            print(f"❌ Erro: Arquivo {db_file} não encontrado!")

if __name__ == "__main__":
    test_multi_tenancy()

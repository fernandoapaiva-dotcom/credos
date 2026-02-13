import sqlite3
import os

# Nome exato do banco que apareceu no seu log
NOME_BANCO = 'credos_data.db' 

def criar_colunas():
    if not os.path.exists(NOME_BANCO):
        print(f"❌ Erro: O arquivo '{NOME_BANCO}' não foi encontrado na pasta.")
        return

    print(f"🔌 Conectando ao banco {NOME_BANCO}...")
    
    try:
        conn = sqlite3.connect(NOME_BANCO)
        cursor = conn.cursor()
        
        # Colunas que precisamos criar para o E-mail Base e Financeiro
        colunas_novas = [
            "base_mail_user", "base_mail_pass", "base_imap_server",
            "fin_mail_user", "fin_mail_pass", "fin_smtp_server", "fin_imap_server"
        ]
        
        # O nome correto da tabela que vimos no seu log é 'config'
        tabela_alvo = 'config'
        
        print(f"🛠️  Atualizando tabela '{tabela_alvo}'...")
        
        colunas_criadas = 0
        for col in colunas_novas:
            try:
                # Tenta adicionar a coluna
                cursor.execute(f"ALTER TABLE {tabela_alvo} ADD COLUMN {col} TEXT")
                print(f"   ✅ Coluna '{col}' criada com sucesso!")
                colunas_criadas += 1
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"   ⚠️  Coluna '{col}' já existe (Tudo certo).")
                else:
                    print(f"   ❌ Erro ao criar '{col}': {e}")
        
        conn.commit()
        conn.close()
        
        print("\n" + "="*40)
        if colunas_criadas > 0:
            print("🏁 Sucesso! O banco foi atualizado.")
        else:
            print("🏁 Verificação concluída. As colunas já existiam.")
        print("Agora você pode salvar as configurações no sistema sem que elas sumam.")
        print("="*40)
        
    except Exception as e:
        print(f"\n❌ Erro geral de conexão: {e}")

if __name__ == "__main__":
    criar_colunas()
import sqlite3
import os

NOME_BANCO = 'credos_data.db'

def reconstruir_banco_total():
    # 1. Remove o banco antigo para evitar conflitos de colunas
    if os.path.exists(NOME_BANCO):
        os.remove(NOME_BANCO)
        print(f"🗑️ Banco antigo '{NOME_BANCO}' removido.")

    conn = sqlite3.connect(NOME_BANCO)
    cursor = conn.cursor()

    try:
        # 2. Criar Tabela de Usuários com a coluna 'login' (Exatamente como o erro pediu)
        cursor.execute('''
            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT UNIQUE NOT NULL,
                senha TEXT NOT NULL,
                nome_completo TEXT,
                perfil TEXT DEFAULT 'operador',
                status TEXT DEFAULT 'ativo',
                foto_b64 TEXT
            )
        ''')
        
        # 3. Criar Tabela de Configurações (Ajustado para 'config' ou 'configuracoes')
        # Vou criar as duas por segurança, mas o ideal é padronizar para 'config'
        cursor.execute('''
            CREATE TABLE config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                empresa_nome TEXT,
                empresa_cnpj TEXT,
                logo_b64 TEXT,
                evo_url TEXT,
                evo_key TEXT,
                gemini_api_key TEXT
            )
        ''')
        
        # Inserir um Admin padrão para você não ficar trancado fora
        cursor.execute("INSERT INTO usuarios (login, senha, nome_completo, perfil) VALUES ('admin', 'admin', 'Administrador Sistema', 'admin')")
        cursor.execute("INSERT INTO config (id, empresa_nome) VALUES (1, 'Credos SaaS')")

        conn.commit()
        print("✅ Banco reconstruído com sucesso com a coluna 'login' e 'logo_b64'!")
        
    except Exception as e:
        print(f"❌ Erro na reconstrução: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reconstruir_banco_total()
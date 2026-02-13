import sqlite3

# Nome do banco
DB_NAME = "credos_data.db"

def ajustar_admin():
    print(f"🔌 Conectando ao banco {DB_NAME}...")
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Tenta buscar pelo padrão novo 'login'
        # Se der erro aqui, é porque o banco não foi resetado com o script anterior
        try:
            existe = cursor.execute("SELECT * FROM usuarios WHERE login='admin'").fetchone()
            
            if existe:
                # 🔄 RESET DE SENHA: Força a senha para '123' no padrão novo
                cursor.execute("UPDATE usuarios SET senha='123' WHERE login='admin'")
                conn.commit()
                print("✅ Senha do 'admin' resetada para: 123")
            else:
                # ✨ CRIAÇÃO: Insere o admin se ele não existir
                cursor.execute("INSERT INTO usuarios (login, senha, nome_completo, perfil) VALUES ('admin', '123', 'Administrador', 'admin')")
                conn.commit()
                print("✅ Usuário 'admin' criado do zero.")
                
            print("👤 Login: admin | 🔑 Senha: 123")

        except sqlite3.OperationalError as e:
            if "no such column: login" in str(e):
                print("❌ Erro: O banco ainda usa 'username'. Rode o script de RESET_BANCO primeiro!")
            else:
                print(f"❌ Erro operacional: {e}")
            
        conn.close()
        
    except Exception as e:
        print(f"❌ Erro geral: {e}")

if __name__ == "__main__":
    ajustar_admin()
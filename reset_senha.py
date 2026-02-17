import sqlite3

def resolver_login():
    print("🔧 Ajustando o usuário admin...")
    conn = sqlite3.connect("credos_data.db")
    cursor = conn.cursor()

    try:
        # Insere APENAS nas colunas que realmente existem: login e password
        cursor.execute("INSERT INTO usuarios (login, password) VALUES ('admin', '123')")
        print("✅ Usuário 'admin' CRIADO com sucesso!")
    except sqlite3.IntegrityError:
        # Se o admin já existir, apenas atualiza o password
        cursor.execute("UPDATE usuarios SET password='123' WHERE login='admin'")
        print("✅ Usuário 'admin' já existia. Senha ATUALIZADA para '123'!")
        
    conn.commit()
    conn.close()
    print("🚀 Tudo pronto! Pode ir no sistema e entrar com: admin / 123")

if __name__ == "__main__":
    resolver_login()
import sqlite3

def resolver_login():
    print("🔧 Ajustando o usuário admin no banco central...")
    conn = sqlite3.connect("credos_central.db")
    cursor = conn.cursor()

    try:
        # Insere APENAS nas colunas que realmente existem: login, password, nome_completo, perfil
        cursor.execute("INSERT INTO usuarios (login, password, nome_completo, perfil) VALUES (?,?,?,?)",
                      ('admin', '123', 'Administrador', 'admin'))
        print("✅ Usuário 'admin' CRIADO com sucesso no banco central!")
    except sqlite3.IntegrityError:
        # Se o admin já existir, apenas atualiza o password
        cursor.execute("UPDATE usuarios SET password='123' WHERE login='admin'")
        print("✅ Usuário 'admin' já existia no banco central. Senha ATUALIZADA para '123'!")
        
    conn.commit()
    conn.close()
    print("🚀 Tudo pronto! Pode ir no sistema e entrar com: admin / 123")

if __name__ == "__main__":
    resolver_login()
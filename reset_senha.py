import sqlite3
import bcrypt

# Nome do banco de dados
DB_NAME = "credos_data.db"

def resetar_admin():
    print("🔄 Conectando ao banco de dados...")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Garante que a tabela existe (caso tenha sido apagada)
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT
    )''')

    # Define o usuário e senha de resgate
    usuario = "admin"
    nova_senha = "123"  # <--- SUA NOVA SENHA AQUI

    # Criptografa a senha (gera o Hash)
    hashed = bcrypt.hashpw(nova_senha.encode(), bcrypt.gensalt()).decode()

    # Verifica se o usuário já existe
    c.execute("SELECT id FROM usuarios WHERE username = ?", (usuario,))
    existe = c.fetchone()

    if existe:
        print(f"⚠️ Usuário '{usuario}' encontrado. Atualizando senha...")
        c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hashed, usuario))
    else:
        print(f"➕ Usuário '{usuario}' não existia. Criando agora...")
        c.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)", (usuario, hashed))

    conn.commit()
    conn.close()
    print(f"✅ SUCESSO! Login liberado.")
    print(f"👤 Usuário: {usuario}")
    print(f"🔑 Senha: {nova_senha}")

if __name__ == "__main__":
    resetar_admin()
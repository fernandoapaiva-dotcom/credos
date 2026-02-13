import sqlite3

def conferir_dados():
    conn = sqlite3.connect('credos_data.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("🔍 Verificando Tabela 'config'...")
    try:
        row = cursor.execute("SELECT * FROM config WHERE id = 1").fetchone()
        if row:
            dados = dict(row)
            print("✅ Registro ID 1 encontrado!")
            print(f"🏢 Empresa: {dados.get('empresa_nome')}")
            print(f"📧 Email Base: {dados.get('base_mail_user')}")
            print(f"📧 Email Fin: {dados.get('fin_mail_user')}")
            print(f"🖼️ Logo Base64: {'[PRESENTE]' if dados.get('logo_b64') else '[VAZIO]'}")
        else:
            print("❌ Registro ID 1 NÃO encontrado na tabela 'config'.")
    except Exception as e:
        print(f"❌ Erro ao ler tabela 'config': {e}")
    
    print("\n👥 Verificando Tabela 'usuarios'...")
    try:
        users = cursor.execute("SELECT login, perfil FROM usuarios").fetchall()
        print(f"✅ Encontrados {len(users)} usuários.")
        for u in users:
            print(f" - {u['login']} ({u['perfil']})")
    except Exception as e:
        print(f"❌ Erro ao ler tabela 'usuarios': {e}")

    conn.close()

if __name__ == "__main__":
    conferir_dados()
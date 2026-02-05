import sqlite3
import json
import os
import bcrypt

DB_NAME = "credos_data.db"

def conectar():
    return sqlite3.connect(DB_NAME)

def inicializar_banco():
    conn = conectar()
    c = conn.cursor()
    
    # Tabela de Configurações Gerais
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chave TEXT UNIQUE,
        valor TEXT
    )''')

    # Tabela de Empresas (Unidades/Filiais)
    c.execute('''CREATE TABLE IF NOT EXISTS empresas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_nome TEXT,
        empresa_cnpj TEXT,
        logo_b64 TEXT,
        imap_server TEXT,
        smtp_server TEXT,
        mail_user TEXT,
        mail_pass TEXT,
        mail_base_user TEXT,
        mail_base_pass TEXT,
        evo_url TEXT,
        evo_key TEXT,
        evo_inst TEXT,
        gemini_key TEXT,
        email_envio_display TEXT
    )''')

    # Tabela de Clientes
    # Adicionamos 'contato' (Pessoa de referência)
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_dona_cnpj TEXT,
        nome TEXT,
        cnpj TEXT,
        whatsapp TEXT,
        email TEXT,
        contato TEXT 
    )''')
    
    # Migração segura: Adiciona coluna 'contato' se não existir em bancos antigos
    try:
        c.execute("ALTER TABLE clientes ADD COLUMN contato TEXT")
    except sqlite3.OperationalError:
        pass # Coluna já existe

    # Tabela de Títulos
    c.execute('''CREATE TABLE IF NOT EXISTS titulos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_dona_cnpj TEXT,
        pagador TEXT,
        numero_nf TEXT,
        vencimento TEXT,
        valor REAL,
        status TEXT,
        acao TEXT,
        data_promessa TEXT,
        historico_obs TEXT
    )''')

    # Tabela de Logs de Envio
    c.execute('''CREATE TABLE IF NOT EXISTS logs_envio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_hora TEXT,
        cliente TEXT,
        tipo TEXT,
        status TEXT,
        detalhe TEXT
    )''')

    # Tabela de Usuários (Login)
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT
    )''')

    conn.commit()
    conn.close()

# --- FUNÇÕES DE CONFIGURAÇÃO ---
def salvar_configuracoes_db(config_dict):
    if not config_dict: return
    cnpj = config_dict.get('empresa_cnpj')
    conn = conectar()
    c = conn.cursor()
    
    # Verifica se já existe config para este CNPJ (ou cria nova se não tiver CNPJ ainda)
    if cnpj:
        c.execute("SELECT id FROM empresas WHERE empresa_cnpj = ?", (cnpj,))
        existe = c.fetchone()
    else:
        existe = None

    colunas = [
        "empresa_nome", "empresa_cnpj", "logo_b64", 
        "imap_server", "smtp_server", "mail_user", "mail_pass", 
        "mail_base_user", "mail_base_pass", "evo_url", "evo_key", "evo_inst",
        "gemini_key", "email_envio_display"
    ]
    vals = [config_dict.get(k, "") for k in colunas]

    if existe:
        set_query = ", ".join([f"{col}=?" for col in colunas])
        c.execute(f"UPDATE empresas SET {set_query} WHERE id=?", vals + [existe[0]])
    else:
        q_placeholders = ", ".join(["?" for _ in colunas])
        c.execute(f"INSERT INTO empresas ({', '.join(colunas)}) VALUES ({q_placeholders})", vals)
    
    conn.commit()
    conn.close()

def carregar_configuracoes_db(cnpj_alvo=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if cnpj_alvo:
        c.execute("SELECT * FROM empresas WHERE empresa_cnpj = ?", (cnpj_alvo,))
    else:
        c.execute("SELECT * FROM empresas ORDER BY id DESC LIMIT 1")
    
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}

def carregar_todas_unidades_db():
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM empresas")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def excluir_unidade_db(id_unidade):
    conn = conectar()
    c = conn.cursor()
    c.execute("DELETE FROM empresas WHERE id = ?", (id_unidade,))
    conn.commit()
    conn.close()

# --- FUNÇÕES DE CLIENTES ---
def listar_clientes_db():
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM clientes ORDER BY nome")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_cliente_db(nome, cnpj, whatsapp, email, contato=""):
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT id FROM clientes WHERE nome = ?", (nome,))
    existe = c.fetchone()
    
    # Limpa Whatsapp
    zap_clean = "".join(filter(str.isdigit, str(whatsapp))) if whatsapp else ""
    if zap_clean and not zap_clean.startswith("55") and len(zap_clean) > 9:
        zap_clean = "55" + zap_clean

    if existe:
        c.execute("""UPDATE clientes SET 
            cnpj=?, whatsapp=?, email=?, contato=?
            WHERE id=?""", (cnpj, zap_clean, email, contato, existe[0]))
    else:
        c.execute("""INSERT INTO clientes (empresa_dona_cnpj, nome, cnpj, whatsapp, email, contato)
            VALUES (?, ?, ?, ?, ?, ?)""", ("TRV", nome, cnpj, zap_clean, email, contato))
    conn.commit()
    conn.close()

def excluir_cliente_db(id_cli, nome_cli):
    conn = conectar()
    c = conn.cursor()
    c.execute("DELETE FROM clientes WHERE id = ?", (id_cli,))
    c.execute("DELETE FROM titulos WHERE pagador = ?", (nome_cli,))
    conn.commit()
    conn.close()

# --- FUNÇÕES DE TÍTULOS ---
def salvar_dados_no_banco(lista_dicts, empresa_dona_cnpj):
    conn = conectar()
    c = conn.cursor()
    for item in lista_dicts:
        c.execute("SELECT id FROM titulos WHERE numero_nf = ? AND pagador = ?", (item['numero'], item['pagador']))
        existe = c.fetchone()
        if not existe:
            c.execute("""
            INSERT INTO titulos (empresa_dona_cnpj, pagador, numero_nf, vencimento, valor, status, acao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (empresa_dona_cnpj, item['pagador'], item['numero'], item['vencimento'], item['valor'], 'Aberto', 'Cobrar'))
    conn.commit()
    conn.close()

def listar_titulos_por_cliente(nome_cliente):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM titulos WHERE pagador = ?", (nome_cliente,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def atualizar_titulo_acao(id_titulo, nova_acao):
    conn = conectar()
    c = conn.cursor()
    c.execute("UPDATE titulos SET acao = ? WHERE id = ?", (nova_acao, id_titulo))
    conn.commit()
    conn.close()

# --- FUNÇÕES DE LOG E CHAT ---
def salvar_log_envio(cliente, tipo, status, detalhe):
    conn = conectar()
    c = conn.cursor()
    import datetime
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
    c.execute("INSERT INTO logs_envio (data_hora, cliente, tipo, status, detalhe) VALUES (?, ?, ?, ?, ?)",
              (now, cliente, tipo, status, detalhe))
    conn.commit()
    conn.close()

def listar_logs_cliente(cliente):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM logs_envio WHERE cliente = ? ORDER BY id DESC", (cliente,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_chat_whatsapp(cliente, remetente, mensagem):
    # Simulação para futuro RAG
    pass

def listar_chat_cliente(cliente):
    return []

# --- LOGIN E SEGURANÇA ---
def criar_usuario(username, password):
    conn = conectar()
    c = conn.cursor()
    try:
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        c.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)", (username, hashed))
        conn.commit()
        return True, "Usuário criado."
    except sqlite3.IntegrityError:
        return False, "Usuário já existe."
    finally:
        conn.close()

def verificar_login(username, password):
    conn = conectar()
    c = conn.cursor()
    c.execute("SELECT password_hash FROM usuarios WHERE username = ?", (username,))
    res = c.fetchone()
    conn.close()
    if res:
        return bcrypt.checkpw(password.encode(), res[0].encode())
    return False

def alterar_senha_usuario(username, new_pass):
    conn = conectar()
    c = conn.cursor()
    hashed = bcrypt.hashpw(new_pass.encode(), bcrypt.gensalt()).decode()
    c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hashed, username))
    conn.commit()
    conn.close()

def listar_usuarios():
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, username FROM usuarios")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def excluir_usuario(uid):
    conn = conectar()
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
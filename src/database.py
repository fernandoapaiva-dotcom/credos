import sqlite3
import os
import json

# Caminho do banco
DB_PATH = "data/credos_saas.db"

def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_banco():
    conn = get_connection()
    cursor = conn.cursor()
    
    # ... (TABELAS ANTERIORES: usuarios, configuracoes - MANTENHA IGUAL) ...
    # Se quiser, apenas copie as tabelas novas abaixo e rode a migração
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    
    # Cria usuário padrão
    cursor.execute("SELECT count(*) as total FROM usuarios")
    if cursor.fetchone()['total'] == 0:
        cursor.execute("INSERT INTO usuarios (username, password) VALUES ('admin', 'admin123')")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_nome TEXT, empresa_cnpj TEXT UNIQUE, logo_b64 TEXT,
            mail_user TEXT, mail_pass TEXT, smtp_server TEXT,
            mail_base_user TEXT, mail_base_pass TEXT, imap_server TEXT, email_envio_display TEXT,
            gemini_key TEXT, evo_key TEXT, evo_url TEXT,
            agenda_dias TEXT, agenda_hora TEXT,
            auto_scan INTEGER, auto_zap INTEGER, auto_mail INTEGER
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            cnpj TEXT,
            whatsapp TEXT,
            email TEXT,
            data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS titulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj_credor TEXT,
            vencimento DATE,
            numero_nf TEXT,
            valor REAL,
            pagador TEXT,
            status TEXT DEFAULT 'Aberto', -- Aberto, Pago, Negociado
            arquivo_origem TEXT,
            UNIQUE(numero_nf, cnpj_credor)
        )
    """)

    # --- NOVAS TABELAS PARA HISTÓRICO ---
    
    # 1. Logs de Envio (Sistema -> Cliente)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs_envio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            tipo TEXT, -- 'WhatsApp' ou 'Email'
            mensagem TEXT,
            status TEXT, -- 'Sucesso' ou 'Falha'
            data_envio DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Histórico de Chat (Conversa completa WhatsApp)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            remetente TEXT, -- 'Bot/Atendente' ou 'Cliente'
            mensagem TEXT,
            data_hora DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    migrar_banco_existente(conn)
    conn.close()

# ... (MANTENHA AS FUNÇÕES migrar_banco, verificar_login, alterar_senha, ETC.) ...

# --- FUNÇÕES PARA CHAT E LOGS ---

def salvar_log_envio(cliente, tipo, msg, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO logs_envio (cliente_nome, tipo, mensagem, status) VALUES (?,?,?,?)", 
                   (cliente, tipo, msg, status))
    conn.commit()
    conn.close()

def salvar_chat_whatsapp(cliente, remetente, msg):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chat_logs (cliente_nome, remetente, mensagem) VALUES (?,?,?)", 
                   (cliente, remetente, msg))
    conn.commit()
    conn.close()

def listar_logs_cliente(cliente_nome):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs_envio WHERE cliente_nome = ? ORDER BY data_envio DESC", (cliente_nome,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def listar_chat_cliente(cliente_nome):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM chat_logs WHERE cliente_nome = ? ORDER BY data_hora ASC", (cliente_nome,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# Caminho do banco
DB_PATH = "data/credos_saas.db"

def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # Permite acessar colunas pelo nome
    return conn

def inicializar_banco():
    """Cria tabelas se não existirem e aplica atualizações (migrações)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Tabela de Usuários (Login)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    
    # Cria usuário padrão se não existir
    cursor.execute("SELECT count(*) as total FROM usuarios")
    if cursor.fetchone()['total'] == 0:
        cursor.execute("INSERT INTO usuarios (username, password) VALUES ('admin', 'admin123')")
        print("🔐 Usuário padrão criado: admin / admin123")
    
    # 2. Tabela de Configurações
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_nome TEXT,
            empresa_cnpj TEXT UNIQUE,
            logo_b64 TEXT,
            
            -- E-mails e Servidores
            mail_user TEXT, mail_pass TEXT, smtp_server TEXT,
            mail_base_user TEXT, mail_base_pass TEXT, imap_server TEXT, email_envio_display TEXT,
            
            -- IA e API
            gemini_key TEXT, evo_key TEXT, evo_url TEXT,
            
            -- Robô e Agendamento
            agenda_dias TEXT, agenda_hora TEXT,
            auto_scan INTEGER, auto_zap INTEGER, auto_mail INTEGER
        )
    """)
    
    # 3. Tabela de Clientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE,
            cnpj TEXT,
            whatsapp TEXT,
            email TEXT
        )
    """)
    
    # 4. Tabela de Títulos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS titulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cnpj_credor TEXT,
            vencimento DATE,
            numero_nf TEXT,
            valor REAL,
            pagador TEXT,
            status TEXT DEFAULT 'Aberto',
            UNIQUE(numero_nf, cnpj_credor)
        )
    """)
    
    conn.commit()
    migrar_banco_existente(conn)
    conn.close()

def migrar_banco_existente(conn):
    """Verifica e cria colunas novas em bancos antigos."""
    cursor = conn.cursor()
    colunas_necessarias = [
        ("mail_pass", "TEXT"), ("smtp_server", "TEXT"), ("email_envio_display", "TEXT"),
        ("mail_base_user", "TEXT"), ("mail_base_pass", "TEXT"), ("imap_server", "TEXT"),
        ("agenda_dias", "TEXT"), ("agenda_hora", "TEXT"),
        ("auto_scan", "INTEGER"), ("auto_zap", "INTEGER"), ("auto_mail", "INTEGER")
    ]
    cursor.execute("PRAGMA table_info(configuracoes)")
    colunas_atuais = [info[1] for info in cursor.fetchall()]
    
    for nome_col, tipo_col in colunas_necessarias:
        if nome_col not in colunas_atuais:
            try:
                cursor.execute(f"ALTER TABLE configuracoes ADD COLUMN {nome_col} {tipo_col}")
            except Exception:
                pass
    conn.commit()

# --- FUNÇÕES DE USUÁRIO/LOGIN ---

def verificar_login(user, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username = ? AND password = ?", (user, password))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def alterar_senha_admin(nova_senha):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE usuarios SET password = ? WHERE username = 'admin'", (nova_senha,))
        conn.commit()
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        conn.close()

# --- FUNÇÕES DE CONFIGURAÇÃO (EMPRESAS) ---

def salvar_configuracoes_db(conf):
    conn = get_connection()
    cursor = conn.cursor()
    
    dias_json = json.dumps(conf.get('agenda_dias', []))
    scan_int = 1 if conf.get('auto_scan') else 0
    zap_int = 1 if conf.get('auto_zap') else 0
    mail_int = 1 if conf.get('auto_mail') else 0
    
    cursor.execute("""
        INSERT OR REPLACE INTO configuracoes (
            id, empresa_nome, empresa_cnpj, logo_b64, 
            mail_user, mail_pass, smtp_server,
            mail_base_user, mail_base_pass, imap_server, email_envio_display,
            gemini_key, evo_key, evo_url,
            agenda_dias, agenda_hora, auto_scan, auto_zap, auto_mail
        ) VALUES (
            (SELECT id FROM configuracoes WHERE empresa_cnpj = ?),
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        conf['empresa_cnpj'],
        conf.get('empresa_nome'), conf.get('empresa_cnpj'), conf.get('logo_b64'),
        conf.get('mail_user'), conf.get('mail_pass'), conf.get('smtp_server'),
        conf.get('mail_base_user'), conf.get('mail_base_pass'), conf.get('imap_server'), conf.get('email_envio_display'),
        conf.get('gemini_key'), conf.get('evo_key'), conf.get('evo_url'),
        dias_json, conf.get('agenda_hora'), scan_int, zap_int, mail_int
    ))
    conn.commit()
    conn.close()

def carregar_configuracoes_db(cnpj=None):
    conn = get_connection()
    cursor = conn.cursor()
    if cnpj:
        cursor.execute("SELECT * FROM configuracoes WHERE empresa_cnpj = ?", (cnpj,))
    else:
        cursor.execute("SELECT * FROM configuracoes ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        d = dict(row)
        try: d['agenda_dias'] = json.loads(d['agenda_dias']) if d.get('agenda_dias') else []
        except: d['agenda_dias'] = []
        d['auto_scan'] = bool(d.get('auto_scan'))
        d['auto_zap'] = bool(d.get('auto_zap'))
        d['auto_mail'] = bool(d.get('auto_mail'))
        return d
    return {}

def carregar_todas_unidades_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM configuracoes")
    rows = cursor.fetchall()
    conn.close()
    
    lista = []
    for row in rows:
        d = dict(row)
        try: d['agenda_dias'] = json.loads(d['agenda_dias']) if d.get('agenda_dias') else []
        except: d['agenda_dias'] = []
        d['auto_scan'] = bool(d.get('auto_scan'))
        d['auto_zap'] = bool(d.get('auto_zap'))
        d['auto_mail'] = bool(d.get('auto_mail'))
        lista.append(d)
    return lista

def excluir_unidade_db(id_empresa):
    if not id_empresa: return False
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM configuracoes WHERE id = ?", (id_empresa,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

# --- FUNÇÕES DE DADOS (TÍTULOS E CLIENTES) ---

def salvar_dados_no_banco(lista, cnpj_credor):
    conn = get_connection()
    cursor = conn.cursor()
    for t in lista:
        numero = t.get('numero') or t.get('numero_nf')
        cursor.execute("""
            INSERT OR IGNORE INTO titulos (cnpj_credor, vencimento, numero_nf, valor, pagador)
            VALUES (?, ?, ?, ?, ?)
        """, (cnpj_credor, t['vencimento'], numero, t['valor'], t['pagador']))
    conn.commit()
    conn.close()

def listar_clientes_db():
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes") 
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def excluir_cliente_db(id_cliente):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM clientes WHERE id = ?", (id_cliente,))
    conn.commit()
    conn.close()
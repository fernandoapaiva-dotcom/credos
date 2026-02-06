import sqlite3
import bcrypt
import datetime
import json

DB_NAME = "credos_data.db"

def conectar():
    # check_same_thread=False é crucial para o Streamlit não travar o banco
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def inicializar_banco():
    with conectar() as conn:
        c = conn.cursor()
        # Tabelas Core
        c.execute('''CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY AUTOINCREMENT, chave TEXT UNIQUE, valor TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_nome TEXT, empresa_cnpj TEXT, logo_b64 TEXT,
            imap_server TEXT, smtp_server TEXT, mail_user TEXT, mail_pass TEXT,
            mail_base_user TEXT, mail_base_pass TEXT,
            evo_url TEXT, evo_key TEXT, evo_inst TEXT, gemini_key TEXT, email_envio_display TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_dona_cnpj TEXT,
            nome TEXT, cnpj TEXT, whatsapp TEXT, email TEXT, contato TEXT 
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS titulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_dona_cnpj TEXT,
            pagador TEXT, numero_nf TEXT, vencimento TEXT, valor REAL,
            status TEXT, acao TEXT, data_promessa TEXT, historico_obs TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS logs_envio (
            id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, cliente TEXT, tipo TEXT, status TEXT, detalhe TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT
        )''')
        # GARANTINDO A TABELA DE LAYOUTS
        c.execute('''CREATE TABLE IF NOT EXISTS layouts_importacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_dona_cnpj TEXT, nome_layout TEXT,
            col_vencimento TEXT, col_numero TEXT, col_valor TEXT, col_pagador TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS agendamento (
            id INTEGER PRIMARY KEY AUTOINCREMENT, empresa_dona_cnpj TEXT UNIQUE,
            dias_semana TEXT, horario_envio TEXT, pular_feriados INTEGER, ativo INTEGER
        )''')
        conn.commit()

# --- EMPRESAS ---
def salvar_configuracoes_db(config_dict):
    if not config_dict: return
    cnpj = str(config_dict.get('empresa_cnpj', '')).strip() # Garante string
    with conectar() as conn:
        c = conn.cursor()
        existe = None
        if cnpj:
            c.execute("SELECT id FROM empresas WHERE empresa_cnpj = ?", (cnpj,))
            existe = c.fetchone()
        
        cols = ["empresa_nome", "empresa_cnpj", "logo_b64", "imap_server", "smtp_server", "mail_user", "mail_pass", "mail_base_user", "mail_base_pass", "evo_url", "evo_key", "evo_inst", "gemini_key", "email_envio_display"]
        vals = [str(config_dict.get(k, "")) for k in cols]
        
        if existe:
            set_q = ", ".join([f"{col}=?" for col in cols])
            c.execute(f"UPDATE empresas SET {set_q} WHERE id=?", vals + [existe[0]])
        else:
            q_p = ", ".join(["?" for _ in cols])
            c.execute(f"INSERT INTO empresas ({', '.join(cols)}) VALUES ({q_p})", vals)
        conn.commit()

def carregar_configuracoes_db(cnpj_alvo=None):
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        if cnpj_alvo: 
            c.execute("SELECT * FROM empresas WHERE empresa_cnpj = ?", (str(cnpj_alvo),))
        else: 
            c.execute("SELECT * FROM empresas ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        return dict(row) if row else {}

def carregar_todas_unidades_db():
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM empresas")
        return [dict(r) for r in c.fetchall()]

# --- CLIENTES ---
def listar_clientes_db(cnpj_dono):
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM clientes WHERE empresa_dona_cnpj = ? ORDER BY nome", (str(cnpj_dono),))
        return [dict(r) for r in c.fetchall()]

def salvar_cliente_db(cnpj_dono, nome, cnpj_cliente, whatsapp, email, contato=""):
    zap_final = ""
    if whatsapp:
        raw = str(whatsapp).replace(";", ",")
        lista = []
        for num in raw.split(","):
            clean = "".join(filter(str.isdigit, num))
            if clean:
                if not clean.startswith("55") and len(clean) > 9: clean = "55" + clean
                lista.append(clean)
        zap_final = ",".join(lista)
    with conectar() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM clientes WHERE nome = ? AND empresa_dona_cnpj = ?", (nome, str(cnpj_dono)))
        existe = c.fetchone()
        if existe: c.execute("UPDATE clientes SET cnpj=?, whatsapp=?, email=?, contato=? WHERE id=?", (cnpj_cliente, zap_final, email, contato, existe[0]))
        else: c.execute("INSERT INTO clientes (empresa_dona_cnpj, nome, cnpj, whatsapp, email, contato) VALUES (?, ?, ?, ?, ?, ?)", (str(cnpj_dono), nome, cnpj_cliente, zap_final, email, contato))
        conn.commit()

def excluir_cliente_db(id_cli, nome_cli):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM clientes WHERE id = ?", (id_cli,))
        c.execute("DELETE FROM titulos WHERE pagador = ?", (nome_cli,))
        conn.commit()

# --- TITULOS ---
def salvar_dados_no_banco(lista_dicts, empresa_dona_cnpj):
    dono = str(empresa_dona_cnpj)
    with conectar() as conn:
        c = conn.cursor()
        for item in lista_dicts:
            c.execute("SELECT id FROM titulos WHERE numero_nf = ? AND pagador = ? AND empresa_dona_cnpj = ?", (item['numero'], item['pagador'], dono))
            if not c.fetchone():
                c.execute("INSERT INTO titulos (empresa_dona_cnpj, pagador, numero_nf, vencimento, valor, status, acao) VALUES (?, ?, ?, ?, ?, ?, ?)", (dono, item['pagador'], item['numero'], item['vencimento'], item['valor'], 'Aberto', 'Cobrar'))
        conn.commit()

def listar_titulos_por_cliente(nome_cliente, cnpj_dono):
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM titulos WHERE pagador = ? AND empresa_dona_cnpj = ?", (nome_cliente, str(cnpj_dono)))
        return [dict(r) for r in c.fetchall()]

def atualizar_titulo_status_acao(id_titulo, novo_status, nova_acao):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("UPDATE titulos SET status = ?, acao = ? WHERE id = ?", (novo_status, nova_acao, id_titulo))
        conn.commit()

# === FUNÇÃO REINSERIDA ===
def atualizar_titulo_acao(id_titulo, nova_acao):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("UPDATE titulos SET acao = ? WHERE id = ?", (nova_acao, id_titulo))
        conn.commit()
# =========================

# --- LAYOUTS (Onde o Itau é salvo) ---
def salvar_layout_db(cnpj_dono, nome_layout, mapa):
    dono = str(cnpj_dono).strip() # Força string limpa
    nome = str(nome_layout).strip()
    
    print(f"DEBUG DB: Salvando layout '{nome}' para CNPJ '{dono}'") # Debug no terminal
    
    with conectar() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM layouts_importacao WHERE empresa_dona_cnpj = ? AND nome_layout = ?", (dono, nome))
        existe = c.fetchone()
        
        if existe:
            c.execute("UPDATE layouts_importacao SET col_vencimento=?, col_numero=?, col_valor=?, col_pagador=? WHERE id=?", 
                     (mapa['vencimento'], mapa['numero'], mapa['valor'], mapa['pagador'], existe[0]))
        else:
            c.execute("INSERT INTO layouts_importacao (empresa_dona_cnpj, nome_layout, col_vencimento, col_numero, col_valor, col_pagador) VALUES (?, ?, ?, ?, ?, ?)", 
                     (dono, nome, mapa['vencimento'], mapa['numero'], mapa['valor'], mapa['pagador']))
        conn.commit()
        print("DEBUG DB: Layout Salvo e Commitado.")

def listar_layouts_db(cnpj_dono):
    dono = str(cnpj_dono).strip()
    print(f"DEBUG DB: Buscando layouts para CNPJ '{dono}'")
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM layouts_importacao WHERE empresa_dona_cnpj = ? ORDER BY nome_layout", (dono,))
        res = [dict(r) for r in c.fetchall()]
        print(f"DEBUG DB: Encontrados {len(res)} layouts.")
        return res

def excluir_layout_db(id_layout):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM layouts_importacao WHERE id = ?", (id_layout,))
        conn.commit()

# --- AGENDAMENTO ---
def salvar_agendamento_db(cnpj, dias, horario, pular_fer, ativo):
    dono = str(cnpj).strip()
    with conectar() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM agendamento WHERE empresa_dona_cnpj = ?", (dono,))
        existe = c.fetchone()
        dias_str = ",".join(map(str, dias))
        if existe: c.execute("UPDATE agendamento SET dias_semana=?, horario_envio=?, pular_feriados=?, ativo=? WHERE empresa_dona_cnpj=?", (dias_str, horario, pular_fer, ativo, dono))
        else: c.execute("INSERT INTO agendamento (empresa_dona_cnpj, dias_semana, horario_envio, pular_feriados, ativo) VALUES (?, ?, ?, ?, ?)", (dono, dias_str, horario, pular_fer, ativo))
        conn.commit()

def carregar_agendamento_db(cnpj):
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM agendamento WHERE empresa_dona_cnpj = ?", (str(cnpj),))
        res = c.fetchone()
        return dict(res) if res else None

# --- LOGS E USUARIOS ---
def salvar_log_envio(cliente, tipo, status, detalhe):
    with conectar() as conn:
        c = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO logs_envio (data_hora, cliente, tipo, status, detalhe) VALUES (?, ?, ?, ?, ?)", (now, cliente, tipo, status, detalhe))
        conn.commit()

def listar_logs_cliente_db(nome_cliente):
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM logs_envio WHERE cliente = ? ORDER BY data_hora DESC", (nome_cliente,))
        return [dict(r) for r in c.fetchall()]

def criar_usuario(u, p):
    with conectar() as conn:
        c = conn.cursor()
        try:
            hashed = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
            c.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)", (u, hashed))
            conn.commit()
            return True, "Criado."
        except sqlite3.IntegrityError: return False, "Já existe."

def verificar_login(u, p):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("SELECT password_hash FROM usuarios WHERE username = ?", (u,))
        res = c.fetchone()
        if res: return bcrypt.checkpw(p.encode(), res[0].encode())
        return False

def alterar_senha_usuario(u, new_p):
    with conectar() as conn:
        c = conn.cursor()
        hashed = bcrypt.hashpw(new_p.encode(), bcrypt.gensalt()).decode()
        c.execute("UPDATE usuarios SET password_hash = ? WHERE username = ?", (hashed, u))
        conn.commit()

def listar_usuarios():
    with conectar() as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, username FROM usuarios")
        return [dict(r) for r in c.fetchall()]

def excluir_usuario(uid):
    with conectar() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM usuarios WHERE id = ?", (uid,))
        conn.commit()
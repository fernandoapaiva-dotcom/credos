import sqlite3
import json
import os
from datetime import datetime

# Nome do banco de dados
DB_NAME = "credos_data.db"

def conectar():
    return sqlite3.connect(DB_NAME)

def inicializar_banco():
    """Cria as tabelas iniciais se não existirem com a estrutura completa."""
    conn = conectar()
    c = conn.cursor()
    
    # 1. Configurações (CHAVES PADRONIZADAS)
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_nome TEXT, empresa_cnpj TEXT,
        gemini_api_key TEXT, evo_url TEXT, evo_key TEXT,
        base_mail_user TEXT, base_mail_pass TEXT, imap_server TEXT,
        fin_mail_user TEXT, fin_mail_pass TEXT, smtp_server TEXT,
        logo_b64 TEXT
    )''')
    if c.execute("SELECT count(*) FROM config").fetchone()[0] == 0:
        c.execute("INSERT INTO config (empresa_nome) VALUES ('Minha Empresa')")
    
    # 2. Clientes
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cnpj TEXT, whatsapp TEXT, email TEXT, contato TEXT
    )''')
    
    # 3. Títulos
    c.execute('''CREATE TABLE IF NOT EXISTS titulos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pagador TEXT, numero_nf TEXT, vencimento TEXT, valor REAL,
        status TEXT DEFAULT 'Aberto', acao TEXT DEFAULT 'Cobrar'
    )''')
    
    # 4. Usuários (ESTRUTURA COMPLETA CORRIGIDA)
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE, 
        password TEXT, 
        nome_completo TEXT, 
        perfil TEXT DEFAULT 'operador', 
        status TEXT DEFAULT 'Ativo',
        foto_b64 TEXT
    )''')
    
    # 5. Agendamento
    c.execute('''CREATE TABLE IF NOT EXISTS agendamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dias_ui TEXT, horario_envio TEXT, pular_feriados INTEGER, ativo INTEGER
    )''')

    # 6. Layouts de Importação
    c.execute('''CREATE TABLE IF NOT EXISTS layouts_importacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_layout TEXT,
        col_vencimento TEXT, col_numero TEXT, col_valor TEXT, col_pagador TEXT
    )''')

    # 8. Auditoria de Títulos
    c.execute('''CREATE TABLE IF NOT EXISTS auditoria_titulos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo_id INTEGER,
        usuario TEXT,
        data_hora TEXT,
        status_anterior TEXT,
        status_novo TEXT,
        acao TEXT,
        FOREIGN KEY(titulo_id) REFERENCES titulos(id)
    )''')
    
    conn.commit()
    conn.close()

# ==============================================================================
# 1. CONFIGURAÇÕES
# ==============================================================================
def carregar_configuracoes_db(cnpj_empresa=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        if cnpj_empresa:
            query = "SELECT * FROM config WHERE empresa_cnpj = ? LIMIT 1"
            row = c.execute(query, (cnpj_empresa,)).fetchone()
        else:
            row = c.execute("SELECT * FROM config LIMIT 1").fetchone()
        
        if row:
            config_dict = dict(row)
            print(f"✅ Configurações carregadas para: {config_dict.get('empresa_nome', 'Desconhecido')}")
            return config_dict
        return {}
    except Exception as e:
        print(f"❌ Erro ao carregar config: {e}")
        return {}
    finally:
        conn.close()

def salvar_configuracoes_db(novos_dados: dict):
    if not novos_dados: return
    conn = conectar()
    c = conn.cursor()
    TABELA = "config" 
    try:
        c.execute(f"PRAGMA table_info({TABELA})")
        colunas_banco = [info[1] for info in c.fetchall()]
        dados_validos = {k: v for k, v in novos_dados.items() if k in colunas_banco}
        
        if not dados_validos: return

        c.execute(f"SELECT count(*) FROM {TABELA}")
        if c.fetchone()[0] == 0:
            c.execute(f"INSERT INTO {TABELA} (id) VALUES (1)")

        set_clause = ", ".join([f"{key} = ?" for key in dados_validos.keys()])
        valores = list(dados_validos.values())
        query = f"UPDATE {TABELA} SET {set_clause} WHERE id = 1"
        
        c.execute(query, valores)
        conn.commit()
        print(f"✅ Sucesso! {len(dados_validos)} campos salvos.")
    except Exception as e:
        print(f"❌ Erro ao salvar config: {e}")
    finally:
        conn.close()

# ==============================================================================
# 2. CLIENTES
# ==============================================================================
def listar_clientes_db(cnpj_empresa=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    res = conn.cursor().execute("SELECT * FROM clientes").fetchall()
    conn.close()
    return [dict(r) for r in res]

def verificar_cliente_existe(nome_cliente):
    conn = conectar()
    res = conn.cursor().execute("SELECT id FROM clientes WHERE nome=?", (nome_cliente,)).fetchone()
    conn.close()
    return res is not None

def salvar_cliente_db(nome, cnpj, whatsapp, email, contato=None):
    conn = conectar()
    c = conn.cursor()
    if not verificar_cliente_existe(nome):
        c.execute("INSERT INTO clientes (nome, cnpj, whatsapp, email, contato) VALUES (?,?,?,?,?)",
                  (nome, cnpj, whatsapp, email, contato if contato else ""))
    else:
        c.execute("UPDATE clientes SET cnpj=?, whatsapp=?, email=?, contato=? WHERE nome=?",
                  (cnpj, whatsapp, email, contato if contato else "", nome))
    conn.commit()
    conn.close()

def excluir_cliente_db(id_cliente, nome_cliente, usuario=None):
    conn = conectar()
    conn.cursor().execute("DELETE FROM clientes WHERE id=?", (id_cliente,))
    conn.cursor().execute("DELETE FROM titulos WHERE pagador=?", (nome_cliente,))
    conn.commit()
    conn.close()
    if usuario:
        salvar_log_envio(nome_cliente, "Exclusão CRM", "Sucesso", f"Cliente e títulos excluídos", usuario=usuario)

# ==============================================================================
# 3. TÍTULOS FINANCEIROS
# ==============================================================================
def salvar_dados_no_banco(titulos, cnpj_empresa=None):
    conn = conectar()
    c = conn.cursor()
    for t in titulos:
        # Verifica se título existe considerando Número, Pagador e Vencimento (para parcelas)
        exists = c.execute(
            "SELECT id FROM titulos WHERE numero_nf=? AND pagador=? AND vencimento=?", 
            (t['numero'], t['pagador'], t['vencimento'])
        ).fetchone()
        
        if not exists:
            c.execute("INSERT INTO titulos (pagador, numero_nf, vencimento, valor) VALUES (?,?,?,?)", 
                      (t['pagador'], t['numero'], t['vencimento'], t['valor']))
    conn.commit()
    conn.close()

def listar_titulos_por_cliente(nome_cliente, cnpj_empresa=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    res = conn.cursor().execute("SELECT * FROM titulos WHERE pagador=?", (nome_cliente,)).fetchall()
    conn.close()
    return [dict(r) for r in res]

def atualizar_titulo_acao(id_titulo, nova_acao, novo_status=None):
    conn = conectar()
    c = conn.cursor()
    if novo_status:
        c.execute("UPDATE titulos SET acao = ?, status = ? WHERE id = ?", (nova_acao, novo_status, id_titulo))
    else:
        c.execute("UPDATE titulos SET acao = ? WHERE id = ?", (nova_acao, id_titulo))
    conn.commit()
    conn.close()

def atualizar_titulo_status_acao(id_titulo, novo_status, nova_acao):
    return atualizar_titulo_acao(id_titulo, nova_acao, novo_status)

# ==============================================================================
# 4. LAYOUTS
# ==============================================================================
def obter_layouts_bancos(cnpj_empresa=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("SELECT * FROM layouts_importacao").fetchall()
        return [dict(r) for r in res]
    finally:
        conn.close()

def salvar_layout_preferido(nome, mapa):
    conn = conectar()
    conn.cursor().execute("""
        INSERT INTO layouts_importacao (nome_layout, col_vencimento, col_numero, col_valor, col_pagador)
        VALUES (?,?,?,?,?)
    """, (nome, mapa['vencimento'], mapa['numero'], mapa['valor'], mapa['pagador']))
    conn.commit()
    conn.close()

def excluir_layout(id_layout):
    try:
        conn = conectar()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM layouts_importacao WHERE id=?", (id_layout,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao excluir: {e}")
        return False

excluir_layout_db = excluir_layout

# ==============================================================================
# 5. AGENDAMENTO E LOGS
# ==============================================================================
def obter_agendamento(cnpj_empresa=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("SELECT * FROM agendamento LIMIT 1").fetchone()
        return dict(res) if res else {}
    finally:
        conn.close()

def salvar_agendamento_db(cnpj_empresa, dias, hora, pular_feriados, ativo):
    conn = conectar()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM agendamento")
        dias_str = json.dumps(dias) if isinstance(dias, list) else str(dias)
        c.execute("""
            INSERT INTO agendamento (dias_ui, horario_envio, pular_feriados, ativo) 
            VALUES (?, ?, ?, ?)
        """, (dias_str, hora, pular_feriados, ativo))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar agendamento: {e}")
    finally:
        conn.close()

def salvar_log_envio(dados_ou_cliente, tipo_envio=None, status=None, detalhes=None, usuario=None):
    conn = conectar()
    c = conn.cursor()
    if isinstance(dados_ou_cliente, dict):
        dados = dados_ou_cliente
        c.execute("""
            INSERT INTO logs_envio (data_envio, cliente, tipo_envio, status, detalhes, usuario)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (dados.get('data'), dados.get('cliente'), dados.get('canal'), dados.get('status'), str(dados), usuario))
    else:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO logs_envio (data_envio, cliente, tipo_envio, status, detalhes, usuario)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agora, dados_ou_cliente, tipo_envio, status, detalhes, usuario))
    conn.commit()
    conn.close()

def registrar_auditoria_titulo(titulo_id, usuario, status_anterior, status_novo, acao):
    conn = conectar()
    c = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO auditoria_titulos (titulo_id, usuario, data_hora, status_anterior, status_novo, acao)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (titulo_id, usuario, agora, status_anterior, status_novo, acao))
    conn.commit()
    conn.close()

def listar_logs_cliente_db(nome_cliente, cnpj_empresa=None):
    conn = conectar()
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("""
            SELECT data_envio as data_hora, tipo_envio as tipo, status, detalhes as detalhe 
            FROM logs_envio WHERE cliente=? ORDER BY id DESC
        """, (nome_cliente,)).fetchall()
        return [dict(r) for r in res]
    finally:
        conn.close()

# ==============================================================================
# 6. USUÁRIOS E LOGIN (REVISADO E SINCRONIZADO)
# ==============================================================================
def verificar_login(user, pwd):
    try:
        conn = conectar()
        # Sincronizado com colunas login/password
        query = "SELECT * FROM usuarios WHERE login=? AND password=?"
        res = conn.cursor().execute(query, (user, pwd)).fetchone()
        conn.close()
        return res is not None
    except Exception as e:
        print(f"Erro ao verificar login: {e}")
        return False

def criar_usuario(login, senha, nome_completo="", perfil="operador", foto_b64=None):
    try:
        conn = conectar()
        cursor = conn.cursor()        
        query = """
            INSERT INTO usuarios (login, password, nome_completo, perfil, foto_b64) 
            VALUES (?, ?, ?, ?, ?)
        """
        cursor.execute(query, (login, senha, nome_completo, perfil, foto_b64))
        conn.commit()
        conn.close()
        return True, "Usuário criado com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Erro: Este login já existe no sistema."
    except Exception as e:
        return False, f"Erro no banco: {str(e)}"

def listar_usuarios():
    try:
        conn = conectar()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT login, nome_completo, perfil, status, foto_b64 FROM usuarios")
        rows = cursor.fetchall()
        usuarios = [dict(row) for row in rows]
        conn.close()
        return usuarios
    except Exception as e:
        print(f"Erro ao listar usuários: {e}")
        return []

def excluir_usuario(login):
    try:
        conn = conectar()
        conn.cursor().execute("DELETE FROM usuarios WHERE login=?", (login,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao excluir usuário: {e}")
        return False

def alterar_senha_usuario(login, nova_senha):
    try:
        conn = conectar()
        # CORREÇÃO: 'password' no lugar de 'senha'
        conn.cursor().execute("UPDATE usuarios SET password=? WHERE login=?", (nova_senha, login))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao alterar senha: {e}")
        return False

def atualizar_usuario_db(login, nome_completo, perfil, senha=None, foto_b64=None):
    try:
        conn = conectar()
        cursor = conn.cursor()
        # CORREÇÃO: Usando 'password' no lugar de 'senha' nos UPDATEs
        if senha and foto_b64:
            cursor.execute("UPDATE usuarios SET nome_completo=?, perfil=?, password=?, foto_b64=? WHERE login=?", (nome_completo, perfil, senha, foto_b64, login))
        elif senha:
            cursor.execute("UPDATE usuarios SET nome_completo=?, perfil=?, password=? WHERE login=?", (nome_completo, perfil, senha, login))
        elif foto_b64:
            cursor.execute("UPDATE usuarios SET nome_completo=?, perfil=?, foto_b64=? WHERE login=?", (nome_completo, perfil, foto_b64, login))
        else:
            cursor.execute("UPDATE usuarios SET nome_completo=?, perfil=? WHERE login=?", (nome_completo, perfil, login))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao atualizar usuário: {e}")
        return False

def redefinir_senha_usuario(login, senha_padrao="123456"):
    return alterar_senha_usuario(login, senha_padrao)

def carregar_todas_unidades_db():
    cfg = carregar_configuracoes_db()
    return [cfg] if cfg else []

def migrar_banco_automatico():
    """Garante que o banco local tenha todas as colunas necessárias."""
    conn = conectar()
    c = conn.cursor()
    
    # Dicionário de Tabela: [Colunas que DEVEM existir]
    migracoes = {
        "usuarios": ["nome_completo", "perfil", "status", "foto_b64"],
        "config": ["empresa_cnpj", "logo_b64", "gemini_api_key", "evo_url", "evo_key"],
        "logs_envio": ["usuario"]
    }
    
    for tabela, colunas in migracoes.items():
        for col in colunas:
            try:
                c.execute(f"ALTER TABLE {tabela} ADD COLUMN {col} TEXT")
                print(f"🛠️ Migração: Coluna '{col}' adicionada em '{tabela}'.")
            except Exception:
                # Se der erro, é porque a coluna já existe. Podemos ignorar.
                pass
    
    conn.commit()
    conn.close()

# Invocamos a inicialização e a migração sempre que o arquivo é lido
inicializar_banco()
migrar_banco_automatico()

# ==============================================================================
# 7. ALIASES / APELIDOS
# ==============================================================================
cadastrar_cliente_completo = lambda nome, cnpj, whatsapp, email, contato, *args: salvar_cliente_db(nome, cnpj, whatsapp, email, contato)
salvar_config_agendamento = salvar_agendamento_db
salvar_titulos_db = salvar_dados_no_banco
obter_clientes = listar_clientes_db
listar_layouts_db = obter_layouts_bancos
salvar_layout_db = salvar_layout_preferido
carregar_agendamento_db = obter_agendamento
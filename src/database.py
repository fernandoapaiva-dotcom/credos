import sqlite3
import json
import os
from datetime import datetime
import base64

def _get_default_logo():
    path = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "logo.png")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
        except: return ""
    return ""

# Configuração de diretório (suporte para Docker)
DATABASE_DIR = os.getenv("DATABASE_DIR", "/app/data")
if not os.path.exists(DATABASE_DIR):
    os.makedirs(DATABASE_DIR, exist_ok=True)

# Nomes dos bancos
CENTRAL_DB_NAME = os.path.join(DATABASE_DIR, "credos_central.db")
DB_PREFIX = "db_"

def conectar(cnpj=None):
    if cnpj:
        # Limpa o CNPJ para usar como nome de arquivo
        safe_cnpj = str(cnpj).replace('.', '').replace('/', '').replace('-', '').strip()
        db_path = os.path.join(DATABASE_DIR, f"{DB_PREFIX}{safe_cnpj}.db")
        conn = sqlite3.connect(db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        # Verifica se as tabelas fundamentais existem
        c = conn.cursor()
        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
            if not c.fetchone():
                _criar_tabelas_empresa(conn)
            else:
                _verificar_migracoes_config(conn)
                _verificar_migracoes_v3(conn) # Novas tabelas Negociação e Cartório
                _verificar_migracoes_v4(conn) # Tabela de Documentos Proativos
        except:
            _criar_tabelas_empresa(conn)
        return conn
        
    conn = sqlite3.connect(CENTRAL_DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def _verificar_migracoes_config(conn):
    """Garante que as colunas de regras financeiras existam na tabela config."""
    c = conn.cursor()
    c.execute("PRAGMA table_info(config)")
    cols = [col[1] for col in c.fetchall()]
    
    if 'multa_fixed' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN multa_fixed REAL DEFAULT 2.0")
    if 'juros_mensal' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN juros_mensal REAL DEFAULT 1.0")
    if 'dias_para_cartorio' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN dias_para_cartorio INTEGER DEFAULT 10")
    if 'cartorio_pfx_b64' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN cartorio_pfx_b64 TEXT")
    if 'cartorio_pfx_pass' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN cartorio_pfx_pass TEXT")
    if 'cartorio_interval_min' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN cartorio_interval_min INTEGER DEFAULT 5")
    if 'chave_pix' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN chave_pix TEXT")
    if 'tipo_chave_pix' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN tipo_chave_pix TEXT")
    
    # Migração Clientes para incluir Endereço
    c.execute("PRAGMA table_info(clientes)")
    cli_cols = [col[1] for col in c.fetchall()]
    if 'endereco' not in cli_cols:
        c.execute("ALTER TABLE clientes ADD COLUMN endereco TEXT")
    
    if 'logo_b64' in cols:
        # Garante que se estiver vazio, a gente coloca a logo nova (Credos)
        c.execute("SELECT logo_b64 FROM config LIMIT 1")
        row = c.fetchone()
        if not row or not row[0]:
            c.execute("UPDATE config SET logo_b64 = ?", (_get_default_logo(),))
    conn.commit()

def _verificar_migracoes_v3(conn):
    """Garante que as novas tabelas de Negociação e Cartório existam."""
    c = conn.cursor()
    # Tabela Negociações (RAG)
    c.execute('''CREATE TABLE IF NOT EXISTS negociacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT,
        titulos_ids TEXT,
        mensagem_gerada TEXT,
        data_envio TEXT,
        status_resposta TEXT,
        criado_em TEXT
    )''')
    # Tabela Cartório Jobs (Automação Full)
    c.execute('''CREATE TABLE IF NOT EXISTS cartorio_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo_id INTEGER,
        status_automacao TEXT DEFAULT 'Pendente',
        log_erro TEXT,
        data_execucao TEXT,
        intervacao_manual INTEGER DEFAULT 0
    )''')
    # Tabela de Sessões de Conversa WhatsApp (novo fluxo conversacional)
    c.execute('''CREATE TABLE IF NOT EXISTS webhook_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_whatsapp TEXT,
        cliente_nome TEXT,
        dia_cobranca INTEGER DEFAULT 1,
        estado TEXT DEFAULT 'aguardando_resposta',
        ultima_mensagem_enviada TEXT,
        ultima_interacao TEXT,
        grupo_operador_id TEXT,
        data_promessa TEXT
    )''')
    # Tabela de Comprovantes Recebidos
    c.execute('''CREATE TABLE IF NOT EXISTS comprovantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER,
        cliente_nome TEXT,
        arquivo_b64 TEXT,
        mimetype TEXT,
        status TEXT DEFAULT 'Pendente',
        recebido_em TEXT,
        analisado_em TEXT,
        operador TEXT
    )''')
    # Migração Tabela Webhook Sessions
    c.execute("PRAGMA table_info(webhook_sessions)")
    ws_cols = [col[1] for col in c.fetchall()]
    if 'history_json' not in ws_cols:
        c.execute("ALTER TABLE webhook_sessions ADD COLUMN history_json TEXT DEFAULT '[]'")
    if 'data_promessa' not in ws_cols:
        c.execute("ALTER TABLE webhook_sessions ADD COLUMN data_promessa TEXT")

    # Migração Tabela Titulos
    c.execute("PRAGMA table_info(titulos)")
    tit_cols = [col[1] for col in c.fetchall()]
    if 'data_promessa' not in tit_cols:
        c.execute("ALTER TABLE titulos ADD COLUMN data_promessa TEXT")
    if 'emissao' not in tit_cols:
        c.execute("ALTER TABLE titulos ADD COLUMN emissao TEXT")
    if 'data_envio_cartorio' not in tit_cols:
        c.execute("ALTER TABLE titulos ADD COLUMN data_envio_cartorio TEXT")
    if 'status_retorno_cartorio' not in tit_cols:
        c.execute("ALTER TABLE titulos ADD COLUMN status_retorno_cartorio TEXT DEFAULT 'N/A'")

    # Coluna para número do operador (WhatsApp do grupo interno)
    c.execute("PRAGMA table_info(config)")
    cols = [col[1] for col in c.fetchall()]
    if 'operador_whatsapp' not in cols:
        c.execute("ALTER TABLE config ADD COLUMN operador_whatsapp TEXT")

    # Coluna para controle de resiliência de agendamento (Analu Anti-Falhas)
    c.execute("PRAGMA table_info(agendamento)")
    ag_cols = [col[1] for col in c.fetchall()]
    if 'ultima_execucao' not in ag_cols:
        c.execute("ALTER TABLE agendamento ADD COLUMN ultima_execucao TEXT")
    
    conn.commit()

def _verificar_migracoes_v4(conn):
    """Garante a existência da tabela de documentos fiscais indexados."""
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS documentos_fiscais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj_cliente TEXT,
        num_nf TEXT,
        tipo TEXT, 
        emissao TEXT,
        vencimento TEXT,
        valor REAL,
        fpath_local TEXT,
        email_uid TEXT,
        chave_acesso TEXT,
        created_at TEXT
    )''')
    conn.commit()


def _criar_tabelas_empresa(conn):
    """Cria a estrutura de tabelas em um banco de empresa específico."""
    c = conn.cursor()
    # 1. Configurações
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_nome TEXT, empresa_cnpj TEXT,
        gemini_api_key TEXT, evo_url TEXT, evo_key TEXT,
        base_mail_user TEXT, base_mail_pass TEXT, imap_server TEXT,
        fin_mail_user TEXT, fin_mail_pass TEXT, smtp_server TEXT,
        logo_b64 TEXT,
        multa_fixed REAL DEFAULT 2.0,
        juros_mensal REAL DEFAULT 1.0,
        dias_para_cartorio INTEGER DEFAULT 10,
        cartorio_pfx_b64 TEXT,
        cartorio_pfx_pass TEXT,
        cartorio_interval_min INTEGER DEFAULT 5,
        chave_pix TEXT,
        tipo_chave_pix TEXT
    )''')
    # 2. Clientes
    c.execute('''CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT, cnpj TEXT, whatsapp TEXT, email TEXT, contato TEXT, endereco TEXT
    )''')
    # 3. Títulos
    c.execute('''CREATE TABLE IF NOT EXISTS titulos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pagador TEXT, numero_nf TEXT, vencimento TEXT, emissao TEXT, valor REAL,
        status TEXT DEFAULT 'Aberto', acao TEXT DEFAULT 'Cobrar', data_promessa TEXT
    )''')
    # 4. Agendamento
    c.execute('''CREATE TABLE IF NOT EXISTS agendamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dias_ui TEXT, horario_envio TEXT, pular_feriados INTEGER, ativo INTEGER
    )''')
    # 5. Layouts de Importação
    c.execute('''CREATE TABLE IF NOT EXISTS layouts_importacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_layout TEXT,
        col_vencimento TEXT, col_numero TEXT, col_valor TEXT, col_pagador TEXT
    )''')
    # 6. Logs de Envio
    c.execute('''CREATE TABLE IF NOT EXISTS logs_envio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_envio TEXT, cliente TEXT, tipo_envio TEXT, status TEXT, detalhes TEXT, usuario TEXT
    )''')
    # 7. Auditoria de Títulos
    c.execute('''CREATE TABLE IF NOT EXISTS auditoria_titulos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo_id INTEGER, usuario TEXT, data_hora TEXT,
        status_anterior TEXT, status_novo TEXT, acao TEXT,
        FOREIGN KEY(titulo_id) REFERENCES titulos(id)
    )''')
    # 8. Negociações (RAG)
    c.execute('''CREATE TABLE IF NOT EXISTS negociacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente TEXT, titulos_ids TEXT, mensagem_gerada TEXT, 
        data_envio TEXT, status_resposta TEXT, criado_em TEXT
    )''')
    # 9. Cartório Jobs
    c.execute('''CREATE TABLE IF NOT EXISTS cartorio_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo_id INTEGER, status_automacao TEXT DEFAULT 'Pendente',
        log_erro TEXT, data_execucao TEXT, intervacao_manual INTEGER DEFAULT 0
    )''')
    # 10. Documentos Fiscais Indexados (Proativo)
    c.execute('''CREATE TABLE IF NOT EXISTS documentos_fiscais (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj_cliente TEXT, num_nf TEXT, tipo TEXT, 
        emissao TEXT, vencimento TEXT, valor REAL, 
        fpath_local TEXT, email_uid TEXT, chave_acesso TEXT, created_at TEXT
    )''')
    conn.commit()

def inicializar_banco():
    """Inicializa o banco central e as tabelas globais."""
    conn = conectar() # Sem CNPJ = Central
    c = conn.cursor()
    # Tabela de Usuários (Centralizada para login global)
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE, password TEXT, nome_completo TEXT, 
        perfil TEXT DEFAULT 'operador', status TEXT DEFAULT 'Ativo', foto_b64 TEXT
    )''')
    # Tabela de Unidades/Empresas
    c.execute('''CREATE TABLE IF NOT EXISTS unidades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_nome TEXT, empresa_cnpj TEXT UNIQUE, data_cadastro TEXT
    )''')
    
    # Tabela de Contatos Globais (A Fonte Única de Verdade)
    c.execute('''CREATE TABLE IF NOT EXISTS contatos_globais (
        cnpj TEXT PRIMARY KEY,
        whatsapp TEXT,
        email TEXT,
        contato TEXT,
        endereco TEXT,
        last_update TEXT
    )''')
    
    # Tabela de Configuração Global Mestre
    c.execute('''CREATE TABLE IF NOT EXISTS config_global (
        id INTEGER PRIMARY KEY DEFAULT 1,
        grupo_relatorio_jid TEXT,
        webhook_url TEXT
    )''')
    
    # Init row if not exists
    c.execute("INSERT OR IGNORE INTO config_global (id, grupo_relatorio_jid) VALUES (1, NULL)")
    
    # Usuário Admin Padrão
    if c.execute("SELECT count(*) FROM usuarios").fetchone()[0] == 0:
        c.execute("INSERT INTO usuarios (login, password, nome_completo, perfil) VALUES (?,?,?,?)",
                  ('admin@credos.com', 'admin123', 'Administrador Central', 'admin'))
    
    conn.commit()
    conn.close()

# ==============================================================================
# 0. GESTÃO DE UNIDADES (CENTRAL)
# ==============================================================================
def cadastrar_unidade_central(nome, cnpj):
    conn = conectar()
    c = conn.cursor()
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    try:
        c.execute("INSERT INTO unidades (empresa_nome, empresa_cnpj, data_cadastro) VALUES (?,?,?)",
                  (nome, cnpj, agora))
        conn.commit()
        # Inicializa o banco da empresa
        conectar(cnpj).close()
        return True, "Unidade cadastrada com sucesso!"
    except sqlite3.IntegrityError:
        return False, "Erro: Este CNPJ já está cadastrado."
    finally:
        conn.close()

def atualizar_unidade_central(old_cnpj, novo_nome, novo_cnpj):
    """Atualiza nome e/ou CNPJ de uma unidade, renomeando o arquivo físico se necessário."""
    conn = conectar()
    c = conn.cursor()
    try:
        # 1. Atualiza o banco central
        c.execute("UPDATE unidades SET empresa_nome = ?, empresa_cnpj = ? WHERE empresa_cnpj = ?",
                  (novo_nome, novo_cnpj, old_cnpj))
        
        # 2. Se o CNPJ mudou, renomeia o arquivo do banco
        if old_cnpj != novo_cnpj:
            safe_old = str(old_cnpj).replace('.', '').replace('/', '').replace('-', '').strip()
            safe_new = str(novo_cnpj).replace('.', '').replace('/', '').replace('-', '').strip()
            
            old_path = f"{DB_PREFIX}{safe_old}.db"
            new_path = f"{DB_PREFIX}{safe_new}.db"
            
            if os.path.exists(old_path):
                # Se o destino já existe (colisão), não deletamos o antigo por segurança, mas o código central já foi atualizado
                if not os.path.exists(new_path):
                    os.rename(old_path, new_path)
                
            # 3. Atualiza o CNPJ dentro da tabela config do novo banco
            try:
                conn_emp = conectar(novo_cnpj)
                c_emp = conn_emp.cursor()
                c_emp.execute("UPDATE config SET empresa_cnpj = ? WHERE id = 1", (novo_cnpj,))
                conn_emp.commit()
                conn_emp.close()
            except Exception as e:
                print(f"Aviso: Não foi possível atualizar CNPJ interno na config: {e}")

        conn.commit()
        return True, "Unidade atualizada com sucesso!"
    except Exception as e:
        return False, f"Erro ao atualizar unidade: {str(e)}"
    finally:
        conn.close()

def excluir_unidade_central(cnpj):
    conn = conectar()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM unidades WHERE empresa_cnpj = ?", (cnpj,))
        conn.commit()
        # Tenta deletar o arquivo físico do banco
        safe_cnpj = str(cnpj).replace('.', '').replace('/', '').replace('-', '').strip()
        db_path = f"{DB_PREFIX}{safe_cnpj}.db"
        if os.path.exists(db_path):
            try: os.remove(db_path)
            except: pass
        return True, "Unidade excluída com sucesso!"
    except Exception as e:
        return False, f"Erro ao excluir unidade: {str(e)}"
    finally:
        conn.close()

def carregar_todas_unidades_db():
    conn = conectar()
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("SELECT * FROM unidades").fetchall()
        return [dict(r) for r in res]
    finally:
        conn.close()

# ==============================================================================
# 1. CONFIGURAÇÕES
# ==============================================================================
def carregar_configuracoes_db(cnpj_empresa):
    if not cnpj_empresa: return {}
    conn = conectar(cnpj_empresa)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        row = c.execute("SELECT * FROM config LIMIT 1").fetchone()
        if row:
            config_dict = dict(row)
            return config_dict
        return {}
    except Exception as e:
        print(f"❌ Erro ao carregar config ({cnpj_empresa}): {e}")
        return {}
    finally:
        conn.close()

def salvar_configuracoes_db(cnpj_empresa, novos_dados: dict):
    if not cnpj_empresa or not novos_dados: return
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    try:
        c.execute("PRAGMA table_info(config)")
        colunas_banco = [info[1] for info in c.fetchall()]
        dados_validos = {k: v for k, v in novos_dados.items() if k in colunas_banco}
        
        if not dados_validos: return

        c.execute("SELECT count(*) FROM config")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO config (empresa_cnpj, logo_b64) VALUES (?, ?)", (cnpj_empresa, _get_default_logo()))

        set_clause = ", ".join([f"{key} = ?" for key in dados_validos.keys()])
        valores = list(dados_validos.values())
        query = f"UPDATE config SET {set_clause} WHERE id = 1"
        
        c.execute(query, valores)
        conn.commit()
    except Exception as e:
        print(f"❌ Erro ao salvar config ({cnpj_empresa}): {e}")
    finally:
        conn.close()

# ==============================================================================
# 2. CLIENTES
# ==============================================================================
def listar_clientes_db(cnpj_empresa, nome_filtro=None):
    if not cnpj_empresa: return []
    conn = conectar(cnpj_empresa)
    conn.row_factory = sqlite3.Row
    if nome_filtro:
        res = conn.cursor().execute("SELECT * FROM clientes WHERE trim(nome)=?", (nome_filtro.strip(),)).fetchall()
    else:
        res = conn.cursor().execute("SELECT * FROM clientes").fetchall()
    conn.close()
    
    clientes = [dict(r) for r in res]
    
    # --- ENRIQUECIMENTO GLOBAL ---
    # Busca dados unificados no banco central para bater com o CNPJ
    try:
        conn_cent = conectar()
        conn_cent.row_factory = sqlite3.Row
        c_cent = conn_cent.cursor()
        
        for cli in clientes:
            cnpj_norm = _normalizar_cnpj(cli.get('cnpj'))
            if cnpj_norm:
                global_data = c_cent.execute(
                    "SELECT whatsapp, email, contato, endereco FROM contatos_globais WHERE cnpj = ?", 
                    (cnpj_norm,)
                ).fetchone()
                
                if global_data:
                    # Sobrescreve com o dado global (Fonte Única de Verdade)
                    if global_data['whatsapp']: cli['whatsapp'] = global_data['whatsapp']
                    if global_data['email']: cli['email'] = global_data['email']
                    if global_data['contato']: cli['contato'] = global_data['contato']
                    if global_data['endereco']: cli['endereco'] = global_data['endereco']
        conn_cent.close()
    except Exception as e:
        print(f"Erro ao enriquecer clientes com dados globais: {e}")
        
    return clientes

def verificar_cliente_existe(cnpj_empresa, nome_cliente):
    if not cnpj_empresa: return False
    conn = conectar(cnpj_empresa)
    res = conn.cursor().execute("SELECT id FROM clientes WHERE trim(nome)=?", (nome_cliente.strip(),)).fetchone()
    conn.close()
    return res is not None

def _normalizar_cnpj(cnpj):
    if not cnpj: return ""
    return "".join(filter(str.isdigit, str(cnpj)))

def upsert_contato_global(cnpj, whatsapp, email, contato=None, endereco=None):
    """Atualiza ou insere dados na tabela central de contatos globais."""
    cnpj_clean = _normalizar_cnpj(cnpj)
    if not cnpj_clean: return
    
    conn = conectar() # Central
    c = conn.cursor()
    try:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Upsert: se já existe o CNPJ, atualiza apenas o que não for vazio
        c.execute("SELECT cnpj FROM contatos_globais WHERE cnpj = ?", (cnpj_clean,))
        if c.fetchone():
            c.execute("""
                UPDATE contatos_globais 
                SET whatsapp=?, email=?, contato=?, endereco=?, last_update=?
                WHERE cnpj=?
            """, (whatsapp, email, contato, endereco, agora, cnpj_clean))
        else:
            c.execute("""
                INSERT INTO contatos_globais (cnpj, whatsapp, email, contato, endereco, last_update)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cnpj_clean, whatsapp, email, contato, endereco, agora))
        conn.commit()
    except Exception as e:
        print(f"Erro ao salvar contato global: {e}")
    finally:
        conn.close()

def salvar_cliente_db(cnpj_empresa, nome, cnpj, whatsapp, email, contato=None):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    nome = nome.strip() if nome else ""
    if not verificar_cliente_existe(cnpj_empresa, nome):
        c.execute("INSERT INTO clientes (nome, cnpj, whatsapp, email, contato) VALUES (?,?,?,?,?)",
                  (nome, cnpj, whatsapp, email, contato if contato else ""))
    else:
        c.execute("UPDATE clientes SET cnpj=?, whatsapp=?, email=?, contato=? WHERE nome=?",
                  (cnpj, whatsapp, email, contato if contato else "", nome))
    conn.commit()
    conn.close()
    
    # SINCRONIZAÇÃO GLOBAL: Se tem CNPJ, salva na tabela mestre central
    if cnpj and _normalizar_cnpj(cnpj):
        upsert_contato_global(cnpj, whatsapp, email, contato)

def excluir_cliente_db(cnpj_empresa, id_cliente, nome_cliente, usuario=None):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    c.execute("DELETE FROM clientes WHERE id=?", (id_cliente,))
    c.execute("DELETE FROM titulos WHERE pagador=?", (nome_cliente,))
    conn.commit()
    conn.close()
    if usuario:
        salvar_log_envio(cnpj_empresa, nome_cliente, "Exclusão CRM", "Sucesso", f"Cliente e títulos excluídos", usuario=usuario)

# ==============================================================================
# 3. TÍTULOS FINANCEIROS
# ==============================================================================
def salvar_dados_no_banco(cnpj_empresa, titulos):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    for t in titulos:
        pagador = t['pagador'].strip() if t.get('pagador') else ""
        num_nf = str(t['numero']).strip() if t.get('numero') else ""
        
        exists = c.execute(
            "SELECT id FROM titulos WHERE numero_nf=? AND trim(pagador)=? AND vencimento=?", 
            (num_nf, pagador, t['vencimento'])
        ).fetchone()
        
        if not exists:
            c.execute("INSERT INTO titulos (pagador, numero_nf, vencimento, valor) VALUES (?,?,?,?)", 
                      (pagador, num_nf, t['vencimento'], t['valor']))
    conn.commit()
    conn.close()

def listar_titulos_por_cliente(cnpj_empresa, nome_cliente):
    if not cnpj_empresa: return []
    conn = conectar(cnpj_empresa)
    conn.row_factory = sqlite3.Row
    # Usamos trim para evitar problemas com caracteres invisíveis vindos de PDFs
    res = conn.cursor().execute("SELECT * FROM titulos WHERE trim(pagador)=?", (nome_cliente.strip(),)).fetchall()
    conn.close()
    return [dict(r) for r in res]

def atualizar_titulo_acao(cnpj_empresa, id_titulo, nova_acao, novo_status=None):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Busca estado anterior para auditoria e nome do pagador para log
    old = c.execute("SELECT status, acao, pagador FROM titulos WHERE id = ?", (id_titulo,)).fetchone()
    if not old:
        conn.close()
        return
        
    status_anterior = old['status']
    acao_anterior = old['acao']
    pagador = old['pagador']
    
    if novo_status:
        c.execute("UPDATE titulos SET acao = ?, status = ? WHERE id = ?", (nova_acao, novo_status, id_titulo))
    else:
        c.execute("UPDATE titulos SET acao = ? WHERE id = ?", (nova_acao, id_titulo))
        novo_status = status_anterior
        
    conn.commit()
    conn.close()
    
    # Registra auditoria
    registrar_auditoria_titulo(cnpj_empresa, id_titulo, "Sistema/UI", status_anterior, novo_status, nova_acao)
    
    # Log de envio (legado para histórico rápido)
    if pagador:
        salvar_log_envio(cnpj_empresa, pagador, "CRM Status Update", "Sucesso", f"Status alterado para {novo_status} ({nova_acao})", "Sistema/CRM")

def atualizar_titulo_status_acao(cnpj_empresa, id_titulo, novo_status, nova_acao):
    return atualizar_titulo_acao(cnpj_empresa, id_titulo, nova_acao, novo_status)

# ==============================================================================
# 4. LAYOUTS
# ==============================================================================
def obter_layouts_bancos(cnpj_empresa):
    if not cnpj_empresa: return []
    conn = conectar(cnpj_empresa)
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("SELECT * FROM layouts_importacao").fetchall()
        return [dict(r) for r in res]
    finally:
        conn.close()

def salvar_layout_preferido(cnpj_empresa, nome, mapa):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
    conn.cursor().execute("""
        INSERT INTO layouts_importacao (nome_layout, col_vencimento, col_numero, col_valor, col_pagador)
        VALUES (?,?,?,?,?)
    """, (nome, mapa['vencimento'], mapa['numero'], mapa['valor'], mapa['pagador']))
    conn.commit()
    conn.close()

def excluir_layout(cnpj_empresa, id_layout):
    if not cnpj_empresa: return False
    try:
        conn = conectar(cnpj_empresa)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM layouts_importacao WHERE id=?", (id_layout,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao excluir layout ({cnpj_empresa}): {e}")
        return False

# ==============================================================================
# 5. AGENDAMENTO E LOGS
# ==============================================================================
def obter_agendamento(cnpj_empresa):
    if not cnpj_empresa: return {}
    conn = conectar(cnpj_empresa)
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("SELECT * FROM agendamento LIMIT 1").fetchone()
        return dict(res) if res else {}
    finally:
        conn.close()

def listar_todos_agendamentos_ativos():
    unidades = carregar_todas_unidades_db()
    agendamentos_ativos = []
    
    for u in unidades:
        cnpj = u['empresa_cnpj']
        conn = conectar(cnpj)
        conn.row_factory = sqlite3.Row
        try:
            res = conn.cursor().execute("SELECT * FROM agendamento WHERE ativo=1 LIMIT 1").fetchone()
            if res:
                ag = dict(res)
                ag['empresa_dona_cnpj'] = cnpj
                agendamentos_ativos.append(ag)
        except Exception:
            pass
        finally:
            conn.close()
            
    return agendamentos_ativos

def salvar_agendamento_db(cnpj_empresa, dias, hora, pular_feriados, ativo):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
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
        print(f"Erro ao salvar agendamento ({cnpj_empresa}): {e}")
    finally:
        conn.close()

def salvar_log_envio(cnpj_empresa, dados_ou_cliente, tipo_envio=None, status=None, detalhes=None, usuario=None):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
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

def registrar_auditoria_titulo(cnpj_empresa, titulo_id, usuario, status_anterior, status_novo, acao):
    if not cnpj_empresa: return
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO auditoria_titulos (titulo_id, usuario, data_hora, status_anterior, status_novo, acao)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (titulo_id, usuario, agora, status_anterior, status_novo, acao))
    conn.commit()
    conn.close()

def listar_logs_cliente_db(cnpj_empresa, nome_cliente):
    if not cnpj_empresa: return []
    conn = conectar(cnpj_empresa)
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
# 6. USUÁRIOS E LOGIN (CENTRAL)
# ==============================================================================
def verificar_login(user, pwd):
    import bcrypt
    try:
        conn = conectar()
        query = "SELECT password FROM usuarios WHERE login=?"
        res = conn.cursor().execute(query, (user,)).fetchone()
        conn.close()
        if res:
            hashed = res[0]
            try:
                return bcrypt.checkpw(pwd.encode('utf-8'), hashed.encode('utf-8'))
            except:
                return pwd == hashed # Fallback para texto plano se hash der erro
        return False
    except Exception as e:
        print(f"Erro ao verificar login: {e}")
        return False

def criar_usuario(login, senha, nome_completo="", perfil="operador", foto_b64=None):
    try:
        conn = conectar()
        cursor = conn.cursor()        
        query = "INSERT INTO usuarios (login, password, nome_completo, perfil, foto_b64) VALUES (?, ?, ?, ?, ?)"
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
        print(f"Erro ao extrair logs: {e}")
        return []

def obter_stats_dashboard(cnpj):
    conn = conectar(cnpj)
    c = conn.cursor()
    
    # 1. Títulos em Aberto (Soma de valor)
    c.execute("SELECT SUM(valor) FROM titulos WHERE status = 'Aberto'")
    total_aberto = c.fetchone()[0] or 0.0
    
    # 2. Acordos Recebidos (Soma de valor dos que estão 'Pago' ou 'Baixado')
    c.execute("SELECT SUM(valor) FROM titulos WHERE status IN ('Pago', 'Baixado', 'Recebido')")
    total_recebido = c.fetchone()[0] or 0.0
    
    # 3. Clientes Ativos
    c.execute("SELECT COUNT(*) FROM clientes")
    total_clientes = c.fetchone()[0] or 0
    
    # 4. Em Cartório
    c.execute("SELECT COUNT(*) FROM titulos WHERE status = 'Cartório'")
    total_cartorio = c.fetchone()[0] or 0
    
    # 5. Total de Mensagens Enviadas (Logs)
    c.execute("SELECT COUNT(*) FROM logs_envio")
    total_logs = c.fetchone()[0] or 0

    # 6. Total de Negociações IA
    c.execute("SELECT COUNT(*) FROM negociacoes")
    total_negociacoes = c.fetchone()[0] or 0
    
    # 7. Total de Jobs de Cartório (Fila)
    c.execute("SELECT COUNT(*) FROM cartorio_jobs")
    total_cartorio_jobs = c.fetchone()[0] or 0

    # 8. Dados para o Gráfico (Resumo de Atividades)
    # Extraímos MM/YYYY do vencimento e processamos em Python para evitar erros de substr no SQL
    try:
        c.execute("SELECT vencimento, status, valor FROM titulos")
        rows = c.fetchall()
        
        agrupados = {} # { "2026-03": {"name": "03/2026", "recebido": 0, "pendente": 0} }
        
        for venc, status, valor in rows:
            if not venc or '/' not in str(venc): continue
            
            partes = str(venc).split('/')
            if len(partes) == 3:
                # Normaliza para YYYY-MM para ordenação e MM/YYYY para exibição
                d, m, y = partes[0].zfill(2), partes[1].zfill(2), partes[2]
                key = f"{y}-{m}"
                display = f"{m}/{y}"
                
                if key not in agrupados:
                    agrupados[key] = {"name": display, "recebido": 0, "pendente": 0}
                
                if status in ('Pago', 'Baixado', 'Recebido'):
                    agrupados[key]["recebido"] += valor
                elif status not in ('Cancelado', 'Excluído'):
                    # Tudo que não for pago ou cancelado é pendente (Aberto, Negociado, Cartório, etc)
                    agrupados[key]["pendente"] += valor
        
        # Ordenar chaves e pegar os últimos 12 meses
        sorted_keys = sorted(agrupados.keys())
        # Pegar os 12 mais recentes se houver muitos
        if len(sorted_keys) > 12:
            sorted_keys = sorted_keys[-12:]
            
        chart_data = [agrupados[k] for k in sorted_keys]
    except Exception as e:
        print(f"Erro ao gerar chart_data: {e}")
        chart_data = []
        
    # Data placeholder if empty
    if not chart_data:
        chart_data = [
            {"name": "Sem Dados", "recebido": 0, "pendente": 0}
        ]

    conn.close()
    return {
        "stats": {
            "total_aberto": total_aberto,
            "total_recebido": total_recebido,
            "total_clientes": total_clientes,
            "total_cartorio": total_cartorio,
            "total_logs": total_logs,
            "total_negociacoes": total_negociacoes,
            "total_cartorio_jobs": total_cartorio_jobs
        },
        "chart_data": chart_data
    }

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
        conn.cursor().execute("UPDATE usuarios SET password=? WHERE login=?", (nova_senha, login))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao alterar senha: {e}")
        return False

def atualizar_usuario_db(login, nome_completo=None, perfil=None, senha=None, foto_b64=None, novo_login=None):
    try:
        conn = conectar()
        cursor = conn.cursor()
        
        # 1. Se for mudar o login (Primary Key), fazemos primeiro
        if novo_login and novo_login != login:
             cursor.execute("UPDATE usuarios SET login=? WHERE login=?", (novo_login, login))
             login = novo_login
             
        # 2. Construir query dinâmica para os outros campos
        fields = []
        values = []
        
        if nome_completo is not None:
            fields.append("nome_completo=?")
            values.append(nome_completo)
        
        if perfil is not None:
            fields.append("perfil=?")
            values.append(perfil)
            
        if senha is not None:
            fields.append("password=?")
            values.append(senha)
            
        if foto_b64 is not None:
            fields.append("foto_b64=?")
            values.append(foto_b64)
            
        if not fields:
            conn.close()
            return True # Nada para atualizar
            
        query = f"UPDATE usuarios SET {', '.join(fields)} WHERE login=?"
        values.append(login)
        
        cursor.execute(query, tuple(values))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao atualizar usuário: {e}")
        return False

def redefinir_senha_usuario(login, senha_padrao="123456"):
    return alterar_senha_usuario(login, senha_padrao)

# ==============================================================================
# ALIASES E INICIALIZAÇÃO
# ==============================================================================
inicializar_banco()

cadastrar_cliente_completo = lambda cnpj_empresa, nome, cnpj, whatsapp, email, contato, *args: salvar_cliente_db(cnpj_empresa, nome, cnpj, whatsapp, email, contato)
salvar_config_agendamento = salvar_agendamento_db
salvar_titulos_db = salvar_dados_no_banco
obter_clientes = listar_clientes_db
listar_layouts_db = obter_layouts_bancos
salvar_layout_db = salvar_layout_preferido
carregar_agendamento_db = obter_agendamento
excluir_layout_db = excluir_layout
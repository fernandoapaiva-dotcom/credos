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
DATABASE_DIR = os.getenv("DATABASE_DIR", ".")
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
        conn = sqlite3.connect(db_path)
        # Verifica se as tabelas fundamentais existem
        c = conn.cursor()
        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
            if not c.fetchone():
                _criar_tabelas_empresa(conn)
            else:
                _verificar_migracoes_config(conn)
        except:
            _criar_tabelas_empresa(conn)
        return conn
    return sqlite3.connect(CENTRAL_DB_NAME)

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
    if 'logo_b64' in cols:
        # Garante que se estiver vazio, a gente coloca a logo nova (Credos)
        c.execute("SELECT logo_b64 FROM config LIMIT 1")
        row = c.fetchone()
        if not row or not row[0]:
            c.execute("UPDATE config SET logo_b64 = ?", (_get_default_logo(),))
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
        dias_para_cartorio INTEGER DEFAULT 10
    )''')
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
    return [dict(r) for r in res]

def verificar_cliente_existe(cnpj_empresa, nome_cliente):
    if not cnpj_empresa: return False
    conn = conectar(cnpj_empresa)
    res = conn.cursor().execute("SELECT id FROM clientes WHERE trim(nome)=?", (nome_cliente.strip(),)).fetchone()
    conn.close()
    return res is not None

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

    # 6. Dados para o Gráfico (Resumo de Atividades)
    # Extraímos MM/YYYY do vencimento (assumindo DD/MM/YYYY)
    try:
        c.execute("""
            SELECT 
                substr(vencimento, 4, 7) as mes_ano,
                SUM(CASE WHEN status IN ('Pago', 'Baixado', 'Recebido') THEN valor ELSE 0 END) as valor_pago,
                SUM(CASE WHEN status = 'Aberto' THEN valor ELSE 0 END) as valor_aberto
            FROM titulos
            WHERE vencimento LIKE '__/__/____'
            GROUP BY mes_ano
            ORDER BY substr(vencimento, 7, 4) ASC, substr(vencimento, 4, 2) ASC
            LIMIT 12
        """)
        rows = c.fetchall()
        chart_data = []
        for row in rows:
            chart_data.append({
                "name": row[0],
                "recebido": row[1],
                "pendente": row[2]
            })
    except:
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
            "total_logs": total_logs
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

def atualizar_usuario_db(login, nome_completo, perfil, senha=None, foto_b64=None, novo_login=None):
    try:
        conn = conectar()
        cursor = conn.cursor()
        target_login = novo_login if novo_login else login
        
        # Se for mudar o login, precisamos atualizar o campo login
        if novo_login and novo_login != login:
             cursor.execute("UPDATE usuarios SET login=? WHERE login=?", (novo_login, login))
             login = novo_login
             
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
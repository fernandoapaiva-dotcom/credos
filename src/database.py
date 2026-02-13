import sqlite3
import json
import os

# Nome do banco de dados
DB_NAME = "credos_data.db"

def conectar():
    return sqlite3.connect(DB_NAME)

def inicializar_banco():
    """Cria as tabelas iniciais se não existirem."""
    conn = conectar()
    c = conn.cursor()
    
    # 1. Configurações
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_nome TEXT, empresa_cnpj TEXT,
        gemini_api_key TEXT, evo_url TEXT, evo_key TEXT,
        base_mail_user TEXT, base_mail_pass TEXT, base_imap_server TEXT,
        fin_mail_user TEXT, fin_mail_pass TEXT, fin_smtp_server TEXT, fin_imap_server TEXT
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
    
    # 4. Usuários
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE, password TEXT
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

    # 7. Logs
    c.execute('''CREATE TABLE IF NOT EXISTS logs_envio (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data_envio TEXT, cliente TEXT, tipo_envio TEXT, status TEXT, detalhes TEXT
    )''')
    
    conn.commit()
    conn.close()

# ==============================================================================
# 1. CONFIGURAÇÕES
# ==============================================================================
def carregar_configuracoes_db(cnpj_empresa=None):
    """
    Busca as configurações no banco. 
    Prioriza o CNPJ da empresa logada para garantir o isolamento dos dados (SaaS).
    """
    conn = conectar()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    try:
        if cnpj_empresa:
            # Busca a configuração específica da unidade selecionada
            query = "SELECT * FROM config WHERE empresa_cnpj = ? LIMIT 1"
            row = c.execute(query, (cnpj_empresa,)).fetchone()
        else:
            # Fallback: Busca a primeira configuração disponível (útil no primeiro acesso)
            row = c.execute("SELECT * FROM config LIMIT 1").fetchone()
        
        if row:
            config_dict = dict(row)
            # Log de depuração para o terminal (ajuda a ver se o e-mail veio do banco)
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
    
    # ⚠️ AJUSTE: No reset_banco.py você usou 'config'. O nome deve ser IGUAL aqui.
    TABELA = "config" 
    
    try:
        # 1. Pega as colunas reais do banco
        c.execute(f"PRAGMA table_info({TABELA})")
        colunas_banco = [info[1] for info in c.fetchall()]
        
        if not colunas_banco:
            print(f"❌ Erro crítico: A tabela '{TABELA}' não existe no banco de dados!")
            return

        # Filtra os dados (ex: 'logo_b64', 'empresa_nome', 'empresa_cnpj')
        dados_validos = {k: v for k, v in novos_dados.items() if k in colunas_banco}
        
        if not dados_validos: 
            print(f"⚠️ Nenhum dado enviado bate com as colunas de {TABELA}: {colunas_banco}")
            return

        # 2. Garante que o registro 1 existe
        c.execute(f"SELECT count(*) FROM {TABELA}")
        if c.fetchone()[0] == 0:
            c.execute(f"INSERT INTO {TABELA} (id) VALUES (1)")

        # 3. Monta e executa a Query
        set_clause = ", ".join([f"{key} = ?" for key in dados_validos.keys()])
        valores = list(dados_validos.values())
        
        query = f"UPDATE {TABELA} SET {set_clause} WHERE id = 1"
        
        c.execute(query, valores)
        conn.commit()
        print(f"✅ Sucesso! {len(dados_validos)} campos salvos em '{TABELA}'.")
        
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
    # O manager passa o CNPJ da empresa primeiro as vezes, vamos ignorar se for o caso
    # Mas aqui a assinatura original é salvar_cliente_db(nome, cnpj...)
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

def excluir_cliente_db(id_cliente, nome_cliente):
    conn = conectar()
    conn.cursor().execute("DELETE FROM clientes WHERE id=?", (id_cliente,))
    conn.cursor().execute("DELETE FROM titulos WHERE pagador=?", (nome_cliente,))
    conn.commit()
    conn.close()

# ==============================================================================
# 3. TÍTULOS FINANCEIROS
# ==============================================================================
def salvar_dados_no_banco(titulos, cnpj_empresa=None):
    conn = conectar()
    c = conn.cursor()
    for t in titulos:
        exists = c.execute("SELECT id FROM titulos WHERE numero_nf=? AND pagador=?", (t['numero'], t['pagador'])).fetchone()
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

# Função específica que o Manager pede (com ordem de parametros invertida as vezes)
def atualizar_titulo_status_acao(id_titulo, novo_status, nova_acao):
    return atualizar_titulo_acao(id_titulo, nova_acao, novo_status)

# ==============================================================================
# 4. LAYOUTS
# ==============================================================================
def obter_layouts_bancos(cnpj_empresa=None): # <-- Adicionado parâmetro opcional
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

# 1. Primeiro você define a função
def excluir_layout(id_layout):
    try:
        conn = conectar()
        cursor = conn.cursor()
        # Verifique se o nome da tabela é layouts_importacao ou layouts_bancos
        cursor.execute("DELETE FROM layouts_importacao WHERE id=?", (id_layout,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Erro ao excluir: {e}")
        return False

# 2. Depois você faz a atribuição (se realmente precisar dela)
excluir_layout_db = excluir_layout



# ==============================================================================
# 5. AGENDAMENTO E LOGS
# ==============================================================================
def obter_agendamento(cnpj_empresa=None): # <-- Adicionado parâmetro opcional
    conn = conectar()
    conn.row_factory = sqlite3.Row
    try:
        res = conn.cursor().execute("SELECT * FROM agendamento LIMIT 1").fetchone()
        return dict(res) if res else {}
    finally:
        conn.close()

def salvar_agendamento_db(cnpj_empresa, dias, hora, pular_feriados, ativo):
    """
    Recebe 5 argumentos para manter compatibilidade com o Manager.
    O cnpj_empresa é recebido mas ignorado por enquanto.
    """
    conn = conectar()
    c = conn.cursor()
    try:
        # Limpa o agendamento anterior
        c.execute("DELETE FROM agendamento")
        
        # Converte lista de dias para string (JSON) para salvar no banco
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

def salvar_log_envio(dados_ou_cliente, tipo_envio=None, status=None, detalhes=None):
    # O Manager chama isso de duas formas, vamos unificar
    conn = conectar()
    c = conn.cursor()
    
    if isinstance(dados_ou_cliente, dict):
        # Chamada antiga passando dicionario
        dados = dados_ou_cliente
        c.execute("""
            INSERT INTO logs_envio (data_envio, cliente, tipo_envio, status, detalhes)
            VALUES (?, ?, ?, ?, ?)
        """, (dados.get('data'), dados.get('cliente'), dados.get('canal'), dados.get('status'), str(dados)))
    else:
        # Chamada nova passando argumentos
        from datetime import datetime
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO logs_envio (data_envio, cliente, tipo_envio, status, detalhes)
            VALUES (?, ?, ?, ?, ?)
        """, (agora, dados_ou_cliente, tipo_envio, status, detalhes))
        
    conn.commit()
    conn.close()

def listar_logs_cliente_db(nome_cliente, cnpj_empresa=None): # <-- Adicionado parâmetro opcional
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
    return [dict(r) for r in res]

# ==============================================================================
# 6. USUÁRIOS E LOGIN
# ==============================================================================
def verificar_login(user, pwd):
    try:
        conn = conectar() # Certifique-se que esta função conectar() aponta para 'credos_data.db'
        # Mudança crucial: nomes das colunas conforme o novo banco
        query = "SELECT * FROM usuarios WHERE login=? AND senha=?"
        res = conn.cursor().execute(query, (user, pwd)).fetchone()
        conn.close()
        
        if res:
            return True
        return False
    except Exception as e:
        print(f"Erro ao verificar login: {e}")
        return False

def criar_usuario(login, senha, nome_completo="", perfil="operador", foto_b64=None):
    try:
        conn = conectar()
        cursor = conn.cursor()
        # Inserimos as 5 colunas corretas do novo banco
        cursor.execute(
            "INSERT INTO usuarios (login, senha, nome_completo, perfil, foto_b64) VALUES (?, ?, ?, ?, ?)", 
            (login, senha, nome_completo, perfil, foto_b64)
        )
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
        conn.row_factory = sqlite3.Row # Permite que a tela leia como dicionário (u['nome_completo'])
        cursor = conn.cursor()
        # Buscamos todas as colunas essenciais para a tela não dar KeyError
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
        # A tela app.py passa o 'login' (e-mail) para deletar, não mais o 'id'
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
        # Atualizado para as colunas 'senha' e 'login'
        conn.cursor().execute("UPDATE usuarios SET senha=? WHERE login=?", (nova_senha, login))
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
        
        # Dinamismo: atualiza foto e senha apenas se o Admin preencheu no modal de edição
        if senha and foto_b64:
            cursor.execute("UPDATE usuarios SET nome_completo=?, perfil=?, senha=?, foto_b64=? WHERE login=?", (nome_completo, perfil, senha, foto_b64, login))
        elif senha:
            cursor.execute("UPDATE usuarios SET nome_completo=?, perfil=?, senha=? WHERE login=?", (nome_completo, perfil, senha, login))
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
    # Reaproveita a função de alterar senha para facilitar a manutenção
    return alterar_senha_usuario(login, senha_padrao)

# --- GESTÃO DE UNIDADES ---

def carregar_todas_unidades_db():
    cfg = carregar_configuracoes_db()
    if cfg: return [cfg]
    return []

# ==============================================================================
# 7. ALIASES / APELIDOS (A CURA DEFINITIVA)
# ==============================================================================
# Estes aliases garantem que o manager.py encontre as funções com os nomes que ele espera

cadastrar_cliente_completo = lambda nome, cnpj, whatsapp, email, contato, *args: salvar_cliente_db(nome, cnpj, whatsapp, email, contato)
salvar_config_agendamento = salvar_agendamento_db
salvar_titulos_db = salvar_dados_no_banco
obter_clientes = listar_clientes_db
listar_layouts_db = obter_layouts_bancos
salvar_layout_db = salvar_layout_preferido
excluir_layout_db = excluir_layout
carregar_agendamento_db = obter_agendamento
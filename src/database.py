import sqlite3
import os

def get_connection():
    if not os.path.exists("database"):
        os.makedirs("database")
    return sqlite3.connect(os.path.join("database", "credos.db"))

def inicializar_banco():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            cnpj_cpf TEXT PRIMARY KEY,
            nome TEXT,
            contato TEXT,
            whatsapp TEXT,
            email TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS titulos (
            nosso_numero TEXT PRIMARY KEY,
            numero_nf TEXT,
            cnpj_cliente TEXT,
            cnpj_credor TEXT,
            valor REAL,
            vencimento TEXT,
            status TEXT DEFAULT 'ABERTO',
            FOREIGN KEY (cnpj_cliente) REFERENCES clientes (cnpj_cpf)
        )
    ''')
    conn.commit()
    conn.close()

def salvar_dados_no_banco(dados, cnpj_credor):
    conn = get_connection()
    cursor = conn.cursor()
    for item in dados:
        razao = item.get('razao_social') or item.get('pagador') or "Cliente Desconhecido"
        cnpj_cli = item.get('cnpj_cliente') or item.get('cnpj_pagador')
        
        # Insere o cliente com contato vazio se não existir
        cursor.execute('INSERT OR IGNORE INTO clientes (cnpj_cpf, nome, contato) VALUES (?, ?, ?)', (cnpj_cli, razao, ""))
        
        cursor.execute('''
            INSERT OR IGNORE INTO titulos 
            (nosso_numero, numero_nf, cnpj_cliente, cnpj_credor, valor, vencimento, status)
            VALUES (?, ?, ?, ?, ?, ?, 'ABERTO')
        ''', (item['nosso_numero'], item['numero_nf'], cnpj_cli, cnpj_credor, item['valor'], item['vencimento']))
    conn.commit()
    conn.close()

def atualizar_status_titulo(nosso_numero, novo_status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE titulos SET status = ? WHERE nosso_numero = ?", (novo_status, nosso_numero))
    conn.commit()
    conn.close()

def obter_metricas_mensais(cnpj_credor):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(valor) FROM titulos WHERE cnpj_credor = ? AND status = 'ABERTO'", (cnpj_credor,))
    vencido = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(valor) FROM titulos WHERE cnpj_credor = ? AND status = 'PAGO'", (cnpj_credor,))
    pago = cursor.fetchone()[0] or 0.0
    conn.close()
    return {"vencido": vencido, "pago": pago}

def obter_ranking_devedores(cnpj_credor):
    import pandas as pd
    conn = get_connection()
    query = """
        SELECT c.nome as Cliente, SUM(t.valor) as Total
        FROM titulos t
        JOIN clientes c ON t.cnpj_cliente = c.cnpj_cpf
        WHERE t.cnpj_credor = ? AND t.status = 'ABERTO'
        GROUP BY c.nome ORDER BY Total DESC LIMIT 5
    """
    df = pd.read_sql_query(query, conn, params=(cnpj_credor,))
    conn.close()
    return df
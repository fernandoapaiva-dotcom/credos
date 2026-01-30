import sqlite3
import os
import json
import datetime
from src.database import get_connection, carregar_configuracoes_db
from src.evolution_controller import EvolutionController

class Manager:
    def __init__(self, empresa_cnpj):
        self.empresa_cnpj = empresa_cnpj
        # Carrega as configurações desta empresa específica para usar no envio
        self.config = carregar_configuracoes_db(empresa_cnpj)

    def verificar_cliente_existe(self, nome_pagador):
        """Verifica se o cliente já está cadastrado no banco."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clientes WHERE nome = ?", (nome_pagador,))
        existe = cursor.fetchone()
        conn.close()
        return existe is not None

    def cadastrar_cliente_completo(self, nome, cnpj, whatsapp, email):
        """
        Cadastra ou Atualiza um cliente na base.
        """
        conn = get_connection()
        cursor = conn.cursor()
        try:
            # Usa REPLACE para atualizar se o nome já existir (graças ao UNIQUE no banco)
            cursor.execute("""
                INSERT OR REPLACE INTO clientes (nome, cnpj, whatsapp, email)
                VALUES (?, ?, ?, ?)
            """, (nome, cnpj, whatsapp, email))
            conn.commit()
            return True
        except Exception as e:
            print(f"Erro ao cadastrar cliente {nome}: {e}")
            return False
        finally:
            conn.close()

    def get_email_cliente(self, nome_cliente):
        """Retorna o e-mail do cliente para o Robô enviar cobrança."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT email FROM clientes WHERE nome = ?", (nome_cliente,))
        row = cursor.fetchone()
        conn.close()
        if row and row['email']:
            return row['email'].strip()
        return None

    def conciliar_titulos(self, novos_dados):
        """
        Compara o que veio no PDF novo com o que está no Banco.
        Se algo estava 'Aberto' no banco e NÃO veio no PDF novo, 
        significa que foi BAIXADO (Pago).
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. Pega todos os títulos ABERTOS desta empresa no banco
        cursor.execute("""
            SELECT numero_nf FROM titulos 
            WHERE cnpj_credor = ? AND status = 'Aberto'
        """, (self.empresa_cnpj,))
        
        titulos_banco = {row[0] for row in cursor.fetchall()}
        
        # 2. Pega os títulos que vieram no PDF agora
        # (O extrator pode devolver 'numero' ou 'numero_nf')
        titulos_pdf = {t.get('numero') or t.get('numero_nf') for t in novos_dados}
        
        # 3. A diferença são os que sumiram (Baixados)
        baixados = list(titulos_banco - titulos_pdf)
        
        conn.close()
        return baixados

    def atualizar_status_titulo(self, numero_nf, novo_status):
        """Muda o status (ex: de Aberto para Pago)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE titulos SET status = ? 
            WHERE numero_nf = ? AND cnpj_credor = ?
        """, (novo_status, numero_nf, self.empresa_cnpj))
        conn.commit()
        conn.close()

    def agrupar_debitos_por_cliente(self):
        """
        Retorna um dicionário com quem deve e quanto deve.
        Estrutura: { 'Cliente A': {'total': 100.0, 'itens': ['NF1', 'NF2'], 'detalhes': [...]} }
        """
        conn = get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM titulos 
            WHERE cnpj_credor = ? AND status = 'Aberto'
        """, (self.empresa_cnpj,))
        
        rows = cursor.fetchall()
        conn.close()
        
        agrupado = {}
        for r in rows:
            cli = r['pagador']
            if cli not in agrupado:
                agrupado[cli] = {'total': 0.0, 'itens': [], 'detalhes': []}
            
            agrupado[cli]['total'] += r['valor']
            # Usa o numero da NF ou 'S/N' se estiver vazio
            nf_num = r['numero_nf'] if r['numero_nf'] else "S/N"
            agrupado[cli]['itens'].append(nf_num)
            
            agrupado[cli]['detalhes'].append({
                "Vencimento": r['vencimento'],
                "NF": nf_num,
                "Valor": f"R$ {r['valor']:.2f}"
            })
            
        return agrupado

    def enviar_cobranca_multipla(self, nome_cliente, texto_mensagem, lista_nfs=None):
        """
        Envia mensagem de WhatsApp usando a Evolution API configurada para esta empresa.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        # 1. Busca o telefone do cliente
        cursor.execute("SELECT whatsapp FROM clientes WHERE nome = ?", (nome_cliente,))
        res = cursor.fetchone()
        conn.close()
        
        if not res or not res[0]:
            print(f"❌ Sem telefone cadastrado para {nome_cliente}")
            return False
            
        telefone = res[0] # Ex: "5511999999999"
        
        # 2. Inicializa o controlador do WhatsApp com a config da empresa
        evo = EvolutionController(self.config)
        
        # 3. Envia o texto
        sucesso = evo.enviar_mensagem_texto(telefone, texto_mensagem)
        
        # 4. (Opcional) Enviar os PDFs se existirem na pasta data/downloads
        if sucesso and lista_nfs:
            arquivos = self.buscar_arquivos_das_nfs(lista_nfs)
            for path in arquivos:
                evo.enviar_midia(telefone, path)
                
        return sucesso

    def buscar_arquivos_das_nfs(self, lista_nfs):
        """
        Procura na pasta data/downloads se existem PDFs com o número da NF no nome.
        Retorna lista de caminhos (paths).
        """
        caminhos_encontrados = []
        pasta_downloads = "data/downloads"
        
        if not os.path.exists(pasta_downloads):
            return []
            
        arquivos_na_pasta = os.listdir(pasta_downloads)
        
        for nf in lista_nfs:
            # Lógica simples: Se o número da NF estiver no nome do arquivo
            # Ex: NF 123 -> boleto_123_servweld.pdf
            for arq in arquivos_na_pasta:
                if str(nf) in arq and arq.lower().endswith(".pdf"):
                    caminhos_encontrados.append(os.path.join(pasta_downloads, arq))
                    break # Achou um, pula para a próxima NF
                    
        return caminhos_encontrados
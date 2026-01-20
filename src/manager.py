import pandas as pd
from src.database import get_connection, obter_metricas_mensais, obter_ranking_devedores
from src.messenger import Messenger
from src.mailer import Mailer  # Importação do novo serviço

class Manager:
    def __init__(self, cnpj_credor):
        self.cnpj_credor = cnpj_credor
        self.messenger = Messenger()
        self.mailer = Mailer()  # Instância do Mailer

    def conciliar_titulos(self, dados_extraidos):
        alertas = []
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT nosso_numero, numero_nf, cnpj_cliente FROM titulos WHERE cnpj_credor = ? AND status = 'ABERTO'", (self.cnpj_credor,))
        titulos_banco = cursor.fetchall()
        nosso_numeros_pdf = [str(d['nosso_numero']) for d in dados_extraidos]
        for t_banco in titulos_banco:
            if t_banco[0] not in nosso_numeros_pdf:
                cursor.execute("SELECT nome FROM clientes WHERE cnpj_cpf = ?", (t_banco[2],))
                cliente = cursor.fetchone()
                alertas.append({"nosso_numero": t_banco[0], "nf": t_banco[1], "cliente": cliente[0] if cliente else "Desconhecido"})
        conn.close()
        return alertas

    def agrupar_debitos_por_cliente(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.nome, c.whatsapp, t.numero_nf, t.valor, t.vencimento, c.contato, c.email
            FROM titulos t JOIN clientes c ON t.cnpj_cliente = c.cnpj_cpf
            WHERE t.status = 'ABERTO' AND t.cnpj_credor = ?
        ''', (self.cnpj_credor,))
        linhas = cursor.fetchall()
        relatorio = {}
        for r in linhas:
            cliente, zap, nf, valor, venc, contato, email = r
            if cliente not in relatorio:
                relatorio[cliente] = {
                    'zap': zap, 
                    'contato': contato, 
                    'email': email, 
                    'total': 0, 
                    'itens': []
                }
            relatorio[cliente]['total'] += valor
            relatorio[cliente]['itens'].append(f"NF {nf} (Venc: {venc})")
        conn.close()
        return relatorio
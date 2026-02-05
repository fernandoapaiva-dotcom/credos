import os
import zipfile
import time
import json
from datetime import datetime
from src.database import (
    listar_titulos_por_cliente, atualizar_titulo_acao, salvar_cliente_db, listar_clientes_db, salvar_log_envio
)
from src.mail_scanner import MailScanner
from src.evolution_controller import EvolutionController
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class Manager:
    def __init__(self, cnpj_empresa):
        self.cnpj_empresa = cnpj_empresa
        from src.database import carregar_configuracoes_db
        self.config = carregar_configuracoes_db(cnpj_empresa)
        self.evo = EvolutionController(self.config) if self.config.get('evo_url') else None
        
        # --- LIMPEZA DE PASTAS ---
        self.pasta_base = "temp_data"
        self.pasta_zips = os.path.join(self.pasta_base, "zips")
        if not os.path.exists(self.pasta_zips): os.makedirs(self.pasta_zips)

    def verificar_cliente_existe(self, nome_cliente):
        clis = listar_clientes_db()
        return any(c['nome'] == nome_cliente for c in clis)

    def cadastrar_cliente_completo(self, nome, cnpj, whatsapp, email, contato=""):
        salvar_cliente_db(nome, cnpj, whatsapp, email, contato)

    def agrupar_debitos_por_cliente(self):
        todos = listar_clientes_db()
        mapa = {c['nome']: c for c in todos}
        res = {}
        for cli in mapa:
            titulos = listar_titulos_por_cliente(cli)
            pendentes = [t for t in titulos if t['acao'] == 'Cobrar' and t['status'] == 'Aberto']
            if pendentes:
                total = sum(t['valor'] for t in pendentes)
                res[cli] = {'total': total, 'itens': pendentes, 'dados_cliente': mapa[cli]}
        return res

    def _limpar_arquivos_antigos(self):
        try:
            agora = time.time()
            for root, dirs, files in os.walk(self.pasta_base):
                for f in files:
                    path = os.path.join(root, f)
                    if agora - os.path.getmtime(path) > 86400: # 24 horas
                        os.remove(path)
        except: pass

    def buscar_e_zipar_pdfs(self, nome_cliente, lista_titulos):
        self._limpar_arquivos_antigos()
        scanner = MailScanner(self.config)
        arquivos = []
        
        for t in lista_titulos:
            anexos = scanner.baixar_anexos_por_nf(str(t['numero_nf']))
            if anexos: arquivos.extend(anexos)

        # Remove duplicados
        arquivos = list(set(arquivos))
        
        # Cria TXT se não achar PDF (salva dentro da pasta Zips para não sujar raiz)
        if not arquivos:
            txt_name = f"detalhe_{nome_cliente.replace(' ','_')}.txt"
            txt_path = os.path.join(self.pasta_zips, txt_name)
            with open(txt_path, "w") as f:
                f.write(f"DETALHAMENTO - {nome_cliente}\n\n")
                for t in lista_titulos:
                    f.write(f"NF: {t['numero_nf']} | Venc: {t['vencimento']} | R$ {t['valor']:.2f}\n")
            arquivos.append(txt_path)

        zip_name = f"cobranca_{nome_cliente.replace(' ', '_')}_{int(time.time())}.zip"
        zip_path = os.path.join(self.pasta_zips, zip_name)
        
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for arq in arquivos:
                zf.write(arq, os.path.basename(arq))
        
        return zip_path, len(lista_titulos)

    def gerar_mensagem_cobranca(self, nome_cliente, dados_cliente, total, lista_itens):
        hora = datetime.now().hour
        saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
        contato = (dados_cliente.get('contato') or "Financeiro").title()
        
        detalhes = "".join([f"🧾 NF {i['numero_nf']} | Venc: {i['vencimento']} | R$ {i['valor']:,.2f}\n" for i in lista_itens])
        
        return f"""{saudacao}, {contato}.

Identificamos pendências financeiras em nome de {nome_cliente}.
Solicitamos contato em até 10 dias para regularização.

*Títulos em Aberto:*
{detalhes}
💰 *Total: R$ {total:,.2f}*

Os detalhes seguem no arquivo ZIP anexo.
Atenciosamente,
*Equipe {self.config.get('empresa_nome', 'Financeiro')}*"""

    def executar_processo_completo_cobranca(self, nome_cliente, msg, zip_path, lista_titulos_cobradas=None):
        clis = listar_clientes_db()
        dados = next((c for c in clis if c['nome'] == nome_cliente), None)
        if not dados: return {'email': False, 'whatsapp': False}
        
        res_email = False
        res_whats = False
        
        # 1. Email
        if dados.get('email'):
            res_email = self._enviar_email_smtp(dados['email'], "Aviso Financeiro", msg, zip_path)
            
        # 2. WhatsApp
        if dados.get('whatsapp') and self.evo:
            ok_t = self.evo.enviar_mensagem_texto(dados['whatsapp'], msg)
            time.sleep(1)
            ok_m = self.evo.enviar_midia(dados['whatsapp'], zip_path)
            res_whats = ok_t and ok_m

        # --- REGISTRO AVANÇADO PARA RELATÓRIOS ---
        # Aqui salvamos um JSON no banco com os IDs dos títulos cobrados
        ids_cobradas = [t['id'] for t in lista_titulos_cobradas] if lista_titulos_cobradas else []
        detalhe_json = json.dumps({"titulos_ids": ids_cobradas, "valor_total": sum(t['valor'] for t in lista_titulos_cobradas) if lista_titulos_cobradas else 0})
        
        status_final = "Sucesso Parcial"
        if res_email and res_whats: status_final = "Sucesso Total"
        elif not res_email and not res_whats: status_final = "Falha Total"
        
        salvar_log_envio(nome_cliente, "Cobrança Manual", status_final, detalhe_json)
        
        return {'email': res_email, 'whatsapp': res_whats}

    def _enviar_email_smtp(self, para, assunto, corpo, anexo):
        try:
            user = self.config.get('mail_user')
            pwd = self.config.get('mail_pass')
            srv = self.config.get('smtp_server')
            
            if para: para = para.strip().replace(";", ",")
            if para.endswith(","): para = para[:-1]
            
            msg = MIMEMultipart()
            msg['From'] = f"{self.config.get('email_envio_display','Fin')} <{user}>"
            msg['To'] = para
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))
            
            if anexo and os.path.exists(anexo):
                with open(anexo, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(anexo)}")
                msg.attach(part)
            
            try: s = smtplib.SMTP(srv, 587); s.starttls()
            except: s = smtplib.SMTP_SSL(srv, 465)
            
            s.login(user, pwd)
            s.send_message(msg)
            s.quit()
            return True
        except Exception as e:
            print(f"Erro Email: {e}")
            return False

    def salvar_edicao_titulos(self, df):
        try:
            for _, r in df.iterrows(): atualizar_titulo_acao(r['id'], r['acao'])
            return True
        except: return False
        
    def aplicar_acao_em_lote(self, ids, acao):
        try:
            for i in ids: atualizar_titulo_acao(i, acao)
            return True
        except: return False
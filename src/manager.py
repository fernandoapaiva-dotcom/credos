import os
import shutil
import zipfile
import time
import json
import base64
from datetime import datetime
from fpdf import FPDF
from src.database import (
    listar_titulos_por_cliente, atualizar_titulo_acao, salvar_cliente_db, listar_clientes_db, salvar_log_envio,
    atualizar_titulo_status_acao, listar_logs_cliente_db, carregar_configuracoes_db, carregar_agendamento_db,
    salvar_agendamento_db
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
        # GARANTE QUE O CNPJ É UMA STRING VÁLIDA
        self.cnpj_empresa = str(cnpj_empresa).strip() if cnpj_empresa else ""
        
        # Carrega configurações globais da empresa
        self.config = carregar_configuracoes_db(self.cnpj_empresa)
        self.evo = EvolutionController(self.config) if self.config.get('evo_url') else None
        
        self.pasta_base = "temp_data"
        self.pasta_zips = os.path.join(self.pasta_base, "zips")
        self.pasta_anexos = os.path.join(self.pasta_base, "attachments")
        self.pasta_imgs = os.path.join(self.pasta_base, "imgs")
        
        os.makedirs(self.pasta_zips, exist_ok=True)
        os.makedirs(self.pasta_anexos, exist_ok=True)
        os.makedirs(self.pasta_imgs, exist_ok=True)

    # --- CLIENTES & HISTÓRICO ---
    def verificar_cliente_existe(self, nome_cliente):
        clis = listar_clientes_db(self.cnpj_empresa)
        return any(c['nome'] == nome_cliente for c in clis)

    def cadastrar_cliente_completo(self, nome, cnpj, whatsapp, email, contato=""):
        salvar_cliente_db(nome, cnpj, whatsapp, email, contato)
        
    def buscar_historico_detalhado(self, nome_cliente):
        logs = listar_logs_cliente_db(nome_cliente)
        dados_formatados = []
        for log in logs:
            try: detalhe = json.loads(log['detalhe'])
            except: detalhe = {}
            data_raw = log['data_hora']
            try:
                dt_obj = datetime.strptime(data_raw, "%Y-%m-%d %H:%M:%S")
                data_fmt = dt_obj.strftime("%d/%m/%Y %H:%M")
                data_iso = dt_obj.date()
            except:
                data_fmt = data_raw; data_iso = None
            metodo = "Email"
            dest_zap = detalhe.get('destinos_zap', 0)
            if dest_zap > 0: metodo = "Email + WhatsApp" if log['status'] == 'Sucesso Total' else "WhatsApp"
            if log['status'] == 'Falha Total': metodo = "Falha"
            nfs = detalhe.get('numeros_nf', [])
            if not nfs:
                qt = len(detalhe.get('titulos_ids', []))
                txt_titulos = f"{qt} Títulos" if qt > 0 else "-"
            else: txt_titulos = ", ".join(map(str, nfs))
            dados_formatados.append({"Data": data_fmt, "Data_ISO": data_iso, "Ação": log['tipo'], "Status": log['status'], "Canais": metodo, "Títulos (NF)": txt_titulos, "ZIP Enviado?": detalhe.get('anexo', 'Nao'), "Valor Total": f"R$ {detalhe.get('valor_total', 0):,.2f}"})
        return dados_formatados

    # --- AGENDAMENTO ---
    def obter_agendamento(self):
        """Busca o agendamento e converte os nomes dos dias para a interface."""
        dados = carregar_agendamento_db(self.cnpj_empresa)
        if dados:
            mapa_inv = {0:"Segunda", 1:"Terça", 2:"Quarta", 3:"Quinta", 4:"Sexta", 5:"Sábado", 6:"Domingo"}
            try:
                dias_raw = dados.get('dias_ui', "[]")
                # Se for lista JSON ou string de números
                if "[" in dias_raw:
                    dias_nums = json.loads(dias_raw)
                else:
                    dias_nums = [int(x) for x in dias_raw.split(",") if x]
                dados['dias_ui'] = [mapa_inv[int(x)] for x in dias_nums]
            except:
                dados['dias_ui'] = []
            
            dados['pular_feriados'] = bool(dados.get('pular_feriados', True))
            dados['ativo'] = bool(dados.get('ativo', False))
            return dados
        return None
    
    def obter_layouts_bancos(self):
        """Busca os layouts de bancos salvos no banco de dados."""
        from src.database import obter_layouts_bancos as db_obter_layouts
        # Chama a função do database (ajustada para aceitar o argumento do CNPJ)
        return db_obter_layouts(self.cnpj_empresa)

    def salvar_layout_preferido(self, nome_banco, mapeamento):
        """Salva um novo mapeamento de colunas para um banco específico."""
        from src.database import salvar_layout_preferido as db_salvar_layout
        db_salvar_layout(nome_banco, mapeamento)

    def excluir_layout(self, id_layout):
        """Remove um layout de banco do sistema."""
        from src.database import excluir_layout as db_excluir_layout
        db_excluir_layout(id_layout)

    def salvar_config_agendamento(self, dias_selecionados, hora, pular_feriados, ativo):
        mapa_dias = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5, "Domingo":6}
        dias_nums = [mapa_dias[d] for d in dias_selecionados if d in mapa_dias]
        salvar_agendamento_db(self.cnpj_empresa, dias_nums, hora, pular_feriados, ativo)

    # --- FINANCEIRO & DOCUMENTOS ---
    def agrupar_debitos_por_cliente(self):
        todos = listar_clientes_db(self.cnpj_empresa)
        res = {}
        for cli in todos:
            titulos = listar_titulos_por_cliente(cli['nome'], self.cnpj_empresa)
            pendentes = [t for t in titulos if t['acao'] == 'Cobrar' and t['status'] == 'Aberto']
            if pendentes:
                total = sum(t['valor'] for t in pendentes)
                res[cli['nome']] = {'total': total, 'itens': pendentes, 'dados_cliente': cli}
        return res

    def _gerar_pdf_demonstrativo(self, nome_cliente, lista_titulos):
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16)
        empresa = self.config.get('empresa_nome', 'Financeiro')
        pdf.cell(200, 10, txt=f"Demonstrativo de Débitos - {empresa}", ln=1, align='C')
        pdf.ln(10); pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Cliente: {nome_cliente}", ln=1, align='L')
        pdf.cell(200, 10, txt=f"Data de Emissão: {datetime.now().strftime('%d/%m/%Y')}", ln=1, align='L')
        pdf.ln(10); pdf.set_font("Arial", 'B', 10)
        pdf.cell(40, 10, "Documento/NF", 1); pdf.cell(40, 10, "Vencimento", 1); pdf.cell(50, 10, "Valor (R$)", 1); pdf.ln()
        pdf.set_font("Arial", size=10); total = 0
        for t in lista_titulos:
            pdf.cell(40, 10, str(t['numero_nf']), 1); pdf.cell(40, 10, str(t['vencimento']), 1); pdf.cell(50, 10, f"{t['valor']:,.2f}", 1); pdf.ln(); total += t['valor']
        pdf.ln(5); pdf.set_font("Arial", 'B', 12)
        pdf.cell(80, 10, "Total em Aberto:", border=0); pdf.cell(50, 10, f"R$ {total:,.2f}", border=0)
        filename = f"Demonstrativo_{nome_cliente.replace(' ', '_')}_{int(time.time())}.pdf"
        filepath = os.path.join(self.pasta_zips, filename); pdf.output(filepath); return filepath

    def buscar_e_zipar_pdfs(self, nome_cliente, lista_titulos):
        config_email_base = {
            'mail_user': self.config.get('base_mail_user') or self.config.get('mail_user'),
            'mail_pass': self.config.get('base_mail_pass') or self.config.get('mail_pass'),
            'imap_server': self.config.get('base_imap_server') or self.config.get('imap_server') or 'imap.gmail.com'
        }
        
        scanner = None
        arquivos = []
        arquivos_temp_para_deletar = []
        
        if config_email_base['mail_user'] and config_email_base['mail_pass']:
            try:
                scanner = MailScanner(config_email_base)
                scanner.conectar()
                clis = listar_clientes_db(self.cnpj_empresa)
                dados_cliente = next((c for c in clis if c['nome'] == nome_cliente), None)
                cnpj_alvo = dados_cliente['cnpj'] if dados_cliente else ""
                
                for t in lista_titulos:
                    nf = str(t.get('numero_nf', '')).strip()
                    if nf:
                        anexos = scanner.baixar_anexos_por_nf_validado(nf, cnpj_alvo, nome_cliente)
                        if anexos:
                            arquivos.extend(anexos)
                            arquivos_temp_para_deletar.extend(anexos)
                scanner.fechar()
            except Exception as e:
                print(f"Erro no scanner: {e}")

        if not arquivos:
            pdf_sub = self._gerar_pdf_demonstrativo(nome_cliente, lista_titulos)
            arquivos.append(pdf_sub)
            arquivos_temp_para_deletar.append(pdf_sub)

        zip_path = os.path.join(self.pasta_zips, f"cobranca_{nome_cliente.replace(' ', '_')}_{int(time.time())}.zip")
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for arq in arquivos:
                if os.path.exists(arq):
                    zf.write(arq, os.path.basename(arq))
        
        return zip_path, arquivos_temp_para_deletar

    def executar_processo_completo_cobranca(self, nome_cliente, msg, zip_path, lista_titulos_cobradas=None, arquivos_temp=None):
        clis = listar_clientes_db(self.cnpj_empresa)
        dados = next((c for c in clis if c['nome'] == nome_cliente), None)
        if not dados: return {'email': False, 'whatsapp': False}
        
        res_email = self._enviar_email_smtp(dados['email'], "Aviso de Pendência", msg, zip_path) if dados.get('email') else False
        res_whats = False
        
        whatsapp_field = dados.get('whatsapp', '')
        if whatsapp_field and self.evo:
            numeros = [n.strip() for n in whatsapp_field.split(',') if n.strip()]
            for num in numeros:
                self.evo.enviar_mensagem_texto(num, msg)
                if zip_path and os.path.exists(zip_path):
                    self.evo.enviar_midia(num, zip_path)
            res_whats = True

        # Log de Envio
        ids = [t['id'] for t in lista_titulos_cobradas] if lista_titulos_cobradas else []
        status = "Sucesso Total" if (res_email and res_whats) else "Sucesso Parcial" if (res_email or res_whats) else "Falha"
        detalhe = json.dumps({"titulos_ids": ids, "valor_total": sum(t['valor'] for t in lista_titulos_cobradas) if lista_titulos_cobradas else 0})
        salvar_log_envio(nome_cliente, "Cobrança Manual", status, detalhe)

        return {'email': res_email, 'whatsapp': res_whats}

    def _enviar_email_smtp(self, para, assunto, corpo, anexo):
        try:
            user = self.config.get('fin_mail_user') or self.config.get('mail_user')
            pwd = self.config.get('fin_mail_pass') or self.config.get('mail_pass')
            srv = self.config.get('fin_smtp_server') or self.config.get('smtp_server')
            
            msg = MIMEMultipart()
            msg['From'] = user
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
            
            s = smtplib.SMTP(srv, 587)
            s.starttls()
            s.login(user, pwd)
            s.send_message(msg)
            s.quit()
            return True
        except Exception as e:
            print(f"Erro email: {e}")
            return False

    def salvar_edicao_titulos(self, df):
        try:
            for _, r in df.iterrows():
                atualizar_titulo_status_acao(r['id'], r['status'], r['acao'])
            return True
        except: return False

    def excluir_layout_banco(self, layout_id):
        """Ponte para a exclusão do layout no banco de dados."""
        from src.database import excluir_layout_db
        return excluir_layout_db(layout_id)
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
    atualizar_titulo_status_acao, listar_logs_cliente_db
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
        
        from src.database import carregar_configuracoes_db
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
        salvar_cliente_db(self.cnpj_empresa, nome, cnpj, whatsapp, email, contato)
        
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

    def gerar_relatorio_historico_pdf(self, nome_cliente, dados_lista):
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        logo_b64 = self.config.get('logo_b64')
        if logo_b64:
            try:
                img_path = os.path.join(self.pasta_imgs, f"logo_{int(time.time())}.png")
                with open(img_path, "wb") as f: f.write(base64.b64decode(logo_b64))
                pdf.image(img_path, x=10, y=8, h=20)
            except: pass
        pdf.set_font("Arial", 'B', 16); pdf.set_xy(40, 10); pdf.cell(0, 10, self.config.get('empresa_nome', 'Minha Empresa'), ln=True)
        pdf.set_font("Arial", '', 10); pdf.set_xy(40, 18); pdf.cell(0, 10, f"Relatório de Histórico de Cobrança - Cliente: {nome_cliente}", ln=True)
        pdf.line(10, 30, 280, 30); pdf.ln(10)
        pdf.set_y(35); pdf.set_font("Arial", 'B', 10)
        col_w = [35, 110, 35, 15, 30, 30] 
        headers = ["Data Envio", "Títulos (NF)", "Canais", "ZIP?", "Status", "Valor"]
        for i, h in enumerate(headers): pdf.cell(col_w[i], 10, h, 1, 0, 'C')
        pdf.ln(); pdf.set_font("Arial", '', 9); margin_left = 10
        for row in dados_lista:
            d_data = str(row['Data']); d_titulos = str(row['Títulos (NF)']); d_canais = str(row['Canais']); d_zip = str(row['ZIP Enviado?']); d_status = str(row['Status']); d_valor = str(row['Valor Total'])
            base_y = pdf.get_y(); pdf.set_xy(margin_left + col_w[0], base_y); pdf.multi_cell(col_w[1], 5, d_titulos, border=0, align='L')
            final_y = pdf.get_y(); row_height = final_y - base_y
            if row_height < 10: row_height = 10; final_y = base_y + 10
            pdf.set_xy(margin_left, base_y); pdf.cell(col_w[0], row_height, d_data, border=1, align='C')
            pdf.rect(margin_left + col_w[0], base_y, col_w[1], row_height)
            pdf.set_xy(margin_left + col_w[0] + col_w[1], base_y); pdf.cell(col_w[2], row_height, d_canais, border=1, align='C')
            pdf.set_xy(margin_left + col_w[0] + col_w[1] + col_w[2], base_y); pdf.cell(col_w[3], row_height, d_zip, border=1, align='C')
            pdf.set_xy(margin_left + col_w[0] + col_w[1] + col_w[2] + col_w[3], base_y); pdf.cell(col_w[4], row_height, d_status, border=1, align='C')
            pdf.set_xy(margin_left + col_w[0] + col_w[1] + col_w[2] + col_w[3] + col_w[4], base_y); pdf.cell(col_w[5], row_height, d_valor, border=1, align='R')
            pdf.set_y(final_y)
        filename = f"Relatorio_{nome_cliente.replace(' ', '_')}_{int(time.time())}.pdf"
        filepath = os.path.join(self.pasta_base, filename); pdf.output(filepath); return filepath

    def agrupar_debitos_por_cliente(self):
        todos = listar_clientes_db(self.cnpj_empresa)
        mapa = {c['nome']: c for c in todos}
        res = {}
        for cli in mapa:
            titulos = listar_titulos_por_cliente(cli, self.cnpj_empresa)
            pendentes = [t for t in titulos if t['acao'] == 'Cobrar' and t['status'] == 'Aberto']
            if pendentes:
                total = sum(t['valor'] for t in pendentes)
                res[cli] = {'total': total, 'itens': pendentes, 'dados_cliente': mapa[cli]}
        return res

    def obter_layouts_bancos(self):
        from src.database import listar_layouts_db
        return listar_layouts_db(self.cnpj_empresa)

    def salvar_layout_preferido(self, nome_banco, mapeamento):
        from src.database import salvar_layout_db
        salvar_layout_db(self.cnpj_empresa, nome_banco, mapeamento)

    def excluir_layout(self, id_layout):
        from src.database import excluir_layout_db
        excluir_layout_db(id_layout)

    def salvar_config_agendamento(self, dias_selecionados, hora, pular_feriados, ativo):
        from src.database import salvar_agendamento_db
        mapa_dias = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5, "Domingo":6}
        dias_nums = [mapa_dias[d] for d in dias_selecionados if d in mapa_dias]
        salvar_agendamento_db(self.cnpj_empresa, dias_nums, hora, 1 if pular_feriados else 0, 1 if ativo else 0)

    def obter_agendamento(self):
        from src.database import carregar_agendamento_db
        dados = carregar_agendamento_db(self.cnpj_empresa)
        if dados:
            mapa_inv = {0:"Segunda", 1:"Terça", 2:"Quarta", 3:"Quinta", 4:"Sexta", 5:"Sábado", 6:"Domingo"}
            dias_nums = [int(x) for x in dados['dias_semana'].split(",") if x]
            dados['dias_ui'] = [mapa_inv[x] for x in dias_nums]
            dados['pular_feriados'] = bool(dados['pular_feriados'])
            dados['ativo'] = bool(dados['ativo'])
        return dados

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
        scanner = MailScanner(self.config); arquivos = []; arquivos_temp_para_deletar = [] 
        clis = listar_clientes_db(self.cnpj_empresa); dados_cliente = next((c for c in clis if c['nome'] == nome_cliente), None)
        cnpj_alvo = dados_cliente['cnpj'] if dados_cliente else ""; nome_alvo = nome_cliente
        print(f"🔍 Buscando arquivos para: {nome_cliente} (CNPJ: {cnpj_alvo})")
        for t in lista_titulos:
            anexos = scanner.baixar_anexos_por_nf_validado(str(t['numero_nf']), cnpj_alvo, nome_alvo)
            if anexos: arquivos.extend(anexos); arquivos_temp_para_deletar.extend(anexos)
            else: print(f"⚠️ NF {t['numero_nf']}: Nenhum anexo validado encontrado.")
        arquivos = list(set(arquivos))
        if len(arquivos) == 0:
            print("📄 Fallback: Gerando PDF Demonstrativo...")
            try: pdf_sub = self._gerar_pdf_demonstrativo(nome_cliente, lista_titulos); arquivos.append(pdf_sub); arquivos_temp_para_deletar.append(pdf_sub)
            except Exception as e: print(f"Erro PDF: {e}")
        zip_path = None
        if arquivos:
            zip_name = f"cobranca_{nome_cliente.replace(' ', '_')}_{int(time.time())}.zip"
            zip_path = os.path.join(self.pasta_zips, zip_name)
            with zipfile.ZipFile(zip_path, 'w') as zf:
                for arq in arquivos: zf.write(arq, os.path.basename(arq))
        return zip_path, arquivos_temp_para_deletar

    def executar_processo_completo_cobranca(self, nome_cliente, msg, zip_path, lista_titulos_cobradas=None, arquivos_temp=None):
        clis = listar_clientes_db(self.cnpj_empresa); dados = next((c for c in clis if c['nome'] == nome_cliente), None)
        if not dados: return {'email': False, 'whatsapp': False}
        res_email = False; res_whats = False
        try:
            if dados.get('email'): res_email = self._enviar_email_smtp(dados['email'], "Aviso de Pendência", msg, zip_path)
            whatsapp_field = dados.get('whatsapp', '')
            if whatsapp_field and self.evo:
                numeros = whatsapp_field.split(','); sucessos_zap = 0
                for num in numeros:
                    num = num.strip(); 
                    if not num: continue
                    self.evo.enviar_mensagem_texto(num, msg); time.sleep(1.5)
                    if zip_path and os.path.exists(zip_path):
                        if self.evo.enviar_midia(num, zip_path): sucessos_zap += 1
                    else: sucessos_zap += 1
                if sucessos_zap > 0: res_whats = True
            ids = [t['id'] for t in lista_titulos_cobradas] if lista_titulos_cobradas else []
            numeros_nf = [t['numero_nf'] for t in lista_titulos_cobradas] if lista_titulos_cobradas else []
            detalhe_json = json.dumps({"titulos_ids": ids, "numeros_nf": numeros_nf, "valor_total": sum(t['valor'] for t in lista_titulos_cobradas) if lista_titulos_cobradas else 0, "destinos_zap": len(numeros) if whatsapp_field else 0, "anexo": "Sim" if (zip_path and os.path.exists(zip_path)) else "Nao"})
            status = "Sucesso Total" if (res_email and res_whats) else "Falha Total" if (not res_email and not res_whats) else "Sucesso Parcial"
            salvar_log_envio(nome_cliente, "Cobrança Manual", status, detalhe_json)
        finally:
            try:
                if zip_path and os.path.exists(zip_path): os.remove(zip_path)
                if arquivos_temp:
                    for f in arquivos_temp:
                         if os.path.exists(f): os.remove(f)
            except Exception as e: print(f"Erro clean: {e}")
        return {'email': res_email, 'whatsapp': res_whats}

    def _enviar_email_smtp(self, para, assunto, corpo, anexo):
        try:
            user = self.config.get('mail_user'); pwd = self.config.get('mail_pass'); srv = self.config.get('smtp_server')
            if para: para = para.strip().replace(";", ",")
            if para.endswith(","): para = para[:-1]
            msg = MIMEMultipart(); msg['From'] = f"{self.config.get('email_envio_display','Fin')} <{user}>"; msg['To'] = para; msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))
            if anexo and os.path.exists(anexo):
                with open(anexo, "rb") as f: part = MIMEBase("application", "octet-stream"); part.set_payload(f.read())
                encoders.encode_base64(part); part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(anexo)}"); msg.attach(part)
            try: s = smtplib.SMTP(srv, 587); s.starttls()
            except: s = smtplib.SMTP_SSL(srv, 465)
            s.login(user, pwd); s.send_message(msg); s.quit(); return True
        except Exception as e: print(f"Erro mail: {e}"); return False

    def salvar_edicao_titulos(self, df):
        try:
            for _, r in df.iterrows():
                novo_status = r['status']; nova_acao = r['acao']
                if nova_acao == 'Pago': novo_status = 'Pago'
                if novo_status == 'Pago': nova_acao = 'Pago'
                atualizar_titulo_status_acao(r['id'], novo_status, nova_acao)
            return True
        except: return False
    
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

Atenciosamente,
*Equipe {self.config.get('empresa_nome', 'Financeiro')}*"""
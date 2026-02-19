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
        
        # Sobrescreve com ENV se faltar no banco
        if not self.config.get('evo_url'): self.config['evo_url'] = os.getenv("SERVER_URL")
        if not self.config.get('evo_key'): self.config['evo_key'] = os.getenv("AUTHENTICATION_API_KEY")

        # Instância dinâmica (CNPJ sem pontos/traços)
        inst_name = self.cnpj_empresa.replace('.', '').replace('/', '').replace('-', '')
        self.evo = EvolutionController(self.config, nome_empresa_cliente=inst_name) if self.config.get('evo_url') else None
        
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
        logs = listar_logs_cliente_db(self.cnpj_empresa, nome_cliente)
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
        db_salvar_layout(self.cnpj_empresa, nome_banco, mapeamento)

    def excluir_layout(self, id_layout):
        """Remove um layout de banco do sistema."""
        from src.database import excluir_layout as db_excluir_layout
        db_excluir_layout(self.cnpj_empresa, id_layout)

    def salvar_config_agendamento(self, dias_selecionados, hora, pular_feriados, ativo):
        mapa_dias = {"Segunda":0, "Terça":1, "Quarta":2, "Quinta":3, "Sexta":4, "Sábado":5, "Domingo":6}
        dias_nums = [mapa_dias[d] for d in dias_selecionados if d in mapa_dias]
        salvar_agendamento_db(self.cnpj_empresa, dias_nums, hora, pular_feriados, ativo)

    # --- FINANCEIRO & DOCUMENTOS ---
    def calcular_valores_cdc(self, valor_original, data_vencimento_str):
        """Calcula Multa (2%) e Juros de Mora (1%/mês pro-rata) desde o 1º dia de atraso."""
        import datetime
        try:
            # Limpa a string de data
            d_str = str(data_vencimento_str).strip().split(' ')[0]
            # Tenta formatos comuns: YYYY-MM-DD ou DD/MM/YYYY
            if '-' in d_str:
                venc = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            elif '/' in d_str:
                venc = datetime.datetime.strptime(d_str, "%d/%m/%Y").date()
            else:
                venc = datetime.date.today()
        except:
            venc = datetime.date.today()
            
        hoje = datetime.date.today()
        dias_atraso = (hoje - venc).days
        
        multa = 0.0
        juros = 0.0
        total = valor_original
        
        if dias_atraso > 0:
            # Pega taxas da config ou usa padrão seguro (garante que não seja None)
            p_multa = (self.config.get('multa_fixed') if self.config.get('multa_fixed') is not None else 2.0) / 100.0
            p_juros_mes = (self.config.get('juros_mensal') if self.config.get('juros_mensal') is not None else 1.0) / 100.0
            p_juros_dia = p_juros_mes / 30.0
            
            multa = valor_original * p_multa
            juros = valor_original * (p_juros_dia * dias_atraso)
            total = valor_original + multa + juros
            
        return {
            'principal': valor_original,
            'multa': multa,
            'juros': juros,
            'total': total,
            'dias_atraso': max(0, dias_atraso)
        }

    def agrupar_debitos_por_cliente(self):
        todos = listar_clientes_db(self.cnpj_empresa)
        res = {}
        for cli in todos:
            titulos = listar_titulos_por_cliente(self.cnpj_empresa, cli['nome'])
            pendentes = []
            for t in titulos:
                if t['acao'] == 'Cobrar' and t['status'] in ('Aberto', 'Manter Aberto'):
                    calc = self.calcular_valores_cdc(t['valor'], t['vencimento'])
                    t_copy = dict(t)
                    t_copy.update(calc)
                    pendentes.append(t_copy)
            
            if pendentes:
                total_cli = sum(t['total'] for t in pendentes)
                total_principal = sum(t['principal'] for t in pendentes)
                res[cli['nome']] = {
                    'total': total_cli, 
                    'principal': total_principal,
                    'itens': pendentes, 
                    'dados_cliente': cli
                }
        return res

    def gerar_mensagem_cobranca(self, nome_cliente, dados_cliente, total, itens):
        import datetime
        agora = datetime.datetime.now()
        hoje = agora.date()
        saudacao = "Bom dia" if agora.hour < 12 else "Boa tarde" if agora.hour < 18 else "Boa noite"
        
        contato = dados_cliente.get('contato') or dados_cliente.get('nome') or nome_cliente
        empresa_dona = self.config.get('empresa_nome', 'Nossa Empresa')
        prazo_cartorio_config = self.config.get('dias_para_cartorio') if self.config.get('dias_para_cartorio') is not None else 10
        
        # Encontra o título mais antigo para a contagem regressiva
        dias_max_atraso = max([it.get('dias_atraso', 0) for it in itens]) if itens else 0
        restante_cartorio = prazo_cartorio_config - dias_max_atraso
        
        msg = f"{saudacao}, {contato}.\n\n"
        msg += f"Identificamos pendências financeiras em aberto em nome de *{nome_cliente}*.\n\n"
        
        # Lógica Regressiva de Cartório - MAIS INCISIVA
        if restante_cartorio > 5:
            msg += f"🗓️ *Aviso:* Faltam {restante_cartorio} dias para o início do processo de negativação/cartório.\n"
            msg += f"Solicitamos a regularização imediata para evitar encargos adicionais.\n"
        elif 1 < restante_cartorio <= 5:
            msg += f"⚠️ *ALERTA URGENTE:* Faltam apenas *{restante_cartorio} dias* para o envio automático deste débito ao *CARTÓRIO*.\n"
        elif restante_cartorio == 1:
            msg += f"🚨 *NOTIFICAÇÃO FINAL:* Seu título será instruído para *CARTÓRIO AMANHÃ*.\n"
        elif restante_cartorio == 0:
            msg += f"❗ *PRAZO ESGOTADO:* O título atingiu o prazo limite e o processo de *CARTÓRIO* será iniciado HOJE.\n"
        else:
            msg += f"❗ *EM PROCESSO DE CARTÓRIO:* Este débito já ultrapassou o prazo limite de {prazo_cartorio_config} dias.\n"

        msg += f"\n📋 *Detalhamento dos Títulos:*\n"
        
        sum_multa = 0
        sum_juros = 0
        for item in itens:
            sum_multa += item.get('multa', 0)
            sum_juros += item.get('juros', 0)
            msg += f"🧾 *NF {item['numero_nf']}* | Venc: {item['vencimento']}\n"
            msg += f"   • Atraso: {item.get('dias_atraso', 0)} dias\n"
            msg += f"   • Principal: R$ {item['principal']:,.2f}\n"
            if item.get('multa', 0) > 0 or item.get('juros', 0) > 0:
                msg += f"   • (+) Multa (2%): R$ {item['multa']:,.2f}\n"
                msg += f"   • (+) Juros Mora: R$ {item['juros']:,.2f}\n"
            msg += f"   • Subtotal: R$ {item['total']:,.2f}\n\n"
            
        if sum_multa > 0 or sum_juros > 0:
            msg += f"--- \n"
            msg += f"💰 *Total Principal:* R$ {sum(it['principal'] for it in itens):,.2f}\n"
            msg += f"📈 *Total Encargos:* R$ {sum_multa + sum_juros:,.2f}\n"

        msg += f"✅ *VALOR TOTAL ATUALIZADO:* R$ {total:,.2f}\n\n"
        msg += f"Gentileza entrar em contato para regularização.\n\n"
        msg += f"Atenciosamente,\nEquipe *{empresa_dona}*"
        return msg

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
            'mail_user': self.config.get('base_mail_user'),
            'mail_pass': self.config.get('base_mail_pass'),
            'imap_server': self.config.get('imap_server', 'imap.gmail.com')
        }
        
        scanner = None
        arquivos = []
        arquivos_temp_para_deletar = []
        
        if config_email_base['mail_user'] and config_email_base['mail_pass']:
            try:
                scanner = MailScanner(config_email_base)
                clis = listar_clientes_db(self.cnpj_empresa)
                dados_cliente = next((c for c in clis if c['nome'] == nome_cliente), None)
                cnpj_alvo = dados_cliente['cnpj'] if dados_cliente else ""
                
                for t in lista_titulos:
                    nf = str(t.get('numero_nf', '')).strip()
                    if nf:
                        anexos = scanner.baixar_anexos_por_nf_validado(nf, cnpj_alvo, nome_cliente, t.get('vencimento'), t.get('valor'))
                        if anexos:
                            arquivos.extend(anexos)
                            arquivos_temp_para_deletar.extend(anexos)
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

    def executar_processo_completo_cobranca(self, nome_cliente, msg, zip_path, lista_titulos_cobradas=None, arquivos_temp=None, usuario=None, simulacao=False, canais_selecionados=None):
        clis = listar_clientes_db(self.cnpj_empresa)
        dados = next((c for c in clis if c['nome'] == nome_cliente), None)
        if not dados: return {'email': False, 'whatsapp': False}
        
        if canais_selecionados is None:
            canais_selecionados = ['email', 'whatsapp']
            
        status_canais = {"email": "Não Enviado", "whatsapp": "Não Enviado"}
        
        res_email = False
        email_field = dados.get('email', '')
        if email_field and 'email' in canais_selecionados:
            if simulacao:
                print(f"🧪 [SIMULAÇÃO] Enviando e-mail para {email_field}")
                res_email = True
                status_canais['email'] = "SIMULADO"
            else:
                res_email = self._enviar_email_smtp(email_field, "Aviso de Pendência", msg, zip_path)
                status_canais['email'] = "OK" if res_email else "FALHA"
        
        res_whats = False
        whatsapp_field = dados.get('whatsapp', '')
        if whatsapp_field and self.evo and 'whatsapp' in canais_selecionados:
            numeros = [n.strip() for n in whatsapp_field.split(';') if n.strip()]
            success_count = 0
            for num in numeros:
                if simulacao:
                    print(f"🧪 [SIMULAÇÃO] Enviando WhatsApp para {num}")
                    success_count += 1
                else:
                    print(f"☎️ Tentando WhatsApp para {num}...")
                    status_txt = self.evo.enviar_mensagem_texto(num, msg)
                    if status_txt:
                        print(f"✅ WhatsApp texto enviado para {num}!")
                        success_count += 1
                        if zip_path and os.path.exists(zip_path):
                            print(f"📎 Tentando enviar anexo ZIP para {num}...")
                            self.evo.enviar_midia(num, zip_path)
                    else:
                        print(f"❌ Falha ao enviar WhatsApp Texto para {num}")
            
            res_whats = (success_count > 0)
            if simulacao:
                status_canais['whatsapp'] = "SIMULADO"
            else:
                status_canais['whatsapp'] = f"OK ({success_count}/{len(numeros)})" if success_count > 0 else "FALHA"

        # Status do envio para o log (agora mais detalhado para o PDF)
        # O PDF usará status_canais depois, mas para compatibilidade mantemos o status geral
        status_geral = "SIMULADO" if simulacao else "Sucesso" if (res_email or res_whats) else "Falha"
        
        # Log de Envio detalhado
        detalhe_info = {
            "titulos": [
                {"numero_nf": t.get('numero_nf'), "valor": t.get('valor')} 
                for t in lista_titulos_cobradas
            ] if lista_titulos_cobradas else [],
            "valor_total": sum(t['valor'] for t in lista_titulos_cobradas) if lista_titulos_cobradas else 0,
            "simulacao": simulacao,
            "canais": status_canais
        }
        salvar_log_envio(self.cnpj_empresa, nome_cliente, "Cobrança Manual", status_geral, json.dumps(detalhe_info), usuario=usuario)

        # Limpeza
        if zip_path and os.path.exists(zip_path):
            try: os.remove(zip_path)
            except: pass
        if arquivos_temp:
            for f in arquivos_temp:
                if os.path.exists(f):
                    try: os.remove(f)
                    except: pass

        return {'email': res_email, 'whatsapp': res_whats}

    def _enviar_email_smtp(self, para, assunto, corpo, anexo):
        try:
            user = self.config.get('fin_mail_user') or self.config.get('base_mail_user')
            pwd = self.config.get('fin_mail_pass') or self.config.get('base_mail_pass')
            srv = self.config.get('smtp_server')
            
            if not srv or not user or not pwd: return False
            
            # Trata múltiplos destinatários
            lista_para = [p.strip() for p in para.split(';') if p.strip()]
            if not lista_para: return False

            msg = MIMEMultipart()
            msg['From'] = user
            msg['To'] = ", ".join(lista_para)
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))
            
            if anexo and os.path.exists(anexo):
                with open(anexo, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(anexo)}")
                    msg.attach(part)
            
            with smtplib.SMTP_SSL(srv, 465) as smtp:
                smtp.login(user, pwd)
                smtp.send_message(msg)
            return True
        except Exception as e:
            print(f"📧 Erro SMTP: {e}")
            return False

    def salvar_edicao_titulos(self, df):
        try:
            for _, r in df.iterrows():
                atualizar_titulo_status_acao(self.cnpj_empresa, r['id'], r['status'], r['acao'])
            return True
        except: return False

    def excluir_layout_banco(self, layout_id):
        """Ponte para a exclusão do layout no banco de dados."""
        from src.database import excluir_layout_db
        return excluir_layout_db(self.cnpj_empresa, layout_id)

    def registrar_mudanca_status(self, titulo_id, usuario, status_ant, status_novo, acao):
        from src.database import registrar_auditoria_titulo, atualizar_titulo_status_acao
        atualizar_titulo_status_acao(self.cnpj_empresa, titulo_id, status_novo, acao)
        registrar_auditoria_titulo(self.cnpj_empresa, titulo_id, usuario, status_ant, status_novo, acao)

    def gerar_relatorio_pdf_cobrancas(self, filtros):
        from fpdf import FPDF
        from src.database import conectar
        import pandas as pd
        import json
        
        conn = conectar(self.cnpj_empresa)
        params = []
        
        if filtros.get('tipo') == "Pagos":
            query = """
                SELECT a.data_hora as data_envio, t.pagador as cliente, 'Variação Status' as tipo_envio, 
                       'Sucesso' as status, a.usuario, 
                       json_object('titulos', json_array(json_object('numero_nf', t.numero_nf, 'valor', t.valor)), 
                                   'valor_total', t.valor, 'simulacao', 0, 
                                   'canais', json_object('email', 'Ação Manual', 'whatsapp', 'Ação Manual')) as detalhes
                FROM auditoria_titulos a
                JOIN titulos t ON a.titulo_id = t.id
                WHERE a.status_novo = 'Pago'
            """
            if filtros.get('cliente'):
                query += " AND t.pagador = ?"
                params.append(filtros['cliente'])
            if filtros.get('data_inicio'):
                query += " AND a.data_hora >= ?"
                params.append(filtros['data_inicio'] + " 00:00:00")
            if filtros.get('data_fim'):
                query += " AND a.data_hora <= ?"
                params.append(filtros['data_fim'] + " 23:59:59")
        else:
            query = """
                SELECT l.data_envio, l.cliente, l.tipo_envio, l.status, l.usuario, l.detalhes
                FROM logs_envio l
                WHERE 1=1
            """
            if filtros.get('cliente'):
                query += " AND l.cliente = ?"
                params.append(filtros['cliente'])
            if filtros.get('data_inicio'):
                query += " AND l.data_envio >= ?"
                params.append(filtros['data_inicio'] + " 00:00:00")
            if filtros.get('data_fim'):
                query += " AND l.data_envio <= ?"
                params.append(filtros['data_fim'] + " 23:59:59")
                
            if filtros.get('tipo') == "Cobranças":
                query += " AND l.tipo_envio LIKE 'Cobrança%'"
            elif filtros.get('tipo') == "Exclusões":
                query += " AND l.tipo_envio LIKE 'Exclusão%'"
            
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if df.empty: return None
        
        # Gerar o PDF
        pdf = FPDF(orientation='L', unit='mm', format='A4') # Paisagem
        pdf.add_page()
        
        def desenhar_cabecalho_tabela(p):
            p.set_font("Arial", 'B', 9)
            p.set_fill_color(220, 220, 220)
            if filtros.get('tipo') == "Pagos":
                p.cell(30, 10, "Data", 1, 0, 'C', True)
                p.cell(60, 10, "Cliente", 1, 0, 'C', True)
                p.cell(140, 10, "Títulos (NF - Valor)", 1, 0, 'C', True)
                p.cell(45, 10, "Status", 1, 1, 'C', True)
            else:
                p.cell(25, 10, "Data/Hora", 1, 0, 'C', True)
                p.cell(35, 10, "Cliente", 1, 0, 'C', True)
                p.cell(70, 10, "Detalhes/Títulos", 1, 0, 'C', True)
                p.cell(20, 10, "Principal", 1, 0, 'C', True)
                p.cell(18, 10, "Juros", 1, 0, 'C', True)
                p.cell(18, 10, "Multa", 1, 0, 'C', True)
                p.cell(22, 10, "Cobrado", 1, 0, 'C', True)
                p.cell(22, 10, "Tipo", 1, 0, 'C', True)
                p.cell(25, 10, "Canais", 1, 0, 'C', True)
                p.cell(22, 10, "Usuário", 1, 1, 'C', True)

        # Cabeçalho Principal
        empresa = self.config.get('empresa_nome', 'Sistema Credos')
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, txt=empresa, ln=1, align='C')
        pdf.set_font("Arial", 'B', 12)
        tipo_rel = filtros.get('tipo', 'Todos')
        pdf.cell(0, 10, txt=f"RELATÓRIO AUDITÁVEL - {tipo_rel.upper()}", ln=1, align='C')
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 5, txt=f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=1, align='R')
        pdf.ln(5)
        
        desenhar_cabecalho_tabela(pdf)
        
        for _, row in df.iterrows():
            titulos_str = ""
            principal = 0
            juros_total = 0
            multa_total = 0
            valor_total = 0
            canais_str = ""
            modo_str = "REAL"
            
            try:
                detalhes_dict = json.loads(row['detalhes'])
                if isinstance(detalhes_dict, dict):
                    tits = detalhes_dict.get('titulos', [])
                    if tits:
                        titulos_list = [f"NF {t['numero_nf']} - R$ {t['valor']:,.2f}" for t in tits]
                        titulos_str = "\n".join(titulos_list)
                        principal = detalhes_dict.get('principal', sum(t['valor'] for t in tits))
                        juros_total = detalhes_dict.get('juros', 0)
                        multa_total = detalhes_dict.get('multa', 0)
                        valor_total = detalhes_dict.get('valor_total', principal + juros_total + multa_total)
                    
                    if detalhes_dict.get('simulacao'): modo_str = "SIMULADO"
                    
                    canais = detalhes_dict.get('canais', {})
                    if isinstance(canais, dict):
                        e_st = canais.get('email', 'N/A')
                        w_st = canais.get('whatsapp', 'N/A')
                        canais_str = f"E: {e_st}\nW: {w_st}"
                else:
                    titulos_str = str(row['detalhes'])
            except:
                titulos_str = str(row['detalhes'])

            try:
                dt_obj = datetime.strptime(row['data_envio'], "%Y-%m-%d %H:%M:%S")
                data_fmt = dt_obj.strftime("%d/%m/%Y %H:%M")
            except:
                data_fmt = str(row['data_envio'])

            current_x = pdf.get_x()
            current_y = pdf.get_y()
            
            # Cálculo de Altura Dinâmica adaptado por layout
            pdf.set_font("Arial", size=8)
            if filtros.get('tipo') == "Pagos":
                pdf.set_xy(current_x + 90, current_y)
                pdf.multi_cell(140, 5, titulos_str, 0, 'L')
                h_tits = pdf.get_y() - current_y
                pdf.set_xy(current_x + 30, current_y)
                pdf.multi_cell(60, 5, str(row['cliente']), 0, 'L')
                h_cli = pdf.get_y() - current_y
                row_height = max(h_tits, h_cli, 10)
            else:
                pdf.set_xy(current_x + 60, current_y)
                pdf.multi_cell(70, 5, titulos_str, 0, 'L')
                h_tits = pdf.get_y() - current_y
                pdf.set_xy(current_x + 25, current_y)
                pdf.multi_cell(35, 5, str(row['cliente']), 0, 'L')
                h_cli = pdf.get_y() - current_y
                pdf.set_xy(current_x + 230, current_y)
                pdf.multi_cell(25, 5, canais_str, 0, 'L')
                h_canais = pdf.get_y() - current_y
                row_height = max(h_tits, h_cli, h_canais, 10)
            
            if (current_y + row_height) > 190:
                pdf.add_page()
                desenhar_cabecalho_tabela(pdf)
                current_y = pdf.get_y()
                current_x = pdf.get_x()

            # Desenho das colunas - CONDICIONAL
            pdf.set_xy(current_x, current_y)
            if filtros.get('tipo') == "Pagos":
                pdf.cell(30, row_height, data_fmt[:10], 1, 0, 'C')
                pdf.cell(60, row_height, "", 1, 0) # Moldura Cliente 60mm
                pdf.set_xy(current_x + 30, current_y)
                pdf.multi_cell(60, 5, str(row['cliente']), 0, 'L')
                pdf.set_xy(current_x + 90, current_y)
                pdf.cell(140, row_height, "", 1, 0) # Moldura Títulos 140mm
                pdf.set_xy(current_x + 90, current_y)
                pdf.multi_cell(140, 5, titulos_str, 0, 'L')
                pdf.set_xy(current_x + 230, current_y)
                pdf.cell(45, row_height, "PAGO", 1, 1, 'C')
            else:
                pdf.cell(25, row_height, data_fmt, 1, 0, 'C')
                
                pdf.cell(35, row_height, "", 1, 0) # Moldura Cliente
                pdf.set_xy(current_x + 25, current_y)
                pdf.multi_cell(35, 5, str(row['cliente']), 0, 'L')
                
                pdf.set_xy(current_x + 60, current_y)
                pdf.cell(70, row_height, "", 1, 0) # Moldura Títulos
                pdf.set_xy(current_x + 60, current_y)
                pdf.multi_cell(70, 5, titulos_str, 0, 'L')
                
                # Valores CDC
                pdf.set_xy(current_x + 130, current_y)
                pdf.cell(20, row_height, f"{principal:,.2f}", 1, 0, 'R')
                pdf.cell(18, row_height, f"{juros_total:,.2f}", 1, 0, 'R')
                pdf.cell(18, row_height, f"{multa_total:,.2f}", 1, 0, 'R')
                pdf.cell(22, row_height, f"{valor_total:,.2f}", 1, 0, 'R')
                
                # Tipo e Canais
                pdf.set_xy(current_x + 208, current_y)
                tipo_txt = f"{row['tipo_envio'][:7]}\n({modo_str})"
                pdf.multi_cell(22, row_height/2, tipo_txt, 1, 'C')
                
                pdf.set_xy(current_x + 230, current_y)
                pdf.cell(25, row_height, "", 1, 0) # Moldura Canais
                pdf.set_xy(current_x + 230, current_y)
                pdf.multi_cell(25, 5, canais_str, 0, 'L')
                
                pdf.set_xy(current_x + 255, current_y)
                pdf.cell(22, row_height, str(row['usuario'] or 'Sistema')[:15], 1, 1, 'L')

        filename = f"Relatorio_Auditoria_{int(time.time())}.pdf"
        filepath = os.path.join(self.pasta_zips, filename)
        pdf.output(filepath)
        return filepath

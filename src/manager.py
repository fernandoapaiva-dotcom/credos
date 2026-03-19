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
    def calcular_valores_cdc(self, valor_original, data_vencimento_str, data_referencia=None):
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
            
        if data_referencia:
            try:
                if '-' in data_referencia:
                    hoje = datetime.datetime.strptime(data_referencia, "%Y-%m-%d").date()
                else:
                    hoje = datetime.datetime.strptime(data_referencia, "%d/%m/%Y").date()
            except:
                hoje = datetime.date.today()
        else:
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
        """
        Gera PDF de Relatório Financeiro Refinado (Fase 2).
        Fixes:
        1. Pagos/Baixados: Mostra data da baixa e calcula atraso real.
        2. Exclusões: Busca registros em logs_envio.
        3. Layout: Coluna dinâmica para data de ocorrência.
        """
        from fpdf import FPDF
        from src.database import conectar
        import pandas as pd
        import json
        from datetime import datetime

        conn = conectar(self.cnpj_empresa)
        tipo_rel = filtros.get('tipo', 'Todos')
        params = []

        # ─── Queries por tipo ──────────────────────────────────────────
        if tipo_rel == "Pagos":
            query = """
                SELECT t.vencimento, t.pagador, t.numero_nf, t.valor,
                       'Pago' as status, a.usuario, a.data_hora as data_baixa
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
            df = pd.read_sql_query(query, conn, params=params)

        elif tipo_rel == "Baixados":
            # Títulos que foram para status Baixado/Cancelado
            query = """
                SELECT t.vencimento, t.pagador, t.numero_nf, t.valor,
                       a.status_novo as status, a.usuario, a.data_hora as data_baixa
                FROM auditoria_titulos a
                JOIN titulos t ON a.titulo_id = t.id
                WHERE a.status_novo IN ('Baixado', 'Cancelado')
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
            df = pd.read_sql_query(query, conn, params=params)

        elif tipo_rel == "Exclusões":
            # Busca em logs_envio pois o título pode ter sido deletado
            query = """
                SELECT l.data_envio as data_baixa, l.cliente as pagador, 
                       'Excluído' as status, l.usuario, l.detalhes
                FROM logs_envio l 
                WHERE l.tipo_envio LIKE 'Exclusão%'
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
            
            raw_df = pd.read_sql_query(query, conn, params=params)
            rows = []
            for _, r in raw_df.iterrows():
                try:
                    det = json.loads(r['detalhes'])
                    tits = det.get('titulos', [])
                    for t in tits:
                        rows.append({
                            'vencimento': t.get('vencimento', '-'),
                            'pagador': r['pagador'],
                            'numero_nf': t.get('numero_nf', '-'),
                            'valor': t.get('valor', 0),
                            'status': 'Excluído',
                            'usuario': r['usuario'],
                            'data_baixa': r['data_baixa']
                        })
                except: pass
            df = pd.DataFrame(rows)

        elif tipo_rel == "Cartório":
            # Títulos que estão no Cartório
            query = """
                SELECT t.vencimento, t.pagador, t.numero_nf, t.valor,
                       t.status, 'Sistema' as usuario, 
                       COALESCE((SELECT MAX(data_hora) FROM auditoria_titulos a WHERE a.titulo_id = t.id AND a.status_novo = 'Cartório'), '') as data_baixa
                FROM titulos t
                WHERE t.status = 'Cartório'
            """
            if filtros.get('cliente'):
                query += " AND t.pagador = ?"
                params.append(filtros['cliente'])
            df = pd.read_sql_query(query, conn, params=params)

        else:
            # "Títulos em Aberto", "Negociados"
            status_filter = ""
            if tipo_rel == "Negociados": status_filter = "WHERE status = 'Negociado'"
            else: status_filter = "WHERE UPPER(status) IN ('ABERTO', 'MANTER ABERTO')"
            
            query = f"""
                SELECT vencimento, pagador, numero_nf, valor, status,
                       'Sistema' as usuario, '' as data_baixa
                FROM titulos {status_filter}
            """
            if filtros.get('cliente'):
                query += " AND pagador = ?"
                params.append(filtros['cliente'])
            df = pd.read_sql_query(query, conn, params=params)

        conn.close()

        if df.empty:
            return None

        # ─── Calcular juros e multa para cada título ───────────────────
        df['v_principal'] = df['valor']
        df['v_juros']     = 0.0
        df['v_multa']     = 0.0
        df['v_total']     = df['valor']
        df['dias_atraso'] = 0

        for idx, row in df.iterrows():
            try:
                # Se for pago/baixado/excluido, calculamos o atraso em relação à data da ocorrência
                data_ate = None
                if row['data_baixa']:
                    data_ate = row['data_baixa'].split(' ')[0] # YYYY-MM-DD
                    # Converter para DD/MM/YYYY para o simulador
                    d_obj = datetime.strptime(data_ate, "%Y-%m-%d")
                    data_ate = d_obj.strftime("%d/%m/%Y")

                calc = self.calcular_valores_cdc(row['valor'], row['vencimento'], data_referencia=data_ate)
                df.at[idx, 'v_principal'] = calc.get('principal', row['valor'])
                df.at[idx, 'v_juros']     = calc.get('juros', 0)
                df.at[idx, 'v_multa']     = calc.get('multa', 0)
                df.at[idx, 'v_total']     = calc.get('total', row['valor'])
                df.at[idx, 'dias_atraso'] = calc.get('dias_atraso', 0)
            except: pass

        # ─── Configuração PDF ────────────────────────────────────────────
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.set_margins(10, 10, 10)
        pdf.set_auto_page_break(auto=True, margin=12)
        pdf.add_page()

        empresa = self.config.get('empresa_nome', 'Credos SaaS').upper()

        # Colunas: Vencimento | Status | Pagador | NF | Principal | Juros | Multa | Total | Dias | Usuário | Data Baixa/Ocor
        # Ajustamos larguras para caber a nova coluna
        col_w = [18, 15, 62, 22, 21, 19, 19, 21, 15, 20, 45] # 277mm
        col_h = ["Venc.", "Status", "Pagador / Cliente", "NF", "Princ. R$", "Juros R$", "Multa R$", "Total R$", "Atr.", "Usuário", "Data Ocorrência"]

        import base64
        import tempfile
        import os

        def _draw_header():
            # Tenta carregar a logo se existir e for base64
            logo_b64 = self.config.get('logo_b64')
            tmp_logo_path = None
            if logo_b64:
                try:
                    ext = '.png'
                    if ',' in logo_b64:
                        prefix = logo_b64.split(',')[0].lower()
                        if 'jpeg' in prefix or 'jpg' in prefix:
                            ext = '.jpg'
                        logo_b64 = logo_b64.split(',')[1]
                    else:
                        if logo_b64.startswith('/9j/'):
                            ext = '.jpg'
                    
                    logo_data = base64.b64decode(logo_b64)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp.write(logo_data)
                        tmp_logo_path = tmp.name
                    pdf.image(tmp_logo_path, x=10, y=8, h=10)
                except: pass

            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 6, empresa, ln=1, align='C')
            pdf.set_font("Arial", 'B', 9)
            pdf.cell(0, 5, f"RELATÓRIO FINANCEIRO: {tipo_rel.upper()}", ln=1, align='C')
            pdf.set_font("Arial", size=7)
            pdf.cell(0, 4, f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   Total: {len(df)} registros", ln=1, align='R')
            pdf.ln(1)
            pdf.set_font("Arial", 'B', 7)
            pdf.set_fill_color(30, 80, 160); pdf.set_text_color(255, 255, 255)
            for w, h in zip(col_w, col_h): pdf.cell(w, 6, h, 1, 0, 'C', True)
            pdf.ln(); pdf.set_text_color(0, 0, 0)
            
            if tmp_logo_path and os.path.exists(tmp_logo_path):
                try: os.remove(tmp_logo_path)
                except: pass

        _draw_header()

        # ─── Dados ──────────────────────────────────────────────────────
        pdf.set_font("Arial", size=6.5)
        for i, (_, row) in enumerate(df.iterrows()):
            fill_color = (245, 248, 255) if i % 2 == 0 else (255, 255, 255)
            pdf.set_fill_color(*fill_color)
            if pdf.get_y() + 5 > 195: pdf.add_page(); _draw_header(); pdf.set_font("Arial", size=6.5)

            st = str(row['status']).lower()
            if 'aberto' in st: pdf.set_text_color(200, 100, 0)
            elif 'pago' in st: pdf.set_text_color(0, 130, 0)
            elif 'exclu' in st or 'cart' in st: pdf.set_text_color(180, 0, 0)
            else: pdf.set_text_color(0, 0, 0)

            # Formata data ocorrência
            dt_ocor = str(row['data_baixa'])
            try:
                if dt_ocor and '-' in dt_ocor:
                    dt_ocor = datetime.strptime(dt_ocor, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
            except: pass

            pdf.cell(col_w[0], 5, str(row['vencimento'])[:10], 1, 0, 'C', True)
            pdf.cell(col_w[1], 5, str(row['status'])[:10], 1, 0, 'C', True)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w[2], 5, str(row['pagador'])[:35], 1, 0, 'L', True)
            pdf.cell(col_w[3], 5, str(row['numero_nf'])[:14], 1, 0, 'C', True)
            pdf.cell(col_w[4], 5, f"{row['v_principal']:,.2f}", 1, 0, 'R', True)
            pdf.cell(col_w[5], 5, f"{row['v_juros']:,.2f}", 1, 0, 'R', True)
            pdf.cell(col_w[6], 5, f"{row['v_multa']:,.2f}", 1, 0, 'R', True)
            if row['v_juros'] > 0: pdf.set_font("Arial", 'B', 6.5); pdf.set_text_color(180, 0, 0)
            pdf.cell(col_w[7], 5, f"{row['v_total']:,.2f}", 1, 0, 'R', True)
            pdf.set_font("Arial", size=6.5); pdf.set_text_color(0, 0, 0)
            pdf.cell(col_w[8], 5, str(int(row['dias_atraso'])), 1, 0, 'C', True)
            pdf.cell(col_w[9], 5, str(row['usuario'])[:12], 1, 0, 'C', True)
            pdf.cell(col_w[10], 5, dt_ocor, 1, 1, 'C', True)

        # Totais
        pdf.ln(2); pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(220, 230, 245)
        w_label = sum(col_w[:4])
        pdf.cell(w_label, 6, f"TOTAIS ({len(df)} registros)", 1, 0, 'R', True)
        pdf.cell(col_w[4], 6, f"{df['v_principal'].sum():,.2f}", 1, 0, 'R', True)
        pdf.cell(col_w[5], 6, f"{df['v_juros'].sum():,.2f}", 1, 0, 'R', True)
        pdf.cell(col_w[6], 6, f"{df['v_multa'].sum():,.2f}", 1, 0, 'R', True)
        pdf.set_text_color(180, 0, 0)
        pdf.cell(col_w[7], 6, f"{df['v_total'].sum():,.2f}", 1, 0, 'R', True)
        pdf.set_text_color(0, 0, 0); pdf.cell(sum(col_w[8:]), 6, "", 1, 1, 'C', True)

        slug = tipo_rel.upper()
        for (a, b) in [("Í","I"),("Ã","A"),("Ç","C"),("É","E"),("Ó","O"),(" ","_")]: slug = slug.replace(a, b)
        filename = f"relatorio_{slug}_{datetime.now().strftime('%d%m%Y')}.pdf"
        filepath = os.path.join(self.pasta_zips, filename); pdf.output(filepath)
        return filepath


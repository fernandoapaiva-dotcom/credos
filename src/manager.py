import os
import json
import pandas as pd
from datetime import datetime
from fpdf import FPDF
from src.database import (
    conectar, listar_clientes_db, listar_titulos_por_cliente,
    salvar_configuracoes_db, carregar_configuracoes_db, atualizar_titulo_status_acao,
    salvar_log_envio
)
from src.mail_scanner import MailScanner
from src.evolution_controller import EvolutionController
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

class Manager:
    def __init__(self, cnpj_empresa):
        self.cnpj_empresa = cnpj_empresa
        # Carrega configurações da empresa para IA e Evolution
        self.config = carregar_configuracoes_db(cnpj_empresa)
        self.evo = EvolutionController(self.config, cnpj_empresa)

    def _formatar_data_br(self, data_str, incluir_hora=False):
        if not data_str: return "-"
        try:
            # Tenta vários formatos comuns
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(data_str[:19], fmt if len(data_str) >= len(fmt) else fmt[:len(data_str)])
                    if incluir_hora:
                        return dt.strftime("%d/%m/%Y %H:%M")
                    return dt.strftime("%d/%m/%Y")
                except: continue
            return data_str
        except: return data_str

    def obter_layouts_bancos(self):
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        c.execute("SELECT * FROM layouts_importacao")
        rows = c.fetchall()
        conn.close()
        return [dict(zip(['id','nome_layout','col_vencimento','col_numero','col_valor','col_pagador'], r)) for r in rows]

    def salvar_layout_banco(self, nome, mapa):
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        c.execute("""
            INSERT INTO layouts_importacao (nome_layout, col_vencimento, col_numero, col_valor, col_pagador)
            VALUES (?, ?, ?, ?, ?)
        """, (nome, mapa['vencimento'], mapa['numero'], mapa['valor'], mapa['pagador']))
        conn.commit()
        conn.close()

    def agrupar_debitos_por_cliente(self):
        todos = listar_clientes_db(self.cnpj_empresa)
        res = {}
        for cli in todos:
            titulos = listar_titulos_por_cliente(self.cnpj_empresa, cli['nome'])
            pendentes = []
            for t in titulos:
                if t['acao'] == 'Cobrar' and t['status'] in ('Aberto', 'Manter Aberto', 'Cartório'):
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

    def calcular_valores_cdc(self, valor_original, vencimento_str, data_referencia=None):
        """
        Calcula Multa (2% fixo) e Juros (1% ao mês pro-rata)
        Vencimento esperado em DD/MM/YYYY
        """
        try:
            venc = datetime.strptime(vencimento_str, "%d/%m/%Y")
        except:
            return {'principal': valor_original, 'multa': 0, 'juros': 0, 'total': valor_original, 'dias_atraso': 0}
            
        if data_referencia:
            try:
                hoje = datetime.strptime(data_referencia, "%d/%m/%Y")
            except:
                hoje = datetime.now()
        else:
            hoje = datetime.now()
            
        dias_atraso = (hoje - venc).days
        
        multa = 0.0
        juros = 0.0
        total = valor_original
        
        if dias_atraso > 0:
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

    def obter_agendamento(self):
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        c.execute("SELECT * FROM agendamento LIMIT 1")
        row = c.fetchone()
        conn.close()
        if not row:
            return {'dias_ui': [], 'hora_envio': '09:00', 'ignorar_feriados': True, 'ativo': False}
        import json
        try:
            dias = json.loads(row[1]) if '[' in (row[1] or '') else [d.strip() for d in (row[1] or '').split(',') if d.strip()]
        except:
            dias = []
        return {
            'dias_ui': dias,
            'hora_envio': row[2] or '09:00',
            'ignorar_feriados': bool(row[3]),
            'ativo': bool(row[4])
        }

    def salvar_config_agendamento(self, dias, hora, ignorar_feriados, ativo):
        import json
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        c.execute("DELETE FROM agendamento")
        c.execute("INSERT INTO agendamento (dias_ui, horario_envio, pular_feriados, ativo) VALUES (?, ?, ?, ?)",
                  (json.dumps(dias), hora, 1 if ignorar_feriados else 0, 1 if ativo else 0))
        conn.commit()
        conn.close()

    def gerar_mensagem_cobranca(self, nome_cliente, dados_cliente, total, itens):
        agora = datetime.now()
        saudacao = "Bom dia" if agora.hour < 12 else "Boa tarde" if agora.hour < 18 else "Boa noite"
        
        contato = dados_cliente.get('contato') or dados_cliente.get('nome') or nome_cliente
        prazo_cartorio_config = self.config.get('dias_para_cartorio') if self.config.get('dias_para_cartorio') is not None else 10
        
        has_cartorio = any(it.get('status') == 'Cartório' for it in itens)
        dias_max_atraso = max([it.get('dias_atraso', 0) for it in itens]) if itens else 0
        restante_cartorio = prazo_cartorio_config - dias_max_atraso
        
        msg = f"{saudacao}, {contato}.\n\n"
        
        if has_cartorio:
            msg += f"❗ *NOTIFICAÇÃO DE TÍTULO EM CARTÓRIO*\n\n"
            msg += f"Informamos que os débitos abaixo em nome de *{nome_cliente}* já se encontram em processo de **PROTESTO/CARTÓRIO** devido ao tempo de atraso.\n\n"
        else:
            msg += f"Identificamos pendências financeiras em aberto em nome de *{nome_cliente}*.\n\n"
        
        # Avisos de prazo (apenas se não estiver em cartório ou se houver outros a vencer)
        if not has_cartorio:
            if restante_cartorio > 5:
                msg += f"🗓️ *Aviso:* Faltam {restante_cartorio} dias para o início do processo de negativação/cartório.\n"
            elif 1 < restante_cartorio <= 5:
                msg += f"⚠️ *ALERTA URGENTE:* Faltam apenas *{restante_cartorio} dias* para o envio automático deste débito ao *CARTÓRIO*.\n"
            elif restante_cartorio == 1:
                msg += f"🚨 *NOTIFICAÇÃO FINAL:* Seu título será instruído para *CARTÓRIO AMANHÃ*.\n"
            elif restante_cartorio == 0:
                msg += f"❗ *PRAZO ESGOTADO:* O título atingiu o prazo limite e o processo de *CARTÓRIO* será iniciado HOJE.\n"
        
        if has_cartorio:
            msg += f"⚠️ *Atenção:* Títulos em cartório geram restrições imediatas ao crédito e custos adicionais operacionais.\n"

        msg += f"\n📋 *Detalhamento dos Títulos:*\n"
        
        for item in itens:
            msg += f"🧾 *NF {item['numero_nf']}* | Venc: {item['vencimento']} ({item['dias_atraso']} dias de atraso)\n"
            msg += f"   • Principal: R$ {item['principal']:,.2f}\n"
            if item.get('multa', 0) > 0 or item.get('juros', 0) > 0:
                msg += f"   • (+) Encargos: R$ {item['multa'] + item['juros']:,.2f}\n"
            msg += f"   • Subtotal: R$ {item['total']:,.2f}\n\n"
            
        msg += f"✅ *VALOR TOTAL ATUALIZADO:* R$ {total:,.2f}\n\n"
        
        if has_cartorio:
            msg += f"👉 *INSTRUÇÕES DE REGULARIZAÇÃO:*\n"
            msg += f"1. O pagamento do valor acima deve ser feito à nossa empresa para quitação do débito.\n"
            msg += f"2. As **taxas de cartório** deverão ser pagas por sua empresa **diretamente ao tabelionato**.\n"
            msg += f"3. Após confirmarmos seu pagamento, emitiremos a **CARTA DE ANUÊNCIA** digital para que você possa baixar o protesto imediatamente.\n\n"
            msg += f"Gentileza tratar este assunto com a máxima prioridade.\n\n"
        else:
            msg += f"Gentileza entrar em contato para regularização.\n\n"
        
        return msg

    def buscar_e_zipar_pdfs(self, cliente_nome, itens):
        scanner = MailScanner(self.config)
        arquivos_temp = []

        # Fetch client data to pass CNPJ
        cli_dados = listar_clientes_db(self.cnpj_empresa, nome_filtro=cliente_nome)
        dados_cli = cli_dados[0] if cli_dados else {}

        for item in itens:
            try:
                path = scanner.baixar_anexos_por_nf_validado(
                    item['numero_nf'], 
                    dados_cli.get('cnpj'), 
                    item['pagador'],
                    vencimento=item.get('vencimento'),
                    valor=item.get('valor')
                )
                if path:
                    arquivos_temp.extend(path)
            except Exception as e:
                print(f"Erro ao buscar PDF para NF {item['numero_nf']}: {e}")
        
        if not arquivos_temp: return None, []
        
        import zipfile
        zip_name = f"faturas_{cliente_nome.replace(' ', '_')}_{datetime.now().strftime('%H%M%S')}.zip"
        with zipfile.ZipFile(zip_name, 'w') as z:
            for f in arquivos_temp:
                z.write(f, os.path.basename(f))
        
        return zip_name, arquivos_temp

    def executar_processo_completo_cobranca(self, cliente_nome, msg, zip_path, itens, arquivos_temp):
        res_wa = False
        res_email = False
        
        cli_dados = listar_clientes_db(self.cnpj_empresa, nome_filtro=cliente_nome)
        if not cli_dados: return {"whatsapp": False, "email": False}
        cli = cli_dados[0]
        
        # FAIL-SAFE: Re-verifica no BANCO se os títulos ainda estão para 'Cobrar'
        # Isso evita Race Conditions se o usuário baixar o título enquanto o robô está rodando
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        itens_validados = []
        for it in itens:
            tid = it.get('id')
            if not tid: continue
            row = c.execute("SELECT status, acao FROM titulos WHERE id=?", (tid,)).fetchone()
            if row and row[1] == 'Cobrar' and row[0] in ('Aberto', 'Manter Aberto', 'Cartório'):
                itens_validados.append(it)
        conn.close()

        if not itens_validados:
            print(f"⚠️ [FAIL-SAFE] Abortando envio para {cliente_nome}: Todos os títulos foram baixados ou pausados recentemente.")
            return {"whatsapp": False, "email": False, "skipped": True}
        
        # Se alguns foram baixados mas outros não, atualizamos o conteúdo para não cobrar o que já foi pago
        itens = itens_validados
        
        # 1. Enviar WhatsApp via Evolution
        whatsapp_raw = cli.get('whatsapp')
        if whatsapp_raw:
            numeros = [n.strip() for n in whatsapp_raw.split(';') if n.strip()]
            for num in numeros:
                success = self.evo.enviar_mensagem_texto(num, msg)
                if success:
                    res_wa = True
                    if zip_path:
                        self.evo.enviar_midia(num, zip_path)

        # 2. Enviar E-mail
        email_raw = cli.get('email')
        smtp_srv = self.config.get('smtp_server')
        email_user = self.config.get('fin_mail_user')
        email_pass = self.config.get('fin_mail_pass')

        if email_raw and smtp_srv and email_user and email_pass:
            destinatarios = [e.strip() for e in email_raw.split(';') if e.strip()]
            try:
                for dest in destinatarios:
                    mail = MIMEMultipart()
                    mail['From'] = f"Financeiro <{email_user}>"
                    mail['To'] = dest
                    mail['Subject'] = f"Aviso de Cobrança - {cliente_nome}"
                    
                    corpo = f"Olá {cliente_nome},\n\n" + msg.replace("*", "")
                    mail.attach(MIMEText(corpo, 'plain'))
                    
                    if zip_path and os.path.exists(zip_path):
                        with open(zip_path, "rb") as f_zip:
                            part = MIMEApplication(f_zip.read(), Name=os.path.basename(zip_path))
                        part['Content-Disposition'] = f'attachment; filename="{os.path.basename(zip_path)}"'
                        mail.attach(part)
                    
                    with smtplib.SMTP_SSL(smtp_srv, 465) as server:
                        server.login(email_user, email_pass)
                        server.send_message(mail)
                res_email = True
            except Exception as e_mail:
                print(f"Erro ao enviar email para {cliente_nome}: {e_mail}")

        # 3. Logar no banco
        status_final = "Sucesso" if (res_wa or res_email) else "Falha"
        salvar_log_envio(
            self.cnpj_empresa, 
            cliente_nome,
            "WhatsApp/Email",
            status_final,
            json.dumps({
                "titulos": [it.get('numero_nf') for it in itens], 
                "ids": [it.get('id') for it in itens],
                "res_wa": res_wa, 
                "res_email": res_email
            }),
            "Sistema/Gerente"
        )
        
        # Cleanup
        if zip_path and os.path.exists(zip_path): 
            try: os.remove(zip_path)
            except: pass
        for f in arquivos_temp:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass
            
        return {"whatsapp": res_wa, "email": res_email}

    def cobrar_cliente_especifico(self, nome_cliente):
        fila = self.agrupar_debitos_por_cliente()
        if nome_cliente not in fila:
            return {"success": False, "message": "Nenhuma pendência para este cliente."}
        
        info = fila[nome_cliente]
        msg = self.gerar_mensagem_cobranca(nome_cliente, info['dados_cliente'], info['total'], info['itens'])
        zip_path, arquivos_temp = self.buscar_e_zipar_pdfs(nome_cliente, info['itens'])
        res = self.executar_processo_completo_cobranca(nome_cliente, msg, zip_path, info['itens'], arquivos_temp)
        return {"success": True, "res": res}

    def cobrar_titulo_unico(self, id_titulo):
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        c.execute("SELECT * FROM titulos WHERE id=?", (id_titulo,))
        row = c.fetchone()
        conn.close()
        if not row: return {"success": False, "message": "Título não encontrado."}
        
        # Colunas: id, pagador, numero_nf, vencimento, valor, status, acao
        tit = {
            'id': row[0],
            'pagador': row[1],
            'numero_nf': row[2],
            'vencimento': row[3],
            'valor': row[4],
            'status': row[5],
            'acao': row[6]
        }
        
        calc = self.calcular_valores_cdc(tit['valor'], tit['vencimento'])
        tit.update(calc) # Adiciona principal, multa, juros, total, dias_atraso
        
        cli_dados = listar_clientes_db(self.cnpj_empresa, nome_filtro=tit['pagador'])
        if not cli_dados: return {"success": False, "message": f"Cliente {tit['pagador']} não encontrado no CRM."}
        cli = cli_dados[0]
        
        msg = self.gerar_mensagem_cobranca(tit['pagador'], cli, tit['total'], [tit])
        zip_path, arquivos_temp = self.buscar_e_zipar_pdfs(tit['pagador'], [tit])
        res = self.executar_processo_completo_cobranca(tit['pagador'], msg, zip_path, [tit], arquivos_temp)
        
        return {"success": True, "res": res}

    def prever_cobranca_coletiva(self):
        """
        Retorna uma lista de clientes que seriam cobrados e o resumo dos valores.
        """
        conn = conectar(self.cnpj_empresa)
        cursor = conn.cursor()
        # Seleciona títulos elegíveis para cobrança (mesmo que pausados individualmente, o motor pode vê-los)
        # Sincronizado com agrupar_debitos_por_cliente
        cursor.execute("SELECT * FROM titulos WHERE status IN ('Aberto', 'Manter Aberto', 'Cartório')")
        rows = cursor.fetchall()
        conn.close()

        # Agrupar por pagador
        agrupados = {}
        for row in rows:
            # id, pagador, numero_nf, vencimento, valor, status, acao
            pagador = row[1]
            if pagador not in agrupados:
                agrupados[pagador] = []
            
            tit = {
                'id': row[0],
                'pagador': row[1],
                'numero_nf': row[2],
                'vencimento': row[3],
                'valor': row[4],
                'status': row[5],
                'acao': row[6]
            }
            calc = self.calcular_valores_cdc(tit['valor'], tit['vencimento'])
            tit.update(calc)
            agrupados[pagador].append(tit)

        # Buscar dados dos clientes no CRM
        resumo = []
        for pagador, itens in agrupados.items():
            cli_dados = listar_clientes_db(self.cnpj_empresa, nome_filtro=pagador)
            cli = cli_dados[0] if cli_dados else {"whatsapp": "", "email": ""}
            
            if any(it['acao'] == 'Cobrar' for it in itens):
                resumo.append({
                    "cliente": pagador,
                    "qtd_titulos": len([it for it in itens if it['acao'] == 'Cobrar']),
                    "valor_total": sum(it['total'] for it in itens if it['acao'] == 'Cobrar'),
                    "whatsapp": cli.get('whatsapp', ''),
                    "email": cli.get('email', ''),
                    "itens": sorted(itens, key=lambda x: x['vencimento'])
                })

        return sorted(resumo, key=lambda x: x['cliente'])

    def gerar_relatorio_pdf_cobrancas(self, filtros):
        """
        Gera um relatório PDF Premium baseado nos filtros (tipo, cliente, periodo).
        """
        tipo_rel = filtros.get('tipo', 'Todos')
        cliente = filtros.get('cliente')
        data_inicio = filtros.get('data_inicio')
        data_fim = filtros.get('data_fim')

        conn = conectar(self.cnpj_empresa)
        params = []
        
        # Obter nome e logo da empresa para o cabeçalho
        c = conn.cursor()
        c.execute("SELECT empresa_nome, logo_b64 FROM config LIMIT 1")
        row = c.fetchone()
        empresa_nome = row[0] if row else "EMPRESA NÃO CONFIGURADA"
        logo_b64 = row[1] if row else None

        logo_path = None
        if logo_b64:
            try:
                import base64
                import os
                if ',' in logo_b64:
                    logo_b64 = logo_b64.split(',')[1]
                
                logo_data = base64.b64decode(logo_b64)
                # Detectar formato simples
                ext = "png"
                if logo_data.startswith(b'\xff\xd8\xff'):
                    ext = "jpg"
                elif logo_data.startswith(b'GIF8'):
                    ext = "gif"
                
                logo_path = f"logo_temp_{self.cnpj_empresa}.{ext}"
                with open(logo_path, "wb") as f:
                    f.write(logo_data)
            except Exception as e:
                print(f"Erro ao decodificar logo: {e}")
                logo_path = None
        
        if tipo_rel == "Cobrados":
            # === RELATÓRIO DE ATIVIDADES DO PERÍODO ===
            today = datetime.now().strftime('%Y-%m-%d')
            dt_ini = (data_inicio + " 00:00:00") if data_inicio else (today + " 00:00:00")
            dt_fim = (data_fim + " 23:59:59") if data_fim else (today + " 23:59:59")
            
            # 1. Cobranças enviadas (WhatsApp/Email) no período
            q_logs = "SELECT l.data_envio as data_hora, l.cliente as pagador, l.detalhes as details_json, l.tipo_envio as acao_tipo, l.status as resultado, l.usuario FROM logs_envio l WHERE l.data_envio >= ? AND l.data_envio <= ?"
            p_logs = [dt_ini, dt_fim]
            if cliente and cliente != "Todos":
                q_logs += " AND l.cliente = ?"
                p_logs.append(cliente)
            
            df_logs_raw = pd.read_sql_query(q_logs, conn, params=p_logs)
            
            # Processar logs para extrair NF e formatar Detalhes
            logs_rows = []
            for _, lrow in df_logs_raw.iterrows():
                nf_val = ""
                dt_fmt = self._formatar_data_br(str(lrow['data_hora']), incluir_hora=True)
                usuario = str(lrow.get('usuario') or "Sistema")
                obs_val = f"Executado em {dt_fmt} por {usuario}"
                
                raw_js = lrow.get('details_json') or ''
                try:
                    if isinstance(raw_js, str) and raw_js.strip().startswith('{'):
                        js = json.loads(raw_js)
                        tits = js.get('titulos', [])
                        if tits:
                            t1 = tits[0]
                            if isinstance(t1, dict):
                                nf_val = str(t1.get('numero_nf') or t1.get('id') or "")
                            else:
                                nf_val = str(t1)
                except Exception as ex:
                    print(f"[WARN] Detalhes parse: {ex}")
                logs_rows.append({
                    'data_hora': lrow['data_hora'], 'pagador': lrow['pagador'],
                    'numero_nf': nf_val, 'acao_tipo': str(lrow['acao_tipo'] or ""),
                    'resultado': str(lrow['resultado'] or ""), 'obs': obs_val,
                })
            df_logs = pd.DataFrame(logs_rows)
            
            # 2. Ações em títulos (baixa, cancelamento, cartório, etc) no período
            q_audit = """SELECT a.data_hora, t.pagador, t.numero_nf, a.acao as acao_tipo, a.status_novo as resultado, a.usuario as act_user, (a.status_anterior || ' -> ' || a.status_novo) as transicao FROM auditoria_titulos a LEFT JOIN titulos t ON t.id = a.titulo_id WHERE a.data_hora >= ? AND a.data_hora <= ?"""
            p_audit = [dt_ini, dt_fim]
            if cliente and cliente != "Todos":
                q_audit += " AND t.pagador = ?"
                p_audit.append(cliente)
            df_audit_raw = pd.read_sql_query(q_audit, conn, params=p_audit)
            
            audit_rows = []
            for _, arow in df_audit_raw.iterrows():
                dt_fmt = self._formatar_data_br(str(arow['data_hora']), incluir_hora=True)
                usuario = str(arow.get('act_user') or "Sistema")
                trans = str(arow['transicao'])
                obs_val = f"{trans} (em {dt_fmt} por {usuario})"
                audit_rows.append({
                    'data_hora': arow['data_hora'], 'pagador': arow['pagador'],
                    'numero_nf': str(arow['numero_nf'] or ""), 'acao_tipo': str(arow['acao_tipo'] or ""),
                    'resultado': str(arow['resultado'] or ""), 'obs': obs_val,
                })
            df_audit = pd.DataFrame(audit_rows)
            
            df = pd.concat([df_logs, df_audit], ignore_index=True)
            df['numero_nf'] = df['numero_nf'].fillna('')
            df['pagador'] = df['pagador'].fillna('Nao identificado')
            df = df.sort_values("data_hora", ascending=False)
        
        elif tipo_rel == "Historico":
            query = "SELECT * FROM logs_envio WHERE 1=1"
            if cliente and cliente != "Todos":
                query += " AND cliente = ?"
                params.append(cliente)
            
            if data_inicio:
                query += " AND data_envio >= ?"
                params.append(data_inicio + " 00:00:00")
            if data_fim:
                query += " AND data_envio <= ?"
                params.append(data_fim + " 23:59:59")
            
            query += " ORDER BY id DESC"
            df = pd.read_sql_query(query, conn, params=params)
        
        elif tipo_rel == "Exclusoes":
            # Histórico de exclusões de títulos (auditoria com acao de exclusão)
            query = """
                SELECT 
                    a.data_hora as data_ocorrencia,
                    t.pagador, t.numero_nf, t.vencimento, t.valor,
                    a.status_anterior, a.status_novo,
                    a.acao, a.usuario
                FROM auditoria_titulos a
                LEFT JOIN titulos t ON t.id = a.titulo_id
                WHERE (a.acao LIKE '%exclu%' OR a.acao LIKE '%remov%' OR a.acao LIKE '%delet%' OR a.acao LIKE '%cancel%')
            """
            params_ex = []
            if cliente and cliente != "Todos":
                query += " AND t.pagador = ?"
                params_ex.append(cliente)
            if data_inicio:
                query += " AND a.data_hora >= ?"
                params_ex.append(data_inicio + " 00:00:00")
            if data_fim:
                query += " AND a.data_hora <= ?"
                params_ex.append(data_fim + " 23:59:59")
            query += " ORDER BY a.data_hora DESC"
            df = pd.read_sql_query(query, conn, params=params_ex)
        
        elif tipo_rel == "Negociacoes IA":
            # Relatório de Negociações geradas pela IA
            query = """
                SELECT 
                    n.criado_em as data_hora,
                    n.cliente as pagador,
                    n.mensagem_gerada as mensagem,
                    n.status_resposta,
                    (SELECT count(*) FROM titulos WHERE id IN (SELECT value FROM json_each('[' || n.titulos_ids || ']'))) as qtd_titulos
                FROM negociacoes n
                WHERE 1=1
            """
            params_n = []
            if cliente and cliente != "Todos":
                query += " AND n.cliente = ?"
                params_n.append(cliente)
            if data_inicio:
                query += " AND n.criado_em >= ?"
                params_n.append(data_inicio + " 00:00:00")
            if data_fim:
                query += " AND n.criado_em <= ?"
                params_n.append(data_fim + " 23:59:59")
            query += " ORDER BY n.id DESC"
            df = pd.read_sql_query(query, conn, params=params_n)

        elif tipo_rel == "Cartório":
            # Relatório de Títulos em Cartório (incluindo status da automação)
            query = """
                SELECT 
                    t.numero_nf, t.pagador, t.vencimento, t.valor,
                    cj.status_automacao, cj.data_execucao, cj.log_erro,
                    t.id as titulo_id
                FROM titulos t
                LEFT JOIN cartorio_jobs cj ON cj.titulo_id = t.id
                WHERE t.status = 'Cartório' OR cj.id IS NOT NULL
            """
            params_c = []
            if cliente and cliente != "Todos":
                query += " AND t.pagador = ?"
                params_c.append(cliente)
            if data_inicio:
                query += " AND (cj.data_execucao >= ? OR t.data_atualizacao >= ?)"
                params_c.extend([data_inicio + " 00:00:00", data_inicio + " 00:00:00"])
            if data_fim:
                query += " AND (cj.data_execucao <= ? OR t.data_atualizacao <= ?)"
                params_c.extend([data_fim + " 23:59:59", data_fim + " 23:59:59"])
            query += " ORDER BY cj.id DESC, t.vencimento ASC"
            df = pd.read_sql_query(query, conn, params=params_c)

        else:
            # Relatório Financeiro (Todos, Abertos, Pagos)
            status_filter = ""
            if tipo_rel == "Pagos":
                status_filter = "AND t.status IN ('Pago', 'Baixado', 'Recebido')"
            elif tipo_rel == "Aberto":
                status_filter = "AND t.status = 'Aberto'"
            
            cliente_filter = ""
            if cliente and cliente != "Todos":
                params.append(cliente)
                cliente_filter = "AND t.pagador = ?"
            
            query = f"""
                SELECT 
                    t.*,
                    a_last.usuario as aud_usuario,
                    a_last.data_hora as aud_data,
                    a_last.acao as aud_acao
                FROM titulos t
                LEFT JOIN (
                    SELECT titulo_id, usuario, data_hora, acao,
                           ROW_NUMBER() OVER (PARTITION BY titulo_id ORDER BY id DESC) as rn
                    FROM auditoria_titulos
                ) a_last ON a_last.titulo_id = t.id AND a_last.rn = 1
                WHERE 1=1 {status_filter} {cliente_filter}
                ORDER BY t.vencimento ASC
            """
            df = pd.read_sql_query(query, conn, params=params)
        
        conn.close()
        
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Logo do Sistema (Credos) - Canto Superior Esquerdo
        credos_logo = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'public', 'logo.png')
        if os.path.exists(credos_logo):
            try:
                # Usando h=12 para altura máxima fixa, mantendo proporção e evitando sobreposição na tabela
                pdf.image(credos_logo, 10, 10, h=12)
            except Exception:
                pass
        
        # Logo da Empresa cadastrada - Canto Superior Direito
        if logo_path and os.path.exists(logo_path):
            try:
                # Posição X calculada para a direita (250mm). O documento Paisagem tem 297mm.
                pdf.image(logo_path, 250, 10, h=12)
            except Exception as e:
                print(f"Erro ao inserir logo no PDF: {e}")
        
        # Cabeçalho Premium
        pdf.set_font("Arial", 'B', 14)
        pdf.set_y(15) 
        pdf.cell(0, 6, str(empresa_nome).upper(), 0, 1, 'C')
        
        # Título amigável do relatório
        titulos_relatorio = {
            "Cobrados": "ATIVIDADES DO PERÍODO (COBRANÇAS E MOVIMENTAÇÕES)",
            "Historico": "HISTÓRICO DE ENVIOS (LOGS)",
            "Exclusoes": "HISTÓRICO DE EXCLUSÕES",
            "Aberto": "TÍTULOS EM ABERTO",
            "Pagos": "TÍTULOS PAGOS / BAIXADOS",
            "Cartório": "TÍTULOS EM CARTÓRIO"
        }
        nome_rel = titulos_relatorio.get(tipo_rel, f"RELATÓRIO: {tipo_rel.upper()}")
        
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 6, nome_rel, 0, 1, 'C')
        pdf.ln(2)
        
        pdf.set_font("Arial", '', 8)
        right_text = f"Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}   |   Total: {len(df)} registros"
        pdf.cell(0, 5, right_text, 0, 1, 'R')

        if df.empty:
            pdf.ln(20)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, "Nenhum registro encontrado para estes filtros.", 0, 1, 'C')
        else:
            if tipo_rel == "Cobrados":
                # === Layout Atividades do Dia ===
                pdf.set_fill_color(30, 80, 160)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Arial", 'B', 8)
                
                cols_atv = [
                    ("Data/Hora", 38, 'C'),
                    ("Pagador / Cliente", 70, 'L'),
                    ("NF", 15, 'C'),
                    ("Tipo de Ação", 40, 'C'),
                    ("Resultado", 28, 'C'),
                    ("Detalhes / Transição", 86, 'L'),
                ]
                for c_name, c_width, _ in cols_atv:
                    pdf.cell(c_width, 7, c_name, border=1, fill=True, align='C')
                pdf.ln()
                
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", '', 7)
                fill = False
                for _, r in df.iterrows():
                    pdf.set_fill_color(240, 245, 255) if fill else pdf.set_fill_color(255, 255, 255)
                    
                    resultado = str(r.get('resultado', ''))
                    if resultado in ('Sucesso', 'Pago', 'Baixado'):
                        pdf.set_text_color(0, 130, 0)
                    elif resultado in ('Falha', 'Cancelado'):
                        pdf.set_text_color(200, 0, 0)
                    else:
                        pdf.set_text_color(60, 60, 60)
                    
                    data_hora_raw = str(r.get('data_hora', ''))
                    data_hora = self._formatar_data_br(data_hora_raw, incluir_hora=True)
                    pagador   = str(r.get('pagador', ''))[:38]
                    nf        = str(r.get('numero_nf', '') or '')[:10]
                    acao      = str(r.get('acao_tipo', ''))[:24]
                    obs       = str(r.get('obs', '') or '').replace('\n', ' ')[:60]
                    
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(cols_atv[0][1], 6, data_hora, 1, 0, 'C', fill=fill)
                    pdf.cell(cols_atv[1][1], 6, pagador,   1, 0, 'L', fill=fill)
                    pdf.cell(cols_atv[2][1], 6, nf,        1, 0, 'C', fill=fill)
                    pdf.cell(cols_atv[3][1], 6, acao,      1, 0, 'C', fill=fill)
                    
                    if resultado in ('Sucesso', 'Pago', 'Baixado'):
                        pdf.set_text_color(0, 130, 0)
                    elif resultado in ('Falha', 'Cancelado'):
                        pdf.set_text_color(200, 0, 0)
                    
                    pdf.cell(cols_atv[4][1], 6, resultado[:16], 1, 0, 'C', fill=fill)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(cols_atv[5][1], 6, obs, 1, 0, 'L', fill=fill)
                    pdf.ln()
                    fill = not fill
                    
            elif tipo_rel == "Historico":
                # Layout Premium Histórico (Tabela de Logs)
                pdf.set_fill_color(30, 80, 160)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Arial", 'B', 8)
                
                cols_hist = [
                    ("Data/Hora", 35, 'C'),
                    ("Cliente", 70, 'L'),
                    ("Ação", 35, 'C'),
                    ("Status", 25, 'C'),
                    ("Detalhes", 112, 'L')
                ]
                
                for c_name, c_width, c_align in cols_hist:
                    pdf.cell(c_width, 7, c_name, border=1, fill=True, align='C')
                pdf.ln()
                
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", '', 7)
                
                for _, r in df.iterrows():
                    pdf.cell(cols_hist[0][1], 6, str(r['data_envio']), 1, 0, 'C')
                    pdf.cell(cols_hist[1][1], 6, str(r['cliente'])[:40], 1, 0, 'L')
                    pdf.cell(cols_hist[2][1], 6, str(r['tipo_envio'])[:20], 1, 0, 'C')
                    
                    status = str(r['status'])
                    if status == "Sucesso":
                        pdf.set_text_color(0, 150, 0)
                    elif status == "Falha":
                        pdf.set_text_color(200, 0, 0)
                    else:
                        pdf.set_text_color(0, 0, 0)
                        
                    pdf.cell(cols_hist[3][1], 6, status, 1, 0, 'C')
                    
                    pdf.set_text_color(0, 0, 0)
                    det = str(r['detalhes']).replace('\n', ' ')
                    if len(det) > 85: det = det[:82] + "..."
                    pdf.cell(cols_hist[4][1], 6, det, 1, 0, 'L')
                    pdf.ln()
                    
            elif tipo_rel == "Exclusoes":
                # === Layout Histórico de Exclusões ===
                pdf.set_fill_color(180, 40, 40)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Arial", 'B', 8)
                cols_ex = [
                    ("Data Ocorrência", 42, 'C'),
                    ("Pagador / Cliente", 75, 'L'),
                    ("NF", 15, 'C'),
                    ("Vencimento", 22, 'C'),
                    ("Valor R$", 20, 'R'),
                    ("Ação", 35, 'C'),
                    ("De → Para", 60, 'L'),
                    ("Usuário", 28, 'C'),
                ]
                for c_name, c_width, _ in cols_ex:
                    pdf.cell(c_width, 7, c_name, border=1, fill=True, align='C')
                pdf.ln()
                pdf.set_text_color(0, 0, 0)
                pdf.set_font("Arial", '', 7)
                fill_ex = False
                for _, r in df.iterrows():
                    pdf.set_fill_color(255, 235, 235) if fill_ex else pdf.set_fill_color(255, 255, 255)
                    data_oc_raw = str(r.get('data_ocorrencia', ''))
                    data_oc = self._formatar_data_br(data_oc_raw, incluir_hora=True)
                    pagador_ex = str(r.get('pagador', '') or '')[:40]
                    nf_ex = str(r.get('numero_nf', '') or '')
                    venc_ex_raw = str(r.get('vencimento', '') or '')
                    venc_ex = self._formatar_data_br(venc_ex_raw)
                    valor_ex = f"{float(r.get('valor', 0) or 0):,.2f}"
                    acao_ex = str(r.get('acao', '') or '')[:20]
                    transicao = f"{r.get('status_anterior','') or ''} -> {r.get('status_novo','') or ''}"[:35]
                    usuario_ex = str(r.get('usuario', '') or 'importação')[:15]
                    pdf.cell(cols_ex[0][1], 6, data_oc,      1, 0, 'C', fill=fill_ex)
                    pdf.cell(cols_ex[1][1], 6, pagador_ex,   1, 0, 'L', fill=fill_ex)
                    pdf.cell(cols_ex[2][1], 6, nf_ex,        1, 0, 'C', fill=fill_ex)
                    pdf.cell(cols_ex[3][1], 6, venc_ex,      1, 0, 'C', fill=fill_ex)
                    pdf.cell(cols_ex[4][1], 6, valor_ex,     1, 0, 'R', fill=fill_ex)
                    pdf.cell(cols_ex[5][1], 6, acao_ex,      1, 0, 'C', fill=fill_ex)
                    pdf.cell(cols_ex[6][1], 6, transicao,    1, 0, 'L', fill=fill_ex)
                    pdf.cell(cols_ex[7][1], 6, usuario_ex,   1, 0, 'C', fill=fill_ex)
                    pdf.ln()
                    fill_ex = not fill_ex
            
            else:
                # Layout Premium Títulos financeiros (Todos, Aberto, Pagos, Cartório)
                pdf.set_fill_color(30, 80, 160)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font("Arial", 'B', 8)
                
                cols = [
                    ("Venc.", 18, 'C'),
                    ("Status", 18, 'C'),
                    ("Pagador / Cliente", 65, 'L'),
                    ("NF", 15, 'C'),
                    ("Princ. R$", 20, 'R'),
                    ("Juros R$", 15, 'R'),
                    ("Multa R$", 15, 'R'),
                    ("Total R$", 20, 'R'),
                    ("Atr.", 10, 'C'),
                    ("Usuário", 25, 'C'),
                    ("Data Ocorrência", 34, 'C') # Opcionalmente extrair auditoria se viável
                ]
                
                # Renderiza Header
                for c_name, c_width, c_align in cols:
                    pdf.cell(c_width, 7, c_name, border=1, fill=True, align='C')
                pdf.ln()
                
                total_princ = 0
                total_juros = 0
                total_multa = 0
                total_geral = 0
                
                pdf.set_font("Arial", '', 7)
                for _, r in df.iterrows():
                    calc = self.calcular_valores_cdc(r['valor'], r['vencimento'])
                    
                    # Vencimento (Verdinho se no futuro, vermelho se atrasado)
                    venc_br = self._formatar_data_br(str(r['vencimento']))
                    if calc.get('dias_atraso', 0) > 0:
                        pdf.set_text_color(180, 0, 0)
                    else:
                        pdf.set_text_color(0, 128, 0)
                    pdf.cell(cols[0][1], 6, venc_br, 1, 0, 'C')
                    
                    # Status
                    status = str(r['status'])
                    if status in ('Pago', 'Baixado'):
                        pdf.set_text_color(0, 150, 0)
                    elif status == 'Cartório':
                        pdf.set_text_color(200, 0, 0)
                    else:
                        pdf.set_text_color(0, 0, 0)
                    pdf.cell(cols[1][1], 6, status, 1, 0, 'C')
                    
                    # Cliente e NF
                    pdf.set_text_color(0, 0, 0)
                    cliente_str = str(r['pagador'])[:35]
                    pdf.cell(cols[2][1], 6, cliente_str, 1, 0, 'L')
                    pdf.cell(cols[3][1], 6, str(r['numero_nf']), 1, 0, 'C')
                    
                    # Valores
                    pdf.cell(cols[4][1], 6, f"{calc['principal']:,.2f}", 1, 0, 'R')
                    pdf.cell(cols[5][1], 6, f"{calc['juros']:,.2f}", 1, 0, 'R')
                    pdf.cell(cols[6][1], 6, f"{calc['multa']:,.2f}", 1, 0, 'R')
                    
                    # Total (Vermelho e Negrito)
                    pdf.set_text_color(200, 0, 0)
                    pdf.set_font("Arial", 'B', 7)
                    pdf.cell(cols[7][1], 6, f"{calc['total']:,.2f}", 1, 0, 'R')
                    
                    # Atraso e Info (Voltando ao normal)
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_font("Arial", '', 7)
                    pdf.cell(cols[8][1], 6, str(calc.get('dias_atraso', 0)), 1, 0, 'C')
                    
                    # Usuário e Data real da Auditoria
                    aud_user = str(r.get('aud_usuario') or 'importação')
                    aud_data_raw = str(r.get('aud_data') or '')
                    aud_data = self._formatar_data_br(aud_data_raw)
                    pdf.cell(cols[9][1], 6, aud_user[:14], 1, 0, 'C')
                    pdf.cell(cols[10][1], 6, aud_data, 1, 0, 'C')
                    
                    pdf.ln()
                    
                    total_princ += calc['principal']
                    total_juros += calc['juros']
                    total_multa += calc['multa']
                    total_geral += calc['total']
                
                # Linha de Totais da Tabela (Fundo Cinza)
                pdf.set_fill_color(220, 230, 240)
                pdf.set_font("Arial", 'B', 8)
                pdf.set_text_color(0, 0, 0)
                
                # Largura até a NF = 18 + 18 + 65 + 15 = 116
                pdf.cell(116, 7, f"TOTAIS ({len(df)} registros)", 1, 0, 'R', fill=True)
                pdf.cell(cols[4][1], 7, f"{total_princ:,.2f}", 1, 0, 'R', fill=True)
                pdf.cell(cols[5][1], 7, f"{total_juros:,.2f}", 1, 0, 'R', fill=True)
                pdf.cell(cols[6][1], 7, f"{total_multa:,.2f}", 1, 0, 'R', fill=True)
                
                pdf.set_text_color(200, 0, 0)
                pdf.cell(cols[7][1], 7, f"{total_geral:,.2f}", 1, 0, 'R', fill=True)
                
                pdf.set_text_color(0, 0, 0)
                resto_largura = cols[8][1] + cols[9][1] + cols[10][1]
                pdf.cell(resto_largura, 7, "", 1, 1, 'C', fill=True)

        # Remover acentos do nome do arquivo para evitar erro no FileResponse
        import unicodedata
        tipo_clean = ''.join(c for c in unicodedata.normalize('NFD', tipo_rel) if unicodedata.category(c) != 'Mn')
        tipo_clean = tipo_clean.replace(' ', '_')
        pdf_path = f"relatorio_{tipo_clean}_{datetime.now().strftime('%H%M%S')}.pdf"
        pdf.output(pdf_path)
        
        # Limpar logo temporária
        if logo_path and os.path.exists(logo_path):
            try:
                os.remove(logo_path)
            except:
                pass
                
        return pdf_path

    # Alias for backward compatibility se chamado via endpoint antigo
    gerar_relatorio_pdf = gerar_relatorio_pdf_cobrancas

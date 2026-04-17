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
        # Carrega configuraes da empresa para IA e Evolution
        self.config = carregar_configuracoes_db(cnpj_empresa)
        self.evo = EvolutionController(self.config, cnpj_empresa)

    def _humanizar_detalhes(self, det_raw):
        """Converte JSON tcnico de logs em texto amigvel."""
        if not det_raw: return ""
        if not isinstance(det_raw, str): return str(det_raw)
        
        det_raw = det_raw.strip()
        if not det_raw.startswith('{'):
            return det_raw # J  texto puro (ex: "Status alterado...")
            
        try:
            js = json.loads(det_raw)
            parts = []
            
            # 1. Canais
            wa = js.get('res_wa')
            em = js.get('res_email')
            
            if wa is not None:
                parts.append(f"WhatsApp: {'OK' if wa else 'Falha'}")
            if em is not None:
                parts.append(f"E-mail: {'OK' if em else 'Falha'}")
                
            # 2. Ttulos/NFs
            tits = js.get('titulos', [])
            if tits:
                nfs = []
                for t in tits:
                    if isinstance(t, dict):
                        nfs.append(str(t.get('numero_nf') or t.get('id') or ''))
                    else:
                        nfs.append(str(t))
                nf_str = ', '.join(filter(None, nfs))
                if nf_str:
                    parts.append(f"NF(s): {nf_str}")
                
            if not parts: return det_raw
            return " | ".join(parts)
        except:
            return det_raw

    def ja_foi_cobrado_hoje(self, nome_cliente):
        """
        Verifica se existe um log de envio com sucesso para o cliente no dia de hoje.
        """
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        hoje = datetime.now().strftime("%Y-%m-%d")
        try:
            # Busca qualquer log de sucesso hoje para este cliente
            c.execute("""
                SELECT count(*) FROM logs_envio 
                WHERE cliente = ? AND status = 'Sucesso' AND data_envio LIKE ?
            """, (nome_cliente, f"{hoje}%"))
            count = c.fetchone()[0]
            return count > 0
        except Exception as e:
            print(f"Erro ao verificar log de cobrana hoje: {e}")
            return False
        finally:
            conn.close()

    def _formatar_data_br(self, data_str, incluir_hora=False):
        if not data_str: return "-"
        try:
            # Tenta vrios formatos comuns
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
                if t['acao'] == 'Cobrar' and t['status'] in ('Aberto', 'Manter Aberto', 'Cartrio'):
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
        Calcula Multa (2% fixo) e Juros (1% ao ms pro-rata)
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
        
        has_cartorio = any(it.get('status') == 'Cartrio' for it in itens)
        dias_max_atraso = max([it.get('dias_atraso', 0) for it in itens]) if itens else 0
        restante_cartorio = prazo_cartorio_config - dias_max_atraso
        
        msg = f"{saudacao}, {contato}.\nSou a *Analu*, assistente financeira da *{self.config.get('empresa_nome', 'empresa')}*.\n\n"
        
        if has_cartorio:
            msg += f" *NOTIFICAÇÃO DE TÍTULO EM CARTÓRIO*\n\n"
            msg += f"Informamos que os débitos abaixo em nome de *{nome_cliente}* já se encontram em processo de **PROTESTO/CARTÓRIO** devido ao tempo de atraso.\n\n"
        else:
            msg += f"Gostaria de tratar sobre a regularização das suas pendências financeiras em aberto conosco.\n\n"
        
        # Avisos de prazo (apenas se não estiver em cartório ou se houver outros a vencer)
        if not has_cartorio:
            if restante_cartorio > 5:
                msg += f" *Aviso:* Faltam {restante_cartorio} dias para o início do processo de negativação/cartório.\n"
            elif 1 < restante_cartorio <= 5:
                msg += f" *ALERTA URGENTE:* Faltam apenas *{restante_cartorio} dias* para o envio automático deste débito ao *CARTÓRIO*.\n"
            elif restante_cartorio == 1:
                msg += f" *NOTIFICAÇÃO FINAL:* Seu título será instruído para *CARTÓRIO AMANHÃ*.\n"
            elif restante_cartorio == 0:
                msg += f" *PRAZO ESGOTADO:* O título atingiu o prazo limite e o processo de *CARTÓRIO* será iniciado HOJE.\n"
        
        if has_cartorio:
            msg += f" *Atenção:* Títulos em cartório geram restrições imediatas ao crédito e custos adicionais operacionais.\n"

        msg += f"\n *Detalhamento dos Títulos:*\n"
        
        for item in itens:
            msg += f" *NF {item['numero_nf']}* | Venc: {item['vencimento']} ({item['dias_atraso']} dias de atraso)\n"
            msg += f"    Principal: R$ {item['principal']:,.2f}\n"
            if item.get('multa', 0) > 0 or item.get('juros', 0) > 0:
                msg += f"    (+) Encargos: R$ {item['multa'] + item['juros']:,.2f}\n"
            msg += f"    Subtotal: R$ {item['total']:,.2f}\n\n"
            
        msg += f" *VALOR TOTAL ATUALIZADO:* R$ {total:,.2f}\n\n"
        
        if has_cartorio:
            msg += f" *INSTRUÇÕES DE REGULARIZAÇÃO:*\n"
            msg += f"1. O pagamento do valor acima deve ser feito à nossa empresa para quitação do débito.\n"
            msg += f"2. As **taxas de cartório** deverão ser pagas por sua empresa **diretamente ao tabelionato**.\n"
            msg += f"3. Após confirmarmos seu pagamento, emitiremos a **CARTA DE ANUÊNCIA** digital para que você possa baixar o protesto imediatamente.\n\n"
            msg += f"Gentileza tratar este assunto com a máxima prioridade.\n\n"
        else:
            msg += f"Gentileza entrar em contato para regularização.\n\n"
        
        return msg

    def buscar_e_zipar_documentos(self, cliente_nome, itens):
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
                    valor=[item.get('principal'), item.get('total'), item.get('valor')]
                )
                if path:
                    arquivos_temp.extend(path)
            except Exception as e:
                print(f"Erro ao buscar PDF para NF {item['numero_nf']}: {e}")
        
        if not arquivos_temp: return None, []
        
        import zipfile
        zip_name = f"faturas_{cliente_nome.replace(' ', '_')}_{datetime.now().strftime('%H%M%S')}.zip"
        try:
            with zipfile.ZipFile(zip_name, 'w') as z:
                for f in arquivos_temp:
                    if f and os.path.exists(f):
                        z.write(f, os.path.basename(f))
                    else:
                        print(f"   [AVISO] Arquivo nao encontrado para o ZIP: {f}")
            
            # Se o ZIP estiver vazio (nenhum arquivo existia de fato), deletamos e retornamos None
            if os.path.exists(zip_name) and os.path.getsize(zip_name) < 50: # Um ZIP vazio tem ~22 bytes
                os.remove(zip_name)
                return None, []
                
            return zip_name, arquivos_temp
        except Exception as e_zip:
            print(f"Erro ao gerar arquivo ZIP: {e_zip}")
            if os.path.exists(zip_name): os.remove(zip_name)
            return None, []

    def executar_processo_completo_cobranca(self, cliente_nome, msg, zip_path, itens, arquivos_temp, canais_selecionados=None, cli_direct=None):
        if canais_selecionados is None: canais_selecionados = ["whatsapp", "email"]
        res_wa = False
        res_email = False
        res_err = ""
        
        # 0. Busca dados do cliente (Prioriza objeto direto se enviado pelo worker)
        if cli_direct:
            cli = cli_direct
        else:
            cli_dados = listar_clientes_db(self.cnpj_empresa, nome_filtro=cliente_nome)
            if not cli_dados: 
                print(f" [ERR] Cliente no encontrado: {cliente_nome}")
                return {"whatsapp": False, "email": False}
            cli = cli_dados[0]
        
        # FAIL-SAFE: Re-verifica no BANCO se os ttulos ainda esto para 'Cobrar'
        # Isso evita Race Conditions se o usurio baixar o ttulo enquanto o rob est rodando
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        itens_validados = []
        for it in itens:
            tid = it.get('id')
            if not tid: continue
            row = c.execute("SELECT status, acao FROM titulos WHERE id=?", (tid,)).fetchone()
            if row and row[1] == 'Cobrar' and row[0] in ('Aberto', 'Manter Aberto', 'Cartrio'):
                itens_validados.append(it)
        conn.close()

        if not itens_validados:
            print(f" [FAIL-SAFE] Abortando envio para {cliente_nome}: Todos os ttulos foram baixados ou pausados recentemente.")
            return {"whatsapp": False, "email": False, "skipped": True}
        
        # Se alguns foram baixados mas outros no, atualizamos o contedo para no cobrar o que j foi pago
        itens = itens_validados
        
        # 1. Enviar WhatsApp via Evolution
        whatsapp_raw = cli.get('whatsapp')
        if whatsapp_raw and 'whatsapp' in canais_selecionados:
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

        if email_raw and smtp_srv and email_user and email_pass and 'email' in canais_selecionados:
            destinatarios = [e.strip() for e in email_raw.split(';') if e.strip()]
            try:
                for dest in destinatarios:
                    mail = MIMEMultipart()
                    mail['From'] = f"Financeiro <{email_user}>"
                    mail['To'] = dest
                    mail['Subject'] = f"Aviso de Cobrana - {cliente_nome}"
                    
                    corpo = f"Ol {cliente_nome},\n\n" + msg.replace("*", "")
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

    def cobrar_cliente_especifico(self, nome_cliente, canais_selecionados=None):
        if canais_selecionados is None: canais_selecionados = ["whatsapp", "email"]
        fila = self.agrupar_debitos_por_cliente()
        if nome_cliente not in fila:
            return {"success": False, "message": "Nenhuma pendncia para este cliente."}
        
        info = fila[nome_cliente]
        msg = self.gerar_mensagem_cobranca(nome_cliente, info['dados_cliente'], info['total'], info['itens'])
        zip_path, arquivos_temp = self.buscar_e_zipar_documentos(nome_cliente, info['itens'])
        res = self.executar_processo_completo_cobranca(nome_cliente, msg, zip_path, info['itens'], arquivos_temp, canais_selecionados=canais_selecionados)
        return {"success": True, "res": res}

    def cobrar_titulo_unico(self, id_titulo, canais_selecionados=None):
        if canais_selecionados is None: canais_selecionados = ["whatsapp", "email"]
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        c.execute("SELECT * FROM titulos WHERE id=?", (id_titulo,))
        row = c.fetchone()
        conn.close()
        if not row: return {"success": False, "message": "Ttulo no encontrado."}
        
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
        if not cli_dados: return {"success": False, "message": f"Cliente {tit['pagador']} no encontrado no CRM."}
        cli = cli_dados[0]
        
        msg = self.gerar_mensagem_cobranca(tit['pagador'], cli, tit['total'], [tit])
        zip_path, arquivos_temp = self.buscar_e_zipar_documentos(tit['pagador'], [tit])
        res = self.executar_processo_completo_cobranca(tit['pagador'], msg, zip_path, [tit], arquivos_temp, canais_selecionados=canais_selecionados)
        
        return {"success": True, "res": res}

    def prever_cobranca_coletiva(self):
        """
        Retorna uma lista de clientes que seriam cobrados e o resumo dos valores.
        """
        conn = conectar(self.cnpj_empresa)
        cursor = conn.cursor()
        # Seleciona ttulos elegveis para cobrana (mesmo que pausados individualmente, o motor pode v-los)
        # Sincronizado com agrupar_debitos_por_cliente
        cursor.execute("SELECT * FROM titulos WHERE status IN ('Aberto', 'Manter Aberto', 'Cartrio')")
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
        tipo_rel = filtros.get('tipo', 'Todos')
        cliente  = filtros.get('cliente')
        data_inicio = filtros.get('data_inicio')
        data_fim    = filtros.get('data_fim')
        
        conn = conectar(self.cnpj_empresa)
        conf = carregar_configuracoes_db(self.cnpj_empresa)
        empresa_nome = conf.get('empresa_nome', 'Credos System')

        df = pd.DataFrame()

        # Helper para construir filtros comuns
        def build_filters(col_data, col_cliente=None):
            where = []
            params = []
            if cliente and cliente != "Todos" and col_cliente:
                where.append(f"{col_cliente} = ?")
                params.append(cliente)
            if data_inicio:
                where.append(f"{col_data} >= ?")
                params.append(data_inicio + " 00:00:00")
            if data_fim:
                where.append(f"{col_data} <= ?")
                params.append(data_fim + " 23:59:59")
            
            where_str = " AND ".join(where)
            if where_str:
                where_str = " AND " + where_str
            return where_str, params

        try:
            if tipo_rel == "Cobrados":
                where_str, params = build_filters("data_envio", "cliente")
                query = f"""
                    SELECT data_envio as data_hora, cliente as pagador, tipo_envio as canal, 
                           status as resultado, detalhes as obs, usuario
                    FROM logs_envio
                    WHERE tipo_envio IN ('Email', 'WhatsApp', 'IA') {where_str}
                """
                df = pd.read_sql_query(query, conn, params=params)

            elif tipo_rel == "Baixados":
                where_str, params = build_filters("a.data_hora", "t.pagador")
                query = f"""
                    SELECT a.data_hora, t.pagador, t.numero_nf, t.valor, a.usuario, a.status_novo as status
                    FROM auditoria_titulos a
                    JOIN titulos t ON a.titulo_id = t.id
                    WHERE a.status_novo IN ('Pago', 'Baixado') {where_str}
                """
                df = pd.read_sql_query(query, conn, params=params)

            elif tipo_rel == "Cancelados":
                where_str, params = build_filters("a.data_hora", "t.pagador")
                query = f"""
                    SELECT a.data_hora, t.pagador, t.numero_nf, t.valor, a.usuario
                    FROM auditoria_titulos a
                    JOIN titulos t ON a.titulo_id = t.id
                    WHERE a.status_novo = 'Cancelado' {where_str}
                """
                df = pd.read_sql_query(query, conn, params=params)

            elif tipo_rel == "Excluidos":
                where_str, params = build_filters("data_envio", "cliente")
                query = f"""
                    SELECT data_envio as data_hora, cliente as pagador, detalhes as obs, usuario
                    FROM logs_envio
                    WHERE tipo_envio = 'Excluso CRM' {where_str}
                """
                df = pd.read_sql_query(query, conn, params=params)

            elif tipo_rel == "Solicitado_Cartorio":
                where_str, params = build_filters("cj.data_execucao", "t.pagador")
                query = f"""
                    SELECT cj.data_execucao as data_hora, t.pagador, t.numero_nf, t.valor, cj.status_automacao as status
                    FROM cartorio_jobs cj
                    JOIN titulos t ON cj.titulo_id = t.id
                    WHERE cj.intervacao_manual = 1 {where_str}
                """
                df = pd.read_sql_query(query, conn, params=params)

            elif tipo_rel == "Enviado_Cartorio":
                where_str, params = build_filters("cj.data_execucao", "t.pagador")
                query = f"""
                    SELECT cj.data_execucao as data_hora, t.pagador, t.numero_nf, t.valor, cj.status_automacao as status
                    FROM cartorio_jobs cj
                    JOIN titulos t ON cj.titulo_id = t.id
                    WHERE cj.intervacao_manual = 0 {where_str}
                """
                df = pd.read_sql_query(query, conn, params=params)
                
            elif tipo_rel == "Todos":
                # Fallback: Combina logs de envio se tipo for Todos
                where_str, params = build_filters("data_envio", "cliente")
                query = f"SELECT data_envio as data_hora, cliente as pagador, 'Atividade' as canal, status as resultado, detalhes as obs, usuario FROM logs_envio WHERE 1=1 {where_str}"
                df = pd.read_sql_query(query, conn, params=params)

        except Exception as e:
            print(f"Erro ao consultar dados para relatrio: {e}")
            df = pd.DataFrame()
        finally:
            conn.close()

        # --- GERAO DO PDF ---
        pdf = FPDF(orientation='L', unit='mm', format='A4')
        pdf.add_page()
        
        # Logo Credos
        credos_logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logo.png')
        if os.path.exists(credos_logo):
            try: pdf.image(credos_logo, 10, 10, h=10)
            except: pass

        # Cabealho
        pdf.set_font("Arial", 'B', 14)
        pdf.set_y(15)
        pdf.cell(0, 6, str(empresa_nome).upper(), 0, 1, 'C')
        
        titulos_map = {
            "Cobrados": "TÍTULOS COBRADOS (OPERADOR & ANALU)",
            "Baixados": "RELATÓRIO DE TÍTULOS BAIXADOS / PAGOS",
            "Cancelados": "RELATÓRIO DE TÍTULOS CANCELADOS",
            "Excluidos": "HISTÓRICO DE EXCLUSÕES NO CRM",
            "Solicitado_Cartorio": "TÍTULOS SOLICITADOS PARA CARTÓRIO (OPERADOR)",
            "Enviado_Cartorio": "TÍTULOS ENVIADOS PARA CARTÓRIO (ANALU IA)"
        }
        pdf.set_font("Arial", 'B', 11)
        pdf.cell(0, 6, titulos_map.get(tipo_rel, "RELATÓRIO DE ATIVIDADES"), 0, 1, 'C')
        
        pdf.set_font("Arial", '', 8)
        pdf.cell(0, 5, f"Período: {data_inicio or 'Início'} até {data_fim or 'Hoje'} | Emissão: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'R')
        pdf.ln(5)

        if df.empty:
            pdf.ln(20)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, "Nenhum registro encontrado para este relatório.", 0, 1, 'C')
        else:
            # Seleo de Colunas
            if tipo_rel == "Cobrados":
                cols = [("Data/Hora", 35), ("Cliente", 65), ("Canal", 25), ("Status", 25), ("USUÁRIO", 30), ("OCORRÊNCIA", 100)]
            elif tipo_rel in ("Baixados", "Cancelados", "Solicitado_Cartorio", "Enviado_Cartorio"):
                cols = [("Data/Hora", 40), ("Cliente", 90), ("NF", 30), ("Valor", 40), ("Complemento", 80)]
            else: # Excluidos / Todos
                cols = [("Data/Hora", 40), ("Cliente", 90), ("USUÁRIO", 40), ("OCORRÊNCIA", 110)]

            # Cabealho da Tabela
            pdf.set_fill_color(30, 80, 160)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Arial", 'B', 8)
            for name, width in cols:
                pdf.cell(width, 7, name, 1, 0, 'C', fill=True)
            pdf.ln()

            # Linhas da Tabela
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", '', 7)
            fill = False
            for _, r in df.iterrows():
                pdf.set_fill_color(245, 245, 250) if fill else pdf.set_fill_color(255, 255, 255)
                h_data = self._formatar_data_br(str(r.get('data_hora', '')), incluir_hora=True)
                
                if tipo_rel == "Cobrados":
                    pdf.cell(cols[0][1], 6, h_data, 1, 0, 'C', fill=fill)
                    pdf.cell(cols[1][1], 6, str(r.get('pagador', ''))[:45], 1, 0, 'L', fill=fill)
                    pdf.cell(cols[2][1], 6, str(r.get('canal', '')), 1, 0, 'C', fill=fill)
                    pdf.cell(cols[3][1], 6, str(r.get('resultado', '')), 1, 0, 'C', fill=fill)
                    pdf.cell(cols[4][1], 6, str(r.get('usuario', '') or 'Analu'), 1, 0, 'C', fill=fill)
                    det = self._humanizar_detalhes(str(r.get('obs', ''))).replace('\n', ' ')
                    pdf.cell(cols[5][1], 6, det[:75], 1, 0, 'L', fill=fill)
                
                elif tipo_rel in ("Baixados", "Cancelados", "Solicitado_Cartorio", "Enviado_Cartorio"):
                    pdf.cell(cols[0][1], 6, h_data, 1, 0, 'C', fill=fill)
                    pdf.cell(cols[1][1], 6, str(r.get('pagador', ''))[:60], 1, 0, 'L', fill=fill)
                    pdf.cell(cols[2][1], 6, str(r.get('numero_nf', '')), 1, 0, 'C', fill=fill)
                    pdf.cell(cols[3][1], 6, f"R$ {float(r.get('valor', 0)):,.2f}", 1, 0, 'R', fill=fill)
                    extra = str(r.get('usuario', '') or r.get('status', ''))
                    pdf.cell(cols[4][1], 6, extra[:60], 1, 0, 'L', fill=fill)

                else: # Excluidos / Todos
                    pdf.cell(cols[0][1], 6, h_data, 1, 0, 'C', fill=fill)
                    pdf.cell(cols[1][1], 6, str(r.get('pagador', ''))[:60], 1, 0, 'L', fill=fill)
                    pdf.cell(cols[2][1], 6, str(r.get('usuario', '') or 'Operador'), 1, 0, 'C', fill=fill)
                    det = self._humanizar_detalhes(str(r.get('obs', ''))).replace('\n', ' ')
                    pdf.cell(cols[3][1], 6, det[:105], 1, 0, 'L', fill=fill)

                pdf.ln()
                fill = not fill

        # Retorno do PDF em bytes
        return pdf.output(dest='S').encode('latin-1')

    # Alias for backward compatibility
    gerar_relatorio_pdf = gerar_relatorio_pdf_cobrancas

    def gerar_relatorio_pdf_operacao_diaria(self, data_alvo=None):
        """Gera um PDF sumarizado das cobrancas do dia para enviar ao grupo da diretoria."""
        if not data_alvo:
            data_alvo = datetime.now().strftime("%Y-%m-%d")
            
        conn = conectar(self.cnpj_empresa)
        conf = carregar_configuracoes_db(self.cnpj_empresa)
        empresa_nome = conf.get('empresa_nome', 'Credos System')
        
        pdf = FPDF()
        pdf.add_page("P") # Portrait
        
        # --- CABEÇALHO ---
        pdf.set_fill_color(0, 51, 102) # Dark Blue
        pdf.rect(0, 0, 210, 40, 'F')
        
        credos_logo = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logo.png')
        if os.path.exists(credos_logo):
            try: pdf.image(credos_logo, 10, 8, h=12)
            except: pass
            
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", 'B', 16)
        pdf.set_y(10)
        pdf.cell(0, 8, str(empresa_nome).upper(), 0, 1, 'R')
        pdf.set_font("Arial", '', 10)
        pdf.cell(0, 6, f"RELATÓRIO EXECUTIVO DE OPERAÇÃO DIÁRIA", 0, 1, 'R')
        
        data_br = datetime.strptime(data_alvo, "%Y-%m-%d").strftime("%d/%m/%Y")
        pdf.set_font("Arial", 'I', 9)
        pdf.cell(0, 5, f"Data da Operação: {data_br} | Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'R')
        
        # --- RESUMO EXECUTIVO ---
        pdf.set_y(45)
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 8, "RESUMO DE PERFORMANCE", 0, 1, 'L')
        pdf.line(10, 53, 200, 53)
        pdf.ln(2)
        
        # Correção da Query: Busca flexível por tipos de envio para incluir 'WhatsApp/Email'
        query = f"SELECT cliente, tipo_envio, status, detalhes, usuario FROM logs_envio WHERE data_envio LIKE '{data_alvo}%' AND (tipo_envio LIKE '%Email%' OR tipo_envio LIKE '%WhatsApp%' OR tipo_envio LIKE '%IA%')"
        
        try:
            df = pd.read_sql_query(query, conn)
            
            total_envios = len(df)
            sucessos = len(df[df['status'] == 'Sucesso'])
            falhas = total_envios - sucessos
            taxa = (sucessos / total_envios * 100) if total_envios > 0 else 0
            
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(60, 10, f"TOTAL DE ACIONAMENTOS", 1, 0, 'C')
            pdf.cell(60, 10, f"ENTREGUES COM SUCESSO", 1, 0, 'C')
            pdf.cell(70, 10, f"TAXA DE EFICIÊNCIA", 1, 1, 'C')
            
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(60, 12, f"{total_envios}", 1, 0, 'C')
            pdf.set_text_color(0, 128, 0) if sucessos > 0 else None
            pdf.cell(60, 12, f"{sucessos}", 1, 0, 'C')
            pdf.set_text_color(0, 0, 0)
            pdf.cell(70, 12, f"{taxa:.1f}%", 1, 1, 'C')
            
            pdf.ln(8)
            
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 8, "DETALHAMENTO POR CLIENTE", 0, 1, 'L')
            pdf.ln(2)
            
            if total_envios > 0:
                pdf.set_fill_color(230, 230, 230)
                pdf.set_font("Arial", 'B', 8)
                pdf.cell(60, 7, " CLIENTE", 1, 0, 'L', fill=True)
                pdf.cell(25, 7, "CANAL", 1, 0, 'C', fill=True)
                pdf.cell(25, 7, "STATUS", 1, 0, 'C', fill=True)
                pdf.cell(80, 7, "DETALHES / NFS", 1, 1, 'L', fill=True)
                
                pdf.set_font("Arial", '', 7)
                fill = False
                for _, r in df.iterrows():
                    cliente = str(r.get('cliente', ''))[:35]
                    canal = str(r.get('tipo_envio', ''))
                    status = str(r.get('status', ''))
                    det_raw = str(r.get('detalhes', ''))
                    det = self._humanizar_detalhes(det_raw).replace('\n', ' ')
                    
                    if status == "Falha": pdf.set_text_color(200, 0, 0)
                    else: pdf.set_text_color(0, 0, 0)
                    
                    pdf.cell(60, 6, f" {cliente}", 1, 0, 'L', fill=fill)
                    pdf.cell(25, 6, canal, 1, 0, 'C', fill=fill)
                    pdf.cell(25, 6, status, 1, 0, 'C', fill=fill)
                    pdf.cell(80, 6, f" {det[:60]}", 1, 1, 'L', fill=fill)
                    fill = not fill
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.set_font("Arial", 'I', 10)
                pdf.cell(0, 10, "Nenhuma atividade financeira registrada hoje.", 0, 1, 'C')
        except Exception as e:
            pdf.set_font("Arial", 'B', 10)
            pdf.set_text_color(255, 0, 0)
            pdf.cell(0, 10, f"Erro ao consolidar dados: {e}", 0, 1, 'L')
        finally:
            conn.close()
            
        pdf.set_y(-20)
        pdf.set_font("Arial", 'I', 8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 10, "Credos System - Analu AI | Tecnologia Avançada de Cobrança", 0, 0, 'C')
            
        pdf_path = f"temp_data/relatorio_diario_{self.cnpj_empresa}_{datetime.now().strftime('%H%M')}.pdf"
        os.makedirs("temp_data", exist_ok=True)
        pdf.output(pdf_path)
        return pdf_path

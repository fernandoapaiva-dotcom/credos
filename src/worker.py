from src.database import listar_todos_agendamentos_ativos, conectar, is_global_halt_active, get_global_jid
from src.manager import Manager
from src.rag_negotiator import RAGNegotiator
from src.cartorio_automation import CartorioAutomation
from src.evolution_controller import EvolutionController
import json
import asyncio
from datetime import datetime
import time

import builtins
import holidays
_original_print = builtins.print
def safe_print(*args, **kwargs):
    try:
        _original_print(*args, **kwargs)
    except Exception:
        safe_args = [str(a).encode('utf-8', 'replace').decode('ascii', 'replace') for a in args]
        _original_print(*safe_args, **kwargs)
builtins.print = safe_print

def disparar_cobranca_automatica(forcar_execucao=False, cnpj_filtro=None, canais_selecionados=None):
    """
    Motor de Cobrança:
    1. Varre agendamentos ativos.
    2. Verifica se hoje é dia de cobrança.
    3. Gera mensagens (com aviso de 10 dias se necessário).
    4. Envia e loga.
    """
    print(f"\\n🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Iniciando Motor de Cobrança...")
    
    if is_global_halt_active():
        print("🛑 [EMERGÊNCIA] Robô pausado pelo botão de pânico global. Abortando execução.")
        return 0
    
    # Verifica promessas vencidas
    verificar_acordos_vencidos(cnpj_filtro)
    
    # Roda as negociações IA também se for uma execução geral
    if not cnpj_filtro:
        disparar_negociacoes_ia()

    # 1. Busca configurações ativas
    agendamentos = listar_todos_agendamentos_ativos()
    
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]
        if not agendamentos:
            # Se não tem agendamento ativo mas queremos forçar, criamos um mock do agendamento
            # para que o loop abaixo funcione com o Manager
            agendamentos = [{'empresa_dona_cnpj': cnpj_filtro}]
            forcar_execucao = True

    if not agendamentos:
        print("zzz Nenhuma automação ativa no banco de dados.")
        return 0

    total_envios = 0

    for ag in agendamentos:
        cnpj_empresa = ag['empresa_dona_cnpj']
        
        # Verifica se hoje é dia de executar (se não for forçado manualmente)
        if not forcar_execucao:
            hoje_semana = datetime.now().weekday()
            hora_atual = datetime.now().strftime("%H:%M")
            
            mapping_dias = {'Segunda':0, 'Terça':1, 'Quarta':2, 'Quinta':3, 'Sexta':4, 'Sábado':5, 'Domingo':6}
            
            try:
                raw_dias = ag.get('dias_ui', '[]')
                if '[' in raw_dias:
                    dias_nomes = json.loads(raw_dias)
                    dias_permitidos = [mapping_dias.get(d) for d in dias_nomes if mapping_dias.get(d) is not None]
                else:
                    dias_permitidos = [int(d) for d in raw_dias.split(",") if d.strip()]
            except:
                dias_permitidos = []
            
            if hoje_semana not in dias_permitidos:
                print(f"⏩ Pulando {cnpj_empresa}: Hoje não está na agenda.")
                continue
                
            pular_feriados = ag.get('pular_feriados', 1)
            horario_esperado = ag.get('horario_envio', '09:00')
            try:
                agora_dt = datetime.now()
                # --- CHECK DE FERIADO NACIONAL ---
                if pular_feriados == 1 and agora_dt.date() in holidays.BR():
                    print(f"⏩ Pulando {cnpj_empresa}: Hoje é feriado nacional (regra ativa).")
                    continue

                hora_esp_dt = datetime.strptime(horario_esperado, "%H:%M").replace(year=agora_dt.year, month=agora_dt.month, day=agora_dt.day)
                atraso_segundos = (agora_dt - hora_esp_dt).total_seconds()
                ja_executou_hoje = ag.get('ultima_execucao', '') == agora_dt.strftime("%Y-%m-%d")

                if ja_executou_hoje:
                    continue

                if not (0 <= atraso_segundos <= 900):
                    continue
                
                print(f"✅ Iniciar Cobrança: Horário previsto {horario_esperado}, Janela OK.")
            except:
                if datetime.now().strftime("%H:%M") != horario_esperado:
                    continue

        # --- EXECUÇÃO DO CICLO ---
        try:
            print(f"🏢 Processando Empresa CNPJ: {cnpj_empresa}...")
            mgr = Manager(cnpj_empresa)
            fila = mgr.agrupar_debitos_por_cliente()
            
            if fila:
                for cliente_nome, info in fila.items():
                    try:
                        print(f"   📦 Preparando: {cliente_nome}...")
                        msg = mgr.gerar_mensagem_cobranca(cliente_nome, info['dados_cliente'], info['total'], info['itens'])
                        zip_path, arquivos_temp = mgr.buscar_e_zipar_documentos(cliente_nome, info['itens'])
                        res = mgr.executar_processo_completo_cobranca(
                            cliente_nome, msg, zip_path, info['itens'], arquivos_temp,
                            canais_selecionados=canais_selecionados, cli_direct=info['dados_cliente']
                        )
                        if res['email'] or res['whatsapp']:
                            total_envios += 1
                        time.sleep(10)
                    except Exception as e_cli:
                        print(f"   ❌ Erro no cliente {cliente_nome}: {e_cli}")
            else:
                print(f"   ✅ Nenhuma pendência 'Cobrar' encontrada para hoje.")

            # --- ENVIO DO RELATÓRIO PDF DIÁRIO ---
            # Roda sempre que o ciclo é processado (janela de horário bate)
            if not forcar_execucao:
                marcar_execucao_hoje(cnpj_empresa)

            # --- ENVIO DO RELATÓRIO PDF DIÁRIO ---
            try:
                grupo_jid = mgr.config.get('grupo_relatorio_jid')
                if not grupo_jid:
                    conn_c = conectar()
                    g_res = conn_c.cursor().execute("SELECT grupo_relatorio_jid FROM config_global WHERE id = 1").fetchone()
                    conn_c.close()
                    if g_res and g_res[0]: grupo_jid = g_res[0]

                if grupo_jid:
                    pdf_path = mgr.gerar_relatorio_pdf_operacao_diaria()
                    pdf_abs = os.path.abspath(pdf_path)
                    if os.path.exists(pdf_abs):
                        nome_unidade = mgr.config.get('empresa_nome', cnpj_empresa)
                        total_cob = total_envios
                        mgr.evo.enviar_mensagem_texto(
                            grupo_jid,
                            f"📊 *Relatório Diário — {nome_unidade}*\n"
                            f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
                            f"✅ Acionamentos com sucesso hoje: *{total_cob}*\n\n"
                            f"Segue o PDF com o detalhamento completo dos clientes cobrados, títulos e valores:"
                        )
                        mgr.evo.enviar_midia(grupo_jid, pdf_abs)
                        print(f"   📊 Relatório diário de {cnpj_empresa} enviado ao grupo com sucesso.")
                        try: os.remove(pdf_abs)
                        except: pass
                    else:
                        print(f"   ⚠️ PDF não encontrado em: {pdf_abs}")
                else:
                    print(f"   ℹ️ Grupo de relatório não configurado para {cnpj_empresa}. Pulando envio.")
            except Exception as er_rel:
                print(f"   ❌ Erro ao enviar relatório diário para {cnpj_empresa}: {er_rel}")

        except Exception as e_emp:
            error_msg = f"❌ Erro crítico ao processar empresa {cnpj_empresa}: {e_emp}"
            print(error_msg)
            try:
                temp_mgr = Manager(cnpj_empresa)
                aviso_sentinela = f"⚠️ ALERTA DE SISTEMA (ANALU SENTINELA)\n\nFernando, detectamos uma falha crítica no lote de hoje da empresa {cnpj_empresa}.\nErro: {str(e_emp)}"
                operador_email = temp_mgr.config.get('fin_mail_user')
                if operador_email:
                    # (Lógica de envio de email omitida para brevidade ou mantida conforme original se necessário)
                    pass
            except: pass

    print(f"🏁 Ciclo Finalizado. Total de envios: {total_envios}")
    return total_envios

def marcar_execucao_hoje(cnpj):
    """Atualiza o banco para registrar que a cobrança já rodou hoje."""
    conn = conectar(cnpj)
    c = conn.cursor()
    hoje = datetime.now().strftime("%Y-%m-%d")
    c.execute("UPDATE agendamento SET ultima_execucao = ?", (hoje,))
    conn.commit()
    conn.close()

def disparar_negociacoes_ia(cnpj_filtro=None, forcar_hoje=False):
    """
    Motor de Negociação RAG — Ciclo Diário de 20 Dias:
    - Dia 1 a 20: envia mensagem diária com tom crescente
    - Detecta pagamento → para cobranças
    - Dia 20+ sem pagamento → notifica operador para confirmar cartório
    """
    print(f"🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Verificando Negociações IA (Ciclo 20 dias)...")
    
    if is_global_halt_active():
        print("🛑 [EMERGÊNCIA] IA de Negociação pausada pelo botão de pânico global.")
        return
    
    from src.evolution_controller import EvolutionController
    from src.database import carregar_configuracoes_db

    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]
    
    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        # Verifica se hoje e este horário são permitidos
        hoje_semana = datetime.now().weekday()
        hora_atual = datetime.now().strftime("%H:%M")
        
        import json
        mapping_dias = {'Segunda':0, 'Terça':1, 'Quarta':2, 'Quinta':3, 'Sexta':4, 'Sábado':5, 'Domingo':6}
        try:
            raw_dias = ag.get('dias_ui', '[]')
            if '[' in raw_dias:
                dias_nomes = json.loads(raw_dias)
                dias_permitidos = [mapping_dias.get(d) for d in dias_nomes if mapping_dias.get(d) is not None]
            else:
                dias_permitidos = [int(d) for d in raw_dias.split(",") if d.strip()]
        except: dias_permitidos = []

        if not forcar_hoje:
            if hoje_semana not in dias_permitidos:
                continue
                
            pular_feriados = ag.get('pular_feriados', 1)
            if pular_feriados == 1 and datetime.now().date() in holidays.BR():
                print(f"⏩ Pulando IA {cnpj}: Hoje é feriado nacional.")
                continue
                
        # Verifica se está dentro da janela de 10 minutos do horário configurado
        if not forcar_hoje:
            horario_esperado = ag.get('horario_envio', '09:00')
            try:
                ref_dt = datetime.strptime(horario_esperado, "%H:%M")
                now_dt = datetime.strptime(hora_atual, "%H:%M")
                diff_min = (now_dt - ref_dt).total_seconds() / 60
                
                if not (0 <= diff_min <= 10):
                    continue
            except:
                if hora_atual != horario_esperado:
                    continue


        try:
            mgr = Manager(cnpj)
            rag = RAGNegotiator(cnpj)
            config = carregar_configuracoes_db(cnpj)
            config['empresa_cnpj'] = cnpj
            evo = EvolutionController(config=config, nome_empresa_cliente=cnpj)
            operador_num = config.get('operador_whatsapp')
            # JID do grupo de relatório da empresa (para alertas Admin — Item 6, 11)
            grupo_jid_empresa = config.get('grupo_relatorio_jid')


            fila = mgr.agrupar_debitos_por_cliente()
            for cliente, info in fila.items():
                if mgr.ja_foi_cobrado_hoje(cliente):
                    print(f"   ⏭️ {cliente}: Já recebeu cobrança hoje. Pulando ciclo IA.")
                    continue

                itens_elegíveis = [it for it in info['itens'] if it.get('dias_atraso', 0) >= 1]
                if not itens_elegíveis:
                    continue

                max_dias = max(it['dias_atraso'] for it in itens_elegíveis)
                whatsapp = info['dados_cliente'].get('whatsapp', '')
                if not whatsapp:
                    print(f"   ⏭️ {cliente}: Sem número de WhatsApp cadastrado. Pulando.")
                    continue

                numeros = [n.strip() for n in whatsapp.split(';') if n.strip()]
                if not numeros:
                    print(f"   ⏭️ {cliente}: Lista de números vazia. Pulando.")
                    continue

                conn = conectar(cnpj)
                conn.row_factory = __import__('sqlite3').Row

                # Busca ou cria sessão de cobrança para este cliente
                sessao = conn.cursor().execute(
                    "SELECT * FROM webhook_sessions WHERE cliente_nome=? ORDER BY id DESC LIMIT 1",
                    (cliente,)
                ).fetchone()

                if sessao:
                    sessao = dict(sessao)
                    dia_atual = sessao.get('dia_cobranca', 1)
                else:
                    # Cria sessão inicial
                    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    conn.cursor().execute(
                        "INSERT INTO webhook_sessions (numero_whatsapp, cliente_nome, dia_cobranca, estado, ultima_interacao) VALUES (?,?,1,'aguardando_resposta',?)",
                        (numeros[0], cliente, agora)
                    )
                    conn.commit()
                    dia_atual = 1
                    sessao = {'id': conn.cursor().lastrowid, 'estado': 'aguardando_resposta'}

                conn.close()

                # Pula se o cliente já mandou comprovante, está com acordo ativo ou fluxo pausado pelo operador
                estados_pausa = ('comprovante_recebido', 'aguardando_comprovante', 'acordo_aprovado',
                                 'verificando_pagamento', 'concluido', 'pausado_pelo_operador')
                if sessao.get('estado') in estados_pausa:
                    print(f"   ⏭️ {cliente}: fluxo suspenso (estado: {sessao.get('estado')}).")
                    continue

                # ─── Verificar se título foi pago ────────────────────
                conn2 = conectar(cnpj)
                todos_pagos = conn2.cursor().execute(
                    "SELECT count(*) FROM titulos WHERE pagador=? AND status='Aberto' AND acao='Cobrar'",
                    (cliente,)
                ).fetchone()[0] == 0
                conn2.close()

                if todos_pagos:
                    print(f"   ✅ {cliente}: todos os títulos quitados. Parando cobranças.")
                    continue

                # ─── Dia 19: Último Aviso ao Cliente ────────────────
                if dia_atual == 19:
                    msg_ultimo_aviso = (
                        f"*Analu (Assistente Virtual) Diz:*\n\n"
                        f"Olá, {cliente.split()[0]}! Preciso te avisar sobre uma situação importante. "
                        f"Amanhã se encerra o prazo de negociação do seu débito de *R$ {info.get('total', 0):,.2f}*. "
                        f"Caso não haja pagamento ou acordo, os títulos seguirão automaticamente para *protesto em cartório*. "
                        f"Se quiser evitar isso, entre em contato agora mesmo que a gente resolve! 🤝"
                    )
                    for num in numeros:
                        evo.enviar_mensagem_texto(num, msg_ultimo_aviso)
                    print(f"   ⚠️ Aviso de D-1 cartório enviado para {cliente}.")

                # ─── Dia 20+: Avisa cliente e Notifica operador ──────
                if dia_atual >= 20:
                    # 1. Avisa o cliente que o título vai a cartório
                    msg_cliente_cartorio = (
                        f"*Analu (Assistente Virtual) Diz:*\n\n"
                        f"Olá, {cliente.split()[0]}. Infelizmente, o prazo de negociação de 20 dias se encerrou "
                        f"sem que o débito de *R$ {info.get('total', 0):,.2f}* fosse regularizado. "
                        f"Por este motivo, os títulos em aberto serão encaminhados para *protesto em cartório* hoje. "
                        f"Caso queira evitar o protesto, entre em contato imediatamente com o nosso financeiro."
                    )
                    for num in numeros:
                        evo.enviar_mensagem_texto(num, msg_cliente_cartorio)

                # 2. Notifica o operador individual e o GRUPO ADMIN (Item 6)
                if operador_num or grupo_jid_empresa:
                    total_fmt = f"R$ {info.get('total', 0):,.2f}"
                    nomes_nfs = ", ".join([f"NF {it['numero_nf']}" for it in itens_elegíveis])
                    msg_op = (
                        f"⚠️ *ALERTA DE CARTÓRIO*\n"
                        f"Empresa: *{config.get('empresa_nome', cnpj)}*\n"
                        f"Cliente: *{cliente}*\n"
                        f"Débito: *{total_fmt}* (vencido há {max_dias} dias)\n"
                        f"Títulos: {nomes_nfs}\n\n"
                        f"O prazo de 20 dias se encerrou. O cliente já foi avisado.\n"
                        f"Confirma o envio para protesto?\n\n"
                        f"✅ CARTÓRIO_SIM_{cnpj}_{cliente.replace(' ', '_')[:20]}\n"
                        f"❌ CARTÓRIO_NAO — para manter em aberto mais tempo"
                    )
                    if operador_num:
                        evo.enviar_mensagem_texto(operador_num, msg_op)
                        print(f"   📋 Operador notificado sobre cartório de {cliente}.")
                    # Notifica também o grupo Admin (Item 6)
                    if grupo_jid_empresa:
                        evo.enviar_mensagem_texto(grupo_jid_empresa, msg_op)
                        print(f"   📊 Grupo Admin notificado sobre cartório de {cliente}.")
                continue

                # ─── Dias 1-19: Enviar mensagem IA ──────────────────
                # Verifica se já enviamos hoje (nas últimas 20h)
                conn3 = conectar(cnpj)
                enviou_hoje = conn3.cursor().execute(
                    "SELECT count(*) FROM negociacoes WHERE cliente=? AND criado_em > datetime('now', '-20 hours')",
                    (cliente,)
                ).fetchone()[0] > 0
                conn3.close()

                if enviou_hoje:
                    print(f"   ⏩ {cliente}: mensagem IA já enviada hoje.")
                    continue

                print(f"   🤖 Dia {dia_atual}/20 — Gerando mensagem IA para {cliente}...")
                info_debito = {'total': sum(it.get('total', 0) for it in itens_elegíveis), 'itens': itens_elegíveis}
                
                # Extrai o histórico da sessão para a IA ter memória
                history_list = []
                try:
                    if sessao.get('history_json'):
                        history_list = json.loads(sessao['history_json'])
                except: pass

                msg_ia, erro_ia = rag.gerar_proposta_ia(cliente, info_debito, dia_numero=dia_atual, history_list=history_list)

                if erro_ia:
                    error_report = (
                        f"❌ *FALHA NA IA - Analu*\n"
                        f"Empresa: {cnpj}\n"
                        f"Cliente: {cliente}\n"
                        f"Erro: {erro_ia}\n\n"
                        f"⚠️ A mensagem de cobrança NÃO foi enviada ao cliente para evitar spam de erro técnico."
                    )
                    print(f"   ⚠️ Erro IA para {cliente}: {erro_ia}")
                    # Notifica grupo global de erros/relatórios se existir
                    jid_global = get_global_jid()
                    if jid_global:
                        try:
                            evo.enviar_mensagem_texto(jid_global, error_report)
                        except: pass
                    continue

                for num in numeros:
                    evo.enviar_mensagem_texto(num, msg_ia)
                
                # Envio opcional de documentos (ZIP) durante o ciclo IA - Mesma regra da Analu (XML/Boleto/NF)
                try:
                    zip_path, arquivos_temp = mgr.buscar_e_zipar_documentos(cliente, info_debito['itens'])
                    if zip_path:
                        for num in numeros:
                            evo.enviar_midia(num, zip_path)
                        # Cleanup
                        if os.path.exists(zip_path): os.remove(zip_path)
                        for f in arquivos_temp:
                            if os.path.exists(f): os.remove(f)
                except Exception as e_zip:
                    print(f"   ⚠️ [ZIP IA] Erro ao anexar documentos para {cliente}: {e_zip}")

                # Avança o dia de cobrança
                conn4 = conectar(cnpj)
                conn4.cursor().execute(
                    "UPDATE webhook_sessions SET dia_cobranca=?, ultima_mensagem_enviada=?, ultima_interacao=? WHERE id=?",
                    (dia_atual + 1, msg_ia, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sessao['id'])
                )
                conn4.commit()
                conn4.close()

                time.sleep(5)
                
            # --- ALERTA DE TÍTULOS SEM DOCUMENTOS (Item 11) ---
            try:
                conn_sd = conectar(cnpj)
                titulos_sem_doc = conn_sd.cursor().execute(
                    "SELECT t.pagador, t.numero_nf, t.vencimento, t.valor, c.cnpj as cnpj_cliente "
                    "FROM titulos t LEFT JOIN clientes c ON trim(c.nome)=trim(t.pagador) "
                    "WHERE t.status='Aberto' AND t.acao='Cobrar'"
                ).fetchall()
                conn_sd.close()
                
                alertas_sem_doc = []
                for row in titulos_sem_doc:
                    nf = str(row[1] or '').lstrip('0').strip()
                    conn_chk = conectar(cnpj)
                    tem_doc = conn_chk.cursor().execute(
                        "SELECT id FROM documentos_fiscais WHERE num_nf=? OR num_nf LIKE ? LIMIT 1",
                        (nf, f'%{nf}%')
                    ).fetchone()
                    conn_chk.close()
                    if not tem_doc:
                        alertas_sem_doc.append(row)
                
                if alertas_sem_doc and grupo_jid_empresa:
                    linhas = [f"🔴 {r[0]} | NF {r[1]} | CNPJ: {r[4] or 'N/A'} | Venc: {r[2]}" for r in alertas_sem_doc[:10]]
                    msg_sem_doc = (
                        f"🚨 *ALERTA: TÍTULOS SEM DOCUMENTOS*\n"
                        f"Empresa: {config.get('empresa_nome', cnpj)}\n\n"
                        f"Os seguintes títulos estão em aberto mas SEM NFe/Boleto indexado:\n\n"
                        + "\n".join(linhas) +
                        f"\n\nTotal: {len(alertas_sem_doc)} título(s)\n"
                        f"Acesse o CRM > Documentos para adicionar manualmente."
                    )
                    evo.enviar_mensagem_texto(grupo_jid_empresa, msg_sem_doc)
                    print(f"   🚨 Alerta de {len(alertas_sem_doc)} título(s) sem documentos enviado para grupo Admin.")
            except Exception as e_sd:
                print(f"   ⚠️ Erro ao verificar títulos sem documentos: {e_sd}")

            # --- ENVIO DO RELATORIO DIÁRIO (FIM DO CICLO DA EMPRESA) ---
            try:
                # Localiza se existe um grupo unificado configurado no banco central
                from src.database import conectar as conectar_central
                conn_c = conectar_central()
                g_res = conn_c.cursor().execute("SELECT grupo_relatorio_jid FROM config_global WHERE id = 1").fetchone()
                conn_c.close()
                
                if g_res and g_res[0]:
                    grupo_jid = g_res[0]
                    pdf_path = mgr.gerar_relatorio_pdf_operacao_diaria()
                    if os.path.exists(pdf_path):
                        # Envia uma mensagem de contexto primeiro
                        evo.enviar_mensagem_texto(grupo_jid, f"📊 *Relatório Diário de Operação*\nUnidade: {config.get('empresa_nome', cnpj)}\n\nSegue o resumo das atividades financeiras realizadas hoje:")
                        evo.enviar_midia(grupo_jid, pdf_path)
                        print(f"   📊 Relatório diário de {cnpj} enviado para o grupo de operadores.")
            except Exception as er_rel:
                print(f"   ⚠️ Erro ao enviar relatório diário para o grupo: {er_rel}")

        except Exception as e:
            print(f"   ❌ Erro na negociação IA ({cnpj}): {e}")
def processar_fila_cartorio(cnpj_filtro=None):
    """
    Motor do Cartório:
    Processa a fila de títulos pendentes para envio ao portal.
    """
    print(f"🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Verificando Fila de Cartório...")
    
    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]
        
    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        try:
            conn = conectar(cnpj)
            
            # --- WATCHDOG: Reset de jobs travados em "Processando" há mais de 10 minutos ---
            conn.cursor().execute("""
                UPDATE cartorio_jobs 
                SET status_automacao = 'Erro', 
                    log_erro = 'Timeout: O robô ficou travado em Processando por mais de 10 minutos. Verifique se o navegador estava aberto e tente novamente.',
                    data_execucao = ?
                WHERE status_automacao = 'Processando'
                AND data_execucao IS NOT NULL
                AND (CAST(strftime('%s','now') AS INTEGER) - CAST(strftime('%s', data_execucao) AS INTEGER)) > 600
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
            conn.commit()
            
            # Busca jobs pendentes
            jobs = conn.cursor().execute(
                "SELECT id, titulo_id FROM cartorio_jobs WHERE status_automacao = 'Pendente' ORDER BY id ASC"
            ).fetchall()
            
            if not jobs:
                conn.close()
                continue
                
            from src.database import carregar_configuracoes_db
            config = carregar_configuracoes_db(cnpj)
            intervalo = config.get('cartorio_interval_min', 5)
            
            # Verifica se o último sucesso/erro foi há menos de 'intervalo' minutos
            ultimo_job = conn.cursor().execute(
                "SELECT data_execucao FROM cartorio_jobs WHERE status_automacao IN ('Sucesso', 'Falha', 'Erro') ORDER BY id DESC LIMIT 1"
            ).fetchone()
            
            if ultimo_job:
                try:
                    dt_last = datetime.strptime(ultimo_job[0], "%Y-%m-%d %H:%M:%S")
                    minutos_passados = (datetime.now() - dt_last).total_seconds() / 60
                    if minutos_passados < intervalo:
                        print(f"   ⏳ Cartório ({cnpj}): Aguardando intervalo de {intervalo} min (faltam {intervalo - minutos_passados:.1f} min).")
                        conn.close()
                        continue
                except: pass
                
            # Se chegamos aqui, podemos processar O PRIMEIRO da fila
            job_id, titulo_id = jobs[0]
            print(f"   🚀 Processando Cartório Job #{job_id} para Título ID {titulo_id}...")
            
            # --- 1. VERIFICAÇÃO DE DADOS ESSENCIAIS (EMAIL EXTRACTION) ---
            conn.row_factory = __import__('sqlite3').Row
            row = conn.cursor().execute("SELECT * FROM titulos WHERE id=?", (titulo_id,)).fetchone()
            titulo = dict(row) if row else None
            
            # Se a emissão não estiver preenchida (nem pelo scanner passado nem manual)
            if titulo and not titulo.get('emissao'):
                print(f"   🔍 Buscando XML/PDF da NF {titulo['numero_nf']} no E-mail...")
                from src.mail_scanner import MailScanner
                scanner = MailScanner(config)
                
                cli = conn.cursor().execute("SELECT nome, cnpj FROM clientes WHERE trim(nome)=?", (titulo['pagador'].strip(),)).fetchone()
                
                dados_extraidos = None
                if cli:
                   dados_extraidos = scanner.buscar_e_extrair_dados_nf(titulo['numero_nf'], cli['cnpj'], cli['nome'])
                
                if dados_extraidos and dados_extraidos.get('emissao'):
                    print(f"   ✅ Extração Inteligente: Emissão inserida ({dados_extraidos['emissao']})")
                    conn.cursor().execute("UPDATE titulos SET emissao=? WHERE id=?", (dados_extraidos['emissao'], titulo_id))
                    conn.commit()
                else:
                    print(f"   ⚠️ NF não encontrada no email ou extração falhou.")
                    conn.cursor().execute("UPDATE cartorio_jobs SET status_automacao = 'Aguardando Dados', log_erro = 'Falta Data de Emissão. Preencha manualmente no CRM.' WHERE id = ?", (job_id,))
                    conn.commit()
                    conn.close()
                    continue
            
            # Marca a data_execucao agora (para o watchdog saber quando começou)
            agora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Deixa como Pendente para o robô local pegar. O watchdog só atua se o robô local pegar (que muda pra Processando).
            conn.cursor().execute("UPDATE cartorio_jobs SET data_execucao = ? WHERE id = ?", (agora_str, job_id,))
            conn.commit()
            conn.close()
            
            print(f"   ✅ Título ID {titulo_id} está pronto na fila (Pendente) aguardando o Robô Local.")
                
        except Exception as e:
            print(f"   ❌ Erro ao processar fila de cartório ({cnpj}): {e}")

def verificar_acordos_vencidos(cnpj_filtro=None):
    from src.evolution_controller import EvolutionController
    from src.database import carregar_configuracoes_db
    print(f"🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Verificando Acordos Prometidos...")
    
    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]
        
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    
    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        try:
            conn = conectar(cnpj)
            conn.row_factory = __import__('sqlite3').Row
            
            sessoes = conn.cursor().execute(
                "SELECT * FROM webhook_sessions WHERE estado='acordo_aprovado' AND data_promessa IS NOT NULL AND data_promessa <= ?",
                (hoje_str,)
            ).fetchall()
            
            if not sessoes:
                conn.close()
                continue
                
            config = carregar_configuracoes_db(cnpj)
            evo = EvolutionController(config=config, nome_empresa_cliente=cnpj)
            operador_num = config.get('operador_whatsapp')
            
            for s in sessoes:
                sess_dict = dict(s)
                cliente = sess_dict['cliente_nome']
                sess_id = sess_dict['id']
                
                tits = conn.cursor().execute("SELECT SUM(valor) as total FROM titulos WHERE pagador=? AND status='Negociado'", (cliente,)).fetchone()
                total = tits['total'] if tits and tits['total'] else 0
                
                if total > 0 and operador_num:
                    msg = (
                        f"📅 *VERIFICAÇÃO DE ACORDO*\\n"
                        f"Chegou a data prometida para o cliente *{cliente}*.\\n"
                        f"O valor acordado era referente a *R$ {total:,.2f}*.\\n\\n"
                        f"O pagamento foi realizado?\\n"
                        f"✅ CONFIRMAR_ACORDO_{cnpj}_{sess_id}\\n"
                        f"❌ QUEBRA_ACORDO_{cnpj}_{sess_id}"
                    )
                    evo.enviar_mensagem_texto(operador_num, msg)
                    
                    conn.cursor().execute("UPDATE webhook_sessions SET estado='verificando_pagamento' WHERE id=?", (sess_id,))
                    conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Erro verificando acordos ({cnpj}): {e}")

def verificar_retorno_cartorio(cnpj_filtro=None):
    """
    Acompanhamento Pós-Protesto:
    - Verifica títulos enviados ao cartório há mais de 5 dias ainda com status 'Aguardando'.
    - Notifica o operador sobre o status e pede atualização de dados se necessário.
    - Se o status_retorno for 'Devolvido', agenda nova tentativa de envio.
    """
    from src.evolution_controller import EvolutionController
    from src.database import carregar_configuracoes_db

    print(f"🏛️ [{datetime.now().strftime('%d/%m %H:%M')}] Verificando Retornos do Cartório...")

    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]

    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        try:
            conn = conectar(cnpj)
            conn.row_factory = __import__('sqlite3').Row
            config = carregar_configuracoes_db(cnpj)
            operador_num = config.get('operador_whatsapp')

            if not operador_num:
                conn.close()
                continue

            # Busca títulos em Cartório há mais de 5 dias ainda sem resposta
            titulos_aguardando = conn.cursor().execute("""
                SELECT t.id, t.numero_nf, t.valor, t.vencimento, t.pagador, t.data_envio_cartorio, t.status_retorno_cartorio
                FROM titulos t
                WHERE t.status = 'Cartório'
                  AND t.status_retorno_cartorio = 'Aguardando'
                  AND t.data_envio_cartorio IS NOT NULL
                  AND t.data_envio_cartorio <= datetime('now', '-5 days')
            """).fetchall()

            evo = EvolutionController(config=config, nome_empresa_cliente=cnpj)

            for tit in titulos_aguardando:
                tit = dict(tit)
                dias_envio = (datetime.now() - datetime.strptime(tit['data_envio_cartorio'], "%Y-%m-%d %H:%M:%S")).days

                msg = (
                    f"🏛️ *ACOMPANHAMENTO DE CARTÓRIO*\n"
                    f"O título *NF {tit['numero_nf']}* do cliente *{tit['pagador']}* "
                    f"foi enviado ao cartório há *{dias_envio} dias*.\n"
                    f"Valor: *R$ {tit['valor']:,.2f}*\n\n"
                    f"O cartório ainda não retornou. Deseja:\n"
                    f"✅ CARTORIO_ACATOU_{cnpj}_{tit['id']} — Confirmar que foi acatado\n"
                    f"🔄 CARTORIO_REENVIAR_{cnpj}_{tit['id']} — Reenviar com dados corrigidos\n"
                    f"❌ CARTORIO_CANCELAR_{cnpj}_{tit['id']} — Cancelar e reabrir o título"
                )
                evo.enviar_mensagem_texto(operador_num, msg)
                print(f"   📋 Operador notificado sobre retorno do cartório: NF {tit['numero_nf']} ({tit['pagador']})")

                # Marca como 'Notificado' para não repetir no próximo ciclo (renotifica só em +5 dias)
                conn.cursor().execute(
                    "UPDATE titulos SET status_retorno_cartorio = 'Notificado', data_envio_cartorio = ? WHERE id = ?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tit['id'])
                )
                conn.commit()

            # Verifica títulos marcados para reenvio
            titulos_reenviar = conn.cursor().execute("""
                SELECT id FROM titulos WHERE status = 'Cartório' AND status_retorno_cartorio = 'Reenviar'
            """).fetchall()

            for r in titulos_reenviar:
                titulo_id = r[0]
                # Recoloca na fila de cartório
                existe = conn.cursor().execute(
                    "SELECT id FROM cartorio_jobs WHERE titulo_id = ? AND status_automacao = 'Pendente'",
                    (titulo_id,)
                ).fetchone()
                if not existe:
                    conn.cursor().execute(
                        "INSERT INTO cartorio_jobs (titulo_id, status_automacao) VALUES (?, 'Pendente')",
                        (titulo_id,)
                    )
                    conn.cursor().execute(
                        "UPDATE titulos SET status_retorno_cartorio = 'Aguardando' WHERE id = ?",
                        (titulo_id,)
                    )
                    conn.commit()
                    print(f"   🔄 Título ID {titulo_id} reinserido na fila do cartório.")

            conn.close()

        except Exception as e:
            print(f"   ❌ Erro no acompanhamento de cartório ({cnpj}): {e}")


def verificar_promessas_d1(cnpj_filtro=None):
    """
    Follow-up Automático D+1:
    Verifica clientes que prometeram pagar mas não enviaram comprovante no dia seguinte.
    A Analu envia mensagem perguntando se conseguiram pagar e retoma o ciclo se necessário.
    """
    from src.evolution_controller import EvolutionController
    from src.database import carregar_configuracoes_db

    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]

    hoje_str = datetime.now().strftime("%Y-%m-%d")

    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        try:
            conn = conectar(cnpj)
            conn.row_factory = __import__('sqlite3').Row

            # Busca sessões com promessa vencida há 1+ dia E que estão aguardando comprovante
            sessoes_vencidas = conn.cursor().execute("""
                SELECT ws.*, c.whatsapp
                FROM webhook_sessions ws
                LEFT JOIN clientes c ON trim(c.nome) = trim(ws.cliente_nome)
                WHERE ws.estado IN ('acordo_aprovado', 'aguardando_comprovante')
                  AND ws.data_promessa IS NOT NULL
                  AND ws.data_promessa < date('now', '-1 day')
            """).fetchall()

            if not sessoes_vencidas:
                conn.close()
                continue

            config = carregar_configuracoes_db(cnpj)
            evo = EvolutionController(config=config, nome_empresa_cliente=cnpj)

            for sess in sessoes_vencidas:
                sess = dict(sess)
                cliente = sess['cliente_nome']
                sessao_id = sess['id']
                numero = sess.get('whatsapp') or sess.get('numero_whatsapp', '')
                data_prom = sess.get('data_promessa', '')

                # Trava: já cobrado hoje? (pode ser manual ou outra rotina)
                mgr = Manager(cnpj)
                if mgr.ja_foi_cobrado_hoje(cliente):
                    print(f"   ⏭️ {cliente}: Já recebeu contato hoje. Pulando follow-up.")
                    continue

                # Verifica se já chegou comprovante depois da promessa
                comp = conn.cursor().execute(
                    "SELECT id FROM comprovantes WHERE session_id=? AND status='Confirmado'",
                    (sessao_id,)
                ).fetchone()

                if comp:
                    print(f"   ✅ {cliente}: comprovante confirmado. Sem necessidade de follow-up.")
                    conn.cursor().execute(
                        "UPDATE webhook_sessions SET estado='concluido', data_promessa=NULL WHERE id=?",
                        (sessao_id,)
                    )
                    conn.commit()
                    continue

                # Envia mensagem de follow-up
                msg_followup = (
                    f"*Analu (Assistente Virtual) Diz:*\n\n"
                    f"Olá, {cliente.split()[0]}! Tudo bem? 😊 "
                    f"Você havia combinado de realizar o pagamento até o dia *{data_prom}*, "
                    f"mas ainda não identificamos o comprovante no nosso sistema. "
                    f"Conseguiu efetuar o pagamento? Se sim, pode mandar o comprovante aqui que a gente confirma. "
                    f"Se tiver algum problema, me avisa que tentamos resolver juntos! 🤝"
                )

                if numero:
                    numeros = [n.strip() for n in numero.split(';') if n.strip()]
                    for num in numeros:
                        evo.enviar_mensagem_texto(num, msg_followup)
                    print(f"   🔔 Follow-up D+1 enviado para {cliente} (promessa: {data_prom}).")

                # Retoma o ciclo de cobrança
                conn.cursor().execute(
                    "UPDATE webhook_sessions SET estado='aguardando_resposta', data_promessa=NULL WHERE id=?",
                    (sessao_id,)
                )
                conn.commit()

            conn.close()
        except Exception as e:
            print(f"   ❌ Erro no follow-up D+1 ({cnpj}): {e}")


def resumo_e_execucao_cartorio_noturno(cnpj_filtro=None):
    """
    Agendamento Noturno do Cartório (21h):
    1. Envia resumo ao operador dos títulos que serão protestados essa noite.
    2. Executa a fila de cartório agendada para esse dia.
    """
    from src.evolution_controller import EvolutionController
    from src.database import carregar_configuracoes_db

    print(f"🏛️ [{datetime.now().strftime('%d/%m %H:%M')}] Iniciando Rotina Noturna de Cartório...")

    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]

    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        try:
            conn = conectar(cnpj)
            conn.row_factory = __import__('sqlite3').Row

            # Busca jobs agendados para hoje
            jobs = conn.cursor().execute("""
                SELECT cj.id, cj.titulo_id, t.numero_nf, t.valor, t.pagador
                FROM cartorio_jobs cj
                JOIN titulos t ON t.id = cj.titulo_id
                WHERE cj.status_automacao = 'Agendado_Noturno'
                ORDER BY cj.id ASC
            """).fetchall()

            if not jobs:
                conn.close()
                continue

            config = carregar_configuracoes_db(cnpj)
            evo = EvolutionController(config=config, nome_empresa_cliente=cnpj)
            operador_num = config.get('operador_whatsapp')

            # 1. Resumo ao operador antes de executar
            if operador_num:
                linhas = [f"  • NF {j['numero_nf']} | {j['pagador']} | R$ {j['valor']:,.2f}" for j in [dict(j) for j in jobs]]
                resumo = (
                    f"🏛️ *ROTINA NOTURNA — CARTÓRIO*\n"
                    f"Vou executar agora o envio de *{len(jobs)} título(s)* para protesto:\n\n"
                    + "\n".join(linhas) +
                    f"\n\nTentei negociar durante 20 dias sem sucesso. Executando agora..."
                )
                evo.enviar_mensagem_texto(operador_num, resumo)
                print(f"   📋 Resumo noturno enviado: {len(jobs)} título(s).")

            conn.close()

            # 2. Processa a fila normalmente
            processar_fila_cartorio(cnpj_filtro=cnpj)

        except Exception as e:
            print(f"   ❌ Erro na rotina noturna de cartório ({cnpj}): {e}")


if __name__ == "__main__":
    # Se rodar o arquivo direto, força a execução para teste
    disparar_cobranca_automatica(forcar_execucao=True)
    processar_fila_cartorio()
    verificar_retorno_cartorio()
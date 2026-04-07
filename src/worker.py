from src.database import listar_todos_agendamentos_ativos, conectar
from src.manager import Manager
from src.rag_negotiator import RAGNegotiator
from src.cartorio_automation import CartorioAutomation
import json
import asyncio
from datetime import datetime
import time

def disparar_cobranca_automatica(forcar_execucao=False, cnpj_filtro=None):
    """
    Motor de Cobrança:
    1. Varre agendamentos ativos.
    2. Verifica se hoje é dia de cobrança.
    3. Gera mensagens (com aviso de 10 dias se necessário).
    4. Envia e loga.
    """
    print(f"\\n🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Iniciando Motor de Cobrança...")
    
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
            hoje_semana = datetime.now().weekday() # 0=Segunda ... 6=Domingo
            hora_atual = datetime.now().strftime("%H:%M")
            
            # Converte string "['Segunda']" para lista e mapeia para numero, ou pega string brutos
            # Ajuste de robustez para dias salvos como JSON array de strings no novo sistema
            import json
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
                
            horario_esperado = ag.get('horario_envio', '09:00')
            if hora_atual != horario_esperado:
                print(f"⏳ Pulando {cnpj_empresa}: Horário previsto é {horario_esperado}, agora são {hora_atual}.")
                continue

        # Inicia o Gerente para esta empresa específica
        try:
            print(f"🏢 Processando Empresa CNPJ: {cnpj_empresa}...")
            mgr = Manager(cnpj_empresa)
            
            # 2. Busca a fila de cobrança (Apenas 'Cobrar' e 'Aberto')
            fila = mgr.agrupar_debitos_por_cliente()
            
            if not fila:
                print(f"   ✅ Nenhuma pendência 'Cobrar' encontrada.")
                continue

            for cliente_nome, info in fila.items():
                try:
                    print(f"   📦 Preparando: {cliente_nome}...")
                    
                    # 3. Gera Mensagem Inteligente (Calcula se tem aviso de 10 dias internamente)
                    msg = mgr.gerar_mensagem_cobranca(cliente_nome, info['dados_cliente'], info['total'], info['itens'])
                    
                    # Busca PDFs atualizados no email
                    zip_path, arquivos_temp = mgr.buscar_e_zipar_pdfs(cliente_nome, info['itens'])
                    
                    # 4. Executa Envio
                    res = mgr.executar_processo_completo_cobranca(
                        cliente_nome, msg, zip_path, info['itens'], arquivos_temp
                    )
                    
                    status = "SUCESSO" if (res['email'] or res['whatsapp']) else "FALHA"
                    print(f"   -> {status} (Zap:{res['whatsapp']} | Email:{res['email']})")
                    
                    if res['email'] or res['whatsapp']:
                        total_envios += 1
                    
                    # Pausa para não bloquear o WhatsApp
                    time.sleep(10)
                    
                except Exception as e_cli:
                    print(f"   ❌ Erro no cliente {cliente_nome}: {e_cli}")

        except Exception as e_emp:
            print(f"❌ Erro crítico ao processar empresa {cnpj_empresa}: {e_emp}")

    print(f"🏁 Ciclo Finalizado. Total de envios: {total_envios}")
    return total_envios

def disparar_negociacoes_ia(cnpj_filtro=None):
    """
    Motor de Negociação RAG — Ciclo Diário de 20 Dias:
    - Dia 1 a 20: envia mensagem diária com tom crescente
    - Detecta pagamento → para cobranças
    - Dia 20+ sem pagamento → notifica operador para confirmar cartório
    """
    print(f"🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Verificando Negociações IA (Ciclo 20 dias)...")
    
    from src.evolution_controller import EvolutionController
    from src.database import carregar_configuracoes_db

    agendamentos = listar_todos_agendamentos_ativos()
    if cnpj_filtro:
        agendamentos = [ag for ag in agendamentos if ag['empresa_dona_cnpj'] == cnpj_filtro]
    
    for ag in agendamentos:
        cnpj = ag['empresa_dona_cnpj']
        try:
            mgr = Manager(cnpj)
            rag = RAGNegotiator(cnpj)
            config = carregar_configuracoes_db(cnpj)
            config['empresa_cnpj'] = cnpj
            evo = EvolutionController(config=config, nome_empresa_cliente=config.get('empresa_nome'))
            operador_num = config.get('operador_whatsapp')

            fila = mgr.agrupar_debitos_por_cliente()
            for cliente, info in fila.items():
                itens_elegíveis = [it for it in info['itens'] if it.get('dias_atraso', 0) >= 1]
                if not itens_elegíveis:
                    continue

                max_dias = max(it['dias_atraso'] for it in itens_elegíveis)
                whatsapp = info['dados_cliente'].get('whatsapp', '')
                if not whatsapp:
                    continue

                numeros = [n.strip() for n in whatsapp.split(';') if n.strip()]
                if not numeros:
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

                # Pula se o cliente já mandou comprovante ou está com acordo ativo
                estados_pausa = ('comprovante_recebido', 'aguardando_comprovante', 'acordo_aprovado', 'verificando_pagamento', 'concluido')
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

                    # 2. Notifica o operador para aprovação final
                    if operador_num:
                        total_fmt = f"R$ {info.get('total', 0):,.2f}"
                        nomes_nfs = ", ".join([f"NF {it['numero_nf']}" for it in itens_elegíveis])
                        msg_op = (
                            f"⚠️ *ALERTA DE CARTÓRIO*\n"
                            f"Cliente: *{cliente}*\n"
                            f"Débito: *{total_fmt}* (vencido há {max_dias} dias)\n"
                            f"Títulos: {nomes_nfs}\n\n"
                            f"O prazo de 20 dias se encerrou. O cliente já foi avisado.\n"
                            f"Confirma o envio para protesto?\n\n"
                            f"✅ CARTÓRIO_SIM_{cnpj}_{cliente.replace(' ', '_')[:20]}\n"
                            f"❌ CARTÓRIO_NAO — para manter em aberto mais tempo"
                        )
                        evo.enviar_mensagem_texto(operador_num, msg_op)
                        print(f"   📋 Operador notificado sobre cartório de {cliente}.")
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
                msg_ia = rag.gerar_proposta_ia(cliente, info_debito, dia_numero=dia_atual)

                for num in numeros:
                    evo.enviar_mensagem_texto(num, msg_ia)

                # Avança o dia de cobrança
                conn4 = conectar(cnpj)
                conn4.cursor().execute(
                    "UPDATE webhook_sessions SET dia_cobranca=?, ultima_mensagem_enviada=?, ultima_interacao=? WHERE id=?",
                    (dia_atual + 1, msg_ia, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sessao['id'])
                )
                conn4.commit()
                conn4.close()

                time.sleep(5)

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
            # Busca jobs pendentes
            jobs = conn.cursor().execute(
                "SELECT id, titulo_id FROM cartorio_jobs WHERE status_automacao = 'Pendente' ORDER BY id ASC"
            ).fetchall()
            
            if not jobs:
                conn.close()
                continue
                
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
            titulo = conn.cursor().execute("SELECT * FROM titulos WHERE id=?", (titulo_id,)).fetchone()
            
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
            
            # Marca como processando para evitar duplicidade
            conn.cursor().execute("UPDATE cartorio_jobs SET status_automacao = 'Processando' WHERE id = ?", (job_id,))
            conn.commit()
            conn.close()
            
            # Executa a automação Playwright (Async -> Sync wrapper)
            robot = CartorioAutomation(cnpj)
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Se já estiver rodando (dentro do FastAPI), criamos uma task
                asyncio.create_task(robot.enviar_titulo(titulo_id))
            else:
                asyncio.run(robot.enviar_titulo(titulo_id))
                
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
            evo = EvolutionController(config=config, nome_empresa_cliente=config.get('empresa_nome'))
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

            evo = EvolutionController(config=config, nome_empresa_cliente=config.get('empresa_nome'))

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
            evo = EvolutionController(config=config, nome_empresa_cliente=config.get('empresa_nome'))

            for sess in sessoes_vencidas:
                sess = dict(sess)
                cliente = sess['cliente_nome']
                sessao_id = sess['id']
                numero = sess.get('whatsapp') or sess.get('numero_whatsapp', '')
                data_prom = sess.get('data_promessa', '')

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
            evo = EvolutionController(config=config, nome_empresa_cliente=config.get('empresa_nome'))
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
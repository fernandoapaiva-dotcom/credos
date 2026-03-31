from src.database import listar_todos_agendamentos_ativos, conectar
from src.manager import Manager
from src.rag_negotiator import RAGNegotiator
from src.cartorio_automation import CartorioAutomation
import json
import asyncio

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

                # ─── Dia 20+: Notificar operador sobre cartório ──────
                if dia_atual >= 20:
                    if operador_num:
                        total_fmt = f"R$ {info.get('total', 0):,.2f}"
                        msg_op = (
                            f"⚠️ *ALERTA DE CARTÓRIO*\n"
                            f"Cliente: *{cliente}*\n"
                            f"Débito: *{total_fmt}* (vencido há {max_dias} dias)\n\n"
                            f"O prazo de 20 dias de negociação se encerrou sem pagamento.\n"
                            f"Deseja enviar os títulos para protesto em cartório?\n\n"
                            f"Responda:\n"
                            f"✅ CARTÓRIO_SIM_{cnpj}_{cliente.replace(' ', '_')[:20]}\n"
                            f"❌ CARTÓRIO_NAO — para manter em aberto"
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

if __name__ == "__main__":
    # Se rodar o arquivo direto, força a execução para teste
    disparar_cobranca_automatica(forcar_execucao=True)
    processar_fila_cartorio()
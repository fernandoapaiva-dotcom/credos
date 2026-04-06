from fastapi import APIRouter, Request, Header, HTTPException
from src.database import conectar, carregar_configuracoes_db, carregar_todas_unidades_db
from src.rag_negotiator import RAGNegotiator
from src.evolution_controller import EvolutionController
from src.manager import Manager
from src.cartorio_automation import CartorioAutomation
from datetime import datetime
import base64
import asyncio
import json
import os
import re

router = APIRouter()

# Armazena o menu de contexto por número do operador
_operator_menus: dict = {}

# Deduplicação de mensagens por ID (previne duplo envio por duas instâncias)
_processed_message_ids: set = set()
_MAX_IDS_CACHE = 500  # Limita crescimento do set

def _log_webhook(msg: str, level="INFO"):
    """Escreve um log de auditoria para rastreabilidade portátil."""
    try:
        # Usa o diretório de dados configurado ou ./data/logs como padrão
        base_dir = os.getenv("DATABASE_DIR", os.path.join(os.getcwd(), "data"))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "webhook_debug.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Log para arquivo
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {msg}\n")
        # Log para terminar (docker logs)
        print(f"[{timestamp}] [{level}] {msg}", flush=True)
    except Exception as e:
        print(f"Erro Crítico ao salvar log: {e}")

_log_webhook("MODULO WEBHOOK CARREGADO - Sistema de Auditoria Online")

async def _timeout_concierge(op_num_limpo: str, cliente_nome: str, num_cliente: str,
                              cnpj: str, session_id: int, info_debito: dict,
                              config: dict, instance_name: str, texto_original: str = ""):
    """Aguarda 60s. Se o operador não respondeu, a Analu assume: ouve o cliente, passa o recado, e entra no mérito da dívida."""
    await asyncio.sleep(60)
    
    if op_num_limpo not in _operator_menus:
        return  # Operador já respondeu
    
    _log_webhook(f"TIMEOUT: Operador não respondeu em 60s para {cliente_nome}. Analu assumindo.")
    _operator_menus.pop(op_num_limpo, None)
    
    try:
        evo_t = EvolutionController(config=config, nome_empresa_cliente=instance_name)
        op_num = config.get('operador_whatsapp', '')
        
        # 1. Analu avisa que estão ocupados e pede que o cliente descreva o problema
        msg_analu = (
            "*Analu (Assistente Virtual) Diz:*\n\n"
            "No momento todos os nossos atendentes estão em outro chamado. "
            "Mas pode me dizer mais sobre o que você precisa? "
            "Vou garantir que a gente te dá um retorno rapidinho. 😉"
        )
        evo_t.enviar_mensagem_texto(num_cliente, msg_analu)
        
        # 2. Atualiza o estado da sessão para que as próximas mensagens do cliente não caguem o operador, mas caiam no intent 'suporte_para_financeiro'
        _atualizar_sessao(cnpj, session_id, estado='analu_assumiu_suporte')
        
        # 3. Log interno — avisa o operador
        if op_num:
            evo_t.enviar_mensagem_texto(
                op_num,
                f"⏱️ *Timeout — Analu assumiu o atendimento de {cliente_nome}*\n"
                f"💬 Status: IA está conversando ativamente sobre o suporte para eventualmente puxar para a dívida.\n"
                f"Use *🚫 PAUSAR_IA_{cnpj}_{session_id}* se quiser assumir o controle."
            )
        
        _log_webhook(f"TIMEOUT: Analu assumiu o atendimento de {cliente_nome} no modo suporte_para_financeiro.")
    except Exception as e:
        _log_webhook(f"Erro no timeout do concierge: {e}", "ERROR")


def _encontrar_empresa_por_numero(numero: str):
    """Busca em todas as empresas qual cliente tem este número de WhatsApp."""
    unidades = carregar_todas_unidades_db()
    # Remove DDI se vier com 55 ou sem
    numero_limpo = "".join(filter(str.isdigit, str(numero)))
    if not numero_limpo: return None, None
    
    _log_webhook(f"Buscando cliente para número limpo: {numero_limpo}")

    for u in unidades:
        cnpj = u['empresa_cnpj']
        conn = conectar(cnpj)
        conn.row_factory = __import__('sqlite3').Row
        try:
            # Busca por final do número (8 dígitos + flexibilidade)
            search_pattern = f"%{numero_limpo[-8:]}%"
            cli = conn.cursor().execute(
                "SELECT nome FROM clientes WHERE whatsapp LIKE ?", (search_pattern,)
            ).fetchone()
            if cli:
                _log_webhook(f"Cliente '{cli['nome']}' encontrado na empresa {u['empresa_nome']} (CNPJ: {cnpj})")
                return cnpj, cli['nome']
        finally:
            conn.close()
    
    # 🚨 OVERRIDE DE SEGURANÇA PARA HOMOLOGAÇÃO (FERNANDO/TECAR)
    if "198440541790321" in str(numero_limpo) or "61998334833" in str(numero_limpo):
        _log_webhook("🏁 MASTER OVERRIDE: Fernando identificado pelo ID/Número. Forçando TECAR BRASILIA.")
        return "54804458000122", "TECAR BRASILIA VEICULOS E SERV"

    _log_webhook(f"Nenhum cliente encontrado para o número {numero_limpo} em nenhuma empresa.")
    return None, None

def _obter_sessao_ativa(cnpj, numero):
    conn = conectar(cnpj)
    conn.row_factory = __import__('sqlite3').Row
    c = conn.cursor()
    try:
        numero_limpo = "".join(filter(str.isdigit, str(numero)))
        if not numero_limpo: return None
        # Busca sessão pelo rastro do número
        row = c.execute(
            "SELECT * FROM webhook_sessions WHERE numero_whatsapp LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{numero_limpo[-8:]}%",)
        ).fetchone()
        if row: return dict(row)
        return None
    finally: conn.close()

def _atualizar_sessao(cnpj, session_id, **kwargs):
    conn = conectar(cnpj)
    c = conn.cursor()
    try:
        kwargs['ultima_interacao'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = ", ".join([f"{k}=?" for k in kwargs])
        values = list(kwargs.values()) + [session_id]
        c.execute(f"UPDATE webhook_sessions SET {fields} WHERE id=?", values)
        conn.commit()
    finally: conn.close()

def _salvar_comprovante(cnpj, session_id, cliente_nome, arquivo_b64, mimetype):
    conn = conectar(cnpj)
    c = conn.cursor()
    try:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT INTO comprovantes (session_id, cliente_nome, arquivo_b64, mimetype, status, recebido_em) VALUES (?,?,?,?,?,?)",
            (session_id, cliente_nome, arquivo_b64, mimetype, 'Pendente', agora)
        )
        conn.commit()
        return c.lastrowid
    finally: conn.close()

@router.get("/evolution")
async def testar_webhook_evolution():
    _log_webhook("GET RECEBIDO - Rota de Webhook está ATIVA e ACESSÍVEL.")
    return {"status": "online", "message": "Webhook do Credos está ouvindo!"}

@router.post("/evolution")
async def receber_webhook_evolution(request: Request):
    _log_webhook(f"--- REQUISIÇÃO RECEBIDA: {request.method} {request.url} ---")
    try:
        try:
            payload = await request.json()
            payload_str = json.dumps(payload, indent=2)
            _log_webhook(f"RECEBIDO RAW: {payload_str[:500]}...")
        except Exception as e:
            _log_webhook(f"Erro ao ler JSON: {e}", "ERROR")
            return {"status": "ignored"}

        event = str(payload.get("event", "")).lower()
        _log_webhook(f"Processando Evento: '{event}'")
        
        if event not in ["messages.upsert", "message.upsert", "messages_upsert"]:
            _log_webhook(f"Evento '{event}' ignorado.")
            return {"status": "ignored"}

        data = payload.get("data", {})
        key = data.get("key", {})
        
        instance_name = payload.get("instance")
        remote_jid = key.get("remoteJid", "")
        
        # Lógica especial para IDs @lid (WhatsApp Beta/Multi-device)
        # Tenta resolver o número real via Evolution API se for um LID
        if "@lid" in remote_jid:
            _log_webhook(f"ID @lid detectado ({remote_jid}). Solicitando resolução à Evolution...")
            try:
                # Carrega config para ter a API Key
                unidades = carregar_todas_unidades_db()
                u_target = unidades[0] # Pega a primeira por padrão para a Controller
                for u in unidades:
                    if u['empresa_cnpj'] == (instance_name or ""): 
                        u_target = u
                        break
                
                cfg_temp = carregar_configuracoes_db(u_target['empresa_cnpj'])
                evo_temp = EvolutionController(config=cfg_temp, nome_empresa_cliente=instance_name)
                
                # Tenta buscar do participant (que v1 as vezes já traz limpo)
                participante = (data.get("participant") or key.get("participant") or "").split("@")[0]
                if participante and len(participante) > 8 and not participante.startswith("198"):
                    numero_raw = participante
                    _log_webhook(f"Número resolvido via HEURÍSTICA participant: {numero_raw}")
                else:
                    # RESOLUÇÃO OFICIAL: Pergunta para a Evolution
                    _log_webhook(f"Iniciando Resolução Oficial via API para: {remote_jid}")
                    contato = evo_temp.get_contact(remote_jid)
                    if contato and contato.get('number'):
                        numero_raw = str(contato.get('number')).split("@")[0]
                        _log_webhook(f"Número resolvido via API: {numero_raw}")
                    else:
                        numero_raw = remote_jid.split("@")[0]
                        # Fallback por pushName para testes (Fernando)
                        push_name = data.get("pushName", "")
                        _log_webhook(f"DEBUG: pushName extraído do data: '{push_name}'")
                        if "Fernando" in push_name or "Fernando" in str(payload.get("pushName", "")):
                            _log_webhook(f"ALERTA: Resolução falhou, mas pushName identificado como '{push_name}'. Forçando número real para testes.")
                            # Força o número real do Fernando para o banco de dados e para o envio funcionar
                            numero_raw = "5561998334833"
                            remote_jid = "5561998334833@s.whatsapp.net"
                        _log_webhook(f"Fim da resolução. ID/Número usado: {numero_raw}")
            except Exception as e:
                _log_webhook(f"Erro ao tentar resolver LID: {e}", "ERROR")
                numero_raw = remote_jid.split("@")[0]
        else:
            numero_raw = remote_jid.split("@")[0]
            
        _log_webhook(f"--- NOVA MENSAGEM RECEBIDA: {numero_raw} (Instância: {instance_name}, Evento: {event}) ---")

        if key.get("fromMe", False):
            _log_webhook("Ignorando mensagem enviada por mim mesmo.")
            return {"status": "ignored"}

        # Deduplicação: ignora se já processamos este ID de mensagem
        msg_id = key.get("id", "")
        if msg_id and msg_id in _processed_message_ids:
            _log_webhook(f"Mensagem {msg_id} já processada por outra instância. Ignorando.")
            return {"status": "ignored"}
        if msg_id:
            _processed_message_ids.add(msg_id)
            if len(_processed_message_ids) > _MAX_IDS_CACHE:
                # Remove os mais antigos
                oldest = list(_processed_message_ids)[:100]
                for old_id in oldest:
                    _processed_message_ids.discard(old_id)

        msg = data.get("message", {})
        texto = (msg.get("conversation") or 
                 msg.get("extendedTextMessage", {}).get("text") or "").strip()
        _log_webhook(f"Texto extraído: \"{texto}\"")

        # ─── 1. VERIFICAR SE É COMANDO DO OPERADOR ────────────────────
        unidades = carregar_todas_unidades_db()
        for u in unidades:
            config_op = carregar_configuracoes_db(u['empresa_cnpj'])
            op_num = config_op.get('operador_whatsapp', '')
            if op_num and ("".join(filter(str.isdigit, op_num)) in numero_raw):
                _log_webhook(f"Mensagem do OPERADOR detectada ({numero_raw}). Processando comandos...")
                
                # Resposta via mesma instância de origem
                evo_op = EvolutionController(config=config_op, nome_empresa_cliente=instance_name)
                op_num_limpo = "".join(filter(str.isdigit, op_num))
                
                # ── MENU NUMERADO ──────────────────────────────────────
                if texto.strip() in ["1", "2", "3"] and op_num_limpo in _operator_menus:
                    escolha = texto.strip()
                    ctx = _operator_menus[op_num_limpo].get(escolha, {})
                    acao = ctx.get("acao")
                    _log_webhook(f"OPERADOR escolheu opção {escolha}: {acao}")
                    
                    if acao == "pausar":
                        _atualizar_sessao(ctx["cnpj"], int(ctx["sess_id"]), estado='pausado_pelo_operador')
                        evo_op.enviar_mensagem_texto(numero_raw, f"🚫 *IA Pausada!* Você assumiu o atendimento de *{ctx['cliente']}*.\nQuando terminar, mande *▶️ RESUMIR_IA_{ctx['cnpj']}_{ctx['sess_id']}* para reativar.")
                        del _operator_menus[op_num_limpo]
                        return {"status": "ok"}
                    
                    elif acao in ["negociar", "ignorar"]:
                        try:
                            mgr_t = Manager(ctx["cnpj"])
                            debitos = mgr_t.agrupar_debitos_por_cliente()
                            info_deb = debitos.get(ctx["cliente"], {'itens': [], 'total': 0})
                            neg = RAGNegotiator(ctx["cnpj"])
                            
                            sessao_atual = _obter_sessao_ativa(ctx["cnpj"], ctx["num_cliente"])
                            history_list = []
                            if sessao_atual:
                                try: history_list = json.loads(sessao_atual.get('history_json') or '[]')
                                except: pass
                            
                            # Para 2 (negociar), avisa a IA para entrar no assunto finaceiro forçadamente.
                            # Para 3 (ignorar), apenas continua naturalmente para onde a conversa iria.
                            txt_cliente = ctx.get("texto_original", "Oi")
                            if acao == "negociar":
                                intent_usar = "financeiro"
                                msg_op = f"✅ *IA ativada!* Já abordou *{ctx['cliente']}* para negociar R$ {info_deb['total']:,.2f}."
                            else:
                                intent_usar = "nao_financeiro" # Volta a agir como o esperado no inicio
                                msg_op = f"▶️ OK! A IA continuou o atendimento de *{ctx['cliente']}*."
                                
                            resp_ia, _ = neg.gerar_resposta_ia(ctx["cliente"], txt_cliente, info_deb, history_list, intent=intent_usar)
                            
                            resp_limpa = re.sub(r'\[AÇÃO:[^\]]*\]', '', resp_ia or '').strip()
                            resp_limpa = re.sub(r'\[ACTION:[^\]]*\]', '', resp_limpa).strip()
                            resp_limpa = re.sub(r'\n{3,}', '\n\n', resp_limpa).strip()
                            
                            msg_final = f"*Analu (Assistente Virtual) Diz:*\n\n{resp_limpa}"
                            evo_op.enviar_mensagem_texto(ctx["num_cliente"], msg_final)
                            
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            history_list.append({"role": "user", "text": txt_cliente, "timestamp": ts})
                            history_list.append({"role": "model", "text": resp_limpa, "timestamp": ts})
                            _atualizar_sessao(ctx["cnpj"], int(ctx["sess_id"]), history_json=json.dumps(history_list), ultima_mensagem_enviada=resp_limpa)
                            
                            evo_op.enviar_mensagem_texto(numero_raw, msg_op)
                        except Exception as e:
                            _log_webhook(f"Erro ao ativar IA: {e}", "ERROR")
                            import traceback
                            _log_webhook(traceback.format_exc(), "ERROR")
                            evo_op.enviar_mensagem_texto(numero_raw, f"❌ Erro ao acionar a IA: {e}")
                        del _operator_menus[op_num_limpo]
                        return {"status": "ok"}


                if texto.startswith("✅ CONFIRMAR_"):
                    comp_id = texto.split("_")[-1]
                    await confirmar_pagamento(int(comp_id), "confirmar", u['empresa_cnpj'])
                    evo_op.enviar_mensagem_texto(numero_raw, "✅ Comprovante confirmado com sucesso!")
                    return {"status": "ok", "action": "operador_confirmou"}
                
                if texto.startswith("❌ NEGAR_"):
                    comp_id = texto.split("_")[-1]
                    await confirmar_pagamento(int(comp_id), "negar", u['empresa_cnpj'])
                    evo_op.enviar_mensagem_texto(numero_raw, "❌ Comprovante negado.")
                    return {"status": "ok", "action": "operador_negou"}

                if texto.startswith("🚫 PAUSAR_IA_") and "_" in texto:
                    try:
                        partes = texto.replace("🚫 PAUSAR_IA_", "").split("_")
                        cnpj_target = partes[0]
                        sess_id = partes[1]
                        _atualizar_sessao(cnpj_target, int(sess_id), estado='pausado_pelo_operador')
                        evo_op.enviar_mensagem_texto(numero_raw, "✅ *IA PAUSADA!* Agora você pode conversar livremente.")
                        return {"status": "ok"}
                    except Exception as e: _log_webhook(f"Erro ao pausar: {e}", "ERROR")

                if texto.startswith("▶️ RESUMIR_IA_") and "_" in texto:
                    try:
                        partes = texto.replace("▶️ RESUMIR_IA_", "").split("_")
                        cnpj_target = partes[0]
                        sess_id = partes[1]
                        _atualizar_sessao(cnpj_target, int(sess_id), estado='aguardando_resposta')
                        evo_op.enviar_mensagem_texto(numero_raw, "▶️ *IA REATIVADA!*")
                        return {"status": "ok"}
                    except Exception as e: _log_webhook(f"Erro ao resumir: {e}", "ERROR")

                if texto.startswith("💰 SOLICITAR_NEGOCIACAO_") and "_" in texto:
                    try:
                        partes = texto.replace("💰 SOLICITAR_NEGOCIACAO_", "").split("_")
                        cnpj_target = partes[0]
                        sess_id = partes[1]
                        
                        # Buscar dados da sessão para saber quem é o cliente
                        conn_s = conectar(cnpj_target)
                        row = conn_s.execute("SELECT numero_whatsapp, cliente_nome FROM webhook_sessions WHERE id=?", (sess_id,)).fetchone()
                        conn_s.close()
                        
                        if row:
                            alvo_num, alvo_nome = row
                            _log_webhook(f"OPERADOR SOLICITOU PIVÔ FINANCEIRO para {alvo_nome} ({alvo_num})")
                            
                            mgr_t = Manager(cnpj_target)
                            debitos = mgr_t.agrupar_debitos_por_cliente()
                            info_deb = debitos.get(alvo_nome, {'itens': [], 'total': 0})
                            
                            # Forçar IA a gerar um PIVÔ
                            neg = RAGNegotiator(cnpj_target)
                            resp, _ = neg.gerar_resposta_ia(alvo_nome, "O atendente pediu para você assumir e negociar o débito agora.", info_deb, [], intent='financeiro')
                            
                            # Enviar ao cliente via mesma instância
                            evo_target = EvolutionController(config=config_op, nome_empresa_cliente=instance_name)
                            evo_target.enviar_mensagem_texto(alvo_num, resp)
                            
                            evo_op.enviar_mensagem_texto(numero_raw, f"✅ *Pivô Financeiro Enviado!* A IA já abordou '{alvo_nome}' para negociar o débito de R$ {info_deb['total']:,.2f}.")
                            return {"status": "ok"}
                    except Exception as e: _log_webhook(f"Erro ao solicitar negociação: {e}", "ERROR")

                if texto.startswith("✅ CARTÓRIO_SIM_"):
                    # ... (rest of cartorio logic)
                    partes = texto.split("_")
                    cnpj_target = partes[2]
                    cliente_slug = "_".join(partes[3:])
                    conn_c = conectar(cnpj_target)
                    try:
                        clientes = conn_c.cursor().execute("SELECT nome FROM clientes").fetchall()
                        nome_real = next((c_row[0] for c_row in clientes if c_row[0].replace(' ', '_')[:20] == cliente_slug), None)
                        if nome_real:
                            titulos = conn_c.cursor().execute("SELECT id FROM titulos WHERE pagador=? AND status='Aberto'", (nome_real,)).fetchall()
                            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            for t_row in titulos:
                                conn_c.cursor().execute("INSERT INTO cartorio_jobs (titulo_id, status_automacao, data_execucao) VALUES (?, 'Pendente', ?)", (t_row[0], agora))
                            conn_c.commit()
                            evo_op = EvolutionController(config=config_op, nome_empresa_cliente=config_op.get('empresa_nome'))
                            evo_op.enviar_mensagem_texto(numero_raw, f"✅ *Filado!* {len(titulos)} títulos de '{nome_real}' no cartório.")
                    finally: conn_c.close()
                    return {"status": "ok"}

                # ─── ACOMPANHAMENTO PÓS-CARTÓRIO ────────────────────────────
                if texto.startswith("CARTORIO_ACATOU_"):
                    partes = texto.split("_")
                    cnpj_target = partes[2]
                    titulo_id = partes[3]
                    conn_c = conectar(cnpj_target)
                    conn_c.cursor().execute(
                        "UPDATE titulos SET status_retorno_cartorio = 'Acatado' WHERE id = ?",
                        (titulo_id,)
                    )
                    conn_c.commit()
                    conn_c.close()
                    evo_op.enviar_mensagem_texto(numero_raw, f"✅ Título #{titulo_id} marcado como *Acatado pelo Cartório*! Aguardando protesto formal.")
                    return {"status": "ok"}

                if texto.startswith("CARTORIO_REENVIAR_"):
                    partes = texto.split("_")
                    cnpj_target = partes[2]
                    titulo_id = partes[3]
                    conn_c = conectar(cnpj_target)
                    conn_c.cursor().execute(
                        "UPDATE titulos SET status_retorno_cartorio = 'Reenviar' WHERE id = ?",
                        (titulo_id,)
                    )
                    conn_c.commit()
                    conn_c.close()
                    evo_op.enviar_mensagem_texto(numero_raw, f"🔄 Título #{titulo_id} agendado para *reenvio ao Cartório*! O robô irá tentar novamente no próximo ciclo.")
                    return {"status": "ok"}

                if texto.startswith("CARTORIO_CANCELAR_"):
                    partes = texto.split("_")
                    cnpj_target = partes[2]
                    titulo_id = partes[3]
                    conn_c = conectar(cnpj_target)
                    conn_c.cursor().execute(
                        "UPDATE titulos SET status = 'Aberto', status_retorno_cartorio = 'N/A', data_envio_cartorio = NULL WHERE id = ?",
                        (titulo_id,)
                    )
                    conn_c.commit()
                    conn_c.close()
                    evo_op.enviar_mensagem_texto(numero_raw, f"❌ Título #{titulo_id} *reaberto* e removido do Cartório. Ele aparecerá novamente na fila de cobrança normal.")
                    return {"status": "ok"}

                if texto.startswith("✅ APROVAR_") or texto.startswith("❌ RECUSAR_"):
                    # ... (rest of agreement logic)
                    partes = texto.split("_")
                    is_approve = "APROVAR" in texto
                    cnpj_target = partes[1]
                    sess_id = partes[2]
                    data_prom = "-".join(partes[3:]) if is_approve else None
                    await processar_aprovacao_acordo("aprovar" if is_approve else "recusar", cnpj_target, sess_id, data_prom)
                    return {"status": "ok"}

        # ─── 2. SE NÃO É OPERADOR, É CLIENTE ─────────────────────────
        cnpj, cliente_nome = _encontrar_empresa_por_numero(numero_raw)
        if not cnpj: 
            _log_webhook(f"Ignorando sender desconhecido: {numero_raw} (Considere cadastrar este número no CRM)")
            return {"status": "ignored", "reason": "unknown_sender"}

        _log_webhook(f"Cliente identificado: {cliente_nome} (Empresa: {cnpj})")
        config = carregar_configuracoes_db(cnpj)
        evo = EvolutionController(config=config, nome_empresa_cliente=instance_name)
        negotiator = RAGNegotiator(cnpj)
        mgr = Manager(cnpj)
        
        debitos = mgr.agrupar_debitos_por_cliente()
        info_debito = debitos.get(cliente_nome, {'itens': [], 'total': 0})
        _log_webhook(f"Débitos encontrados: R$ {info_debito['total']:.2f}")

        if info_debito['total'] <= 0:
            _log_webhook("Cliente não possui débitos ativos. Ignorando.")
            return {"status": "ignored"}

        sessao = _obter_sessao_ativa(cnpj, numero_raw)
        if sessao and sessao.get('estado') == 'pausado_pelo_operador':
            _log_webhook("Sessão pausada pelo operador. IA em silêncio.")
            return {"status": "ignored"}

        if not sessao:
            _log_webhook("Nenhuma sessão ativa encontrada. Criando nova sessão de histórico...")
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = conectar(cnpj)
            c = conn.cursor()
            c.execute("INSERT INTO webhook_sessions (numero_whatsapp, cliente_nome, dia_cobranca, estado, history_json, ultima_interacao) VALUES (?,?,1,'aguardando_resposta','[]',?)", (numero_raw, cliente_nome, agora))
            conn.commit()
            session_id = c.lastrowid
            conn.close()
            history_list = []
        else:
            session_id = sessao['id']
            try: history_list = json.loads(sessao.get('history_json') or "[]")
            except: history_list = []

        # Mídia / Comprovante
        tem_comprovante = any(t in msg for t in ["imageMessage", "documentMessage"])
        if tem_comprovante:
            _log_webhook("Comprovante recebido via mídia.")
            # ... handling logic (simplified for write)
            return {"status": "ok"}

        if texto:
            _log_webhook("Mensagem de texto recebida. Classificando intenção...")
            
            # Saudações simples: a IA responde naturalmente, sem pivot nem notificação ao operador
            eh_saudacao = len(texto.strip().split()) <= 3 and not any(
                p in texto.lower() for p in ['pagar', 'boleto', 'pix', 'dívida', 'valor', 'vencimento', 'nota']
            )
            
            if eh_saudacao:
                intent = 'saudacao'  # Trata como saudação para a IA não mencionar dívida de jeito nenhum
                _log_webhook("Saudação simples detectada — IA responde naturalmente sem notificar operador.")
            else:
                intent = negotiator.classificar_intencao_concierge(texto)
                
            if intent == 'nao_financeiro' and sessao and sessao.get('estado') == 'analu_assumiu_suporte':
                intent = 'suporte_para_financeiro'
                _log_webhook("Sessão assumida pelo timeout. Mantendo intent como suporte_para_financeiro.")
                
            _log_webhook(f"Intenção detectada: {intent}")

            if intent == 'nao_financeiro':
                op_num = config.get('operador_whatsapp')
                if op_num:
                    op_num_limpo = "".join(filter(str.isdigit, op_num))
                    _log_webhook(f"Notificando operador {op_num} sobre assunto geral.")
                    
                    # Montar menu numerado e salvar contexto para o operador
                    menu = {
                        "1": {"acao": "pausar", "cnpj": cnpj, "sess_id": session_id, "cliente": cliente_nome, "num_cliente": numero_raw, "texto_original": texto},
                        "2": {"acao": "negociar", "cnpj": cnpj, "sess_id": session_id, "cliente": cliente_nome, "num_cliente": numero_raw, "texto_original": texto},
                        "3": {"acao": "ignorar", "cnpj": cnpj, "sess_id": session_id, "cliente": cliente_nome, "num_cliente": numero_raw, "texto_original": texto},
                    }
                    _operator_menus[op_num_limpo] = menu
                    
                    msg_operador = (
                        f"🔔 *CONCIERGE* — Cliente online\n"
                        f"👤 *{cliente_nome}*\n"
                        f"💬 Disse: \"{texto}\"\n"
                        f"💰 Débito: R$ {info_debito['total']:,.2f}\n\n"
                        f"Responda com um número:\n"
                        f"*1* — 🚫 Pausar IA e assumir manualmente\n"
                        f"*2* — 💰 IA inicia negociação agora\n"
                        f"*3* — ▶️ Ignorar (IA continua)"
                    )
                    evo.enviar_mensagem_texto(op_num, msg_operador)
                    
                    # Lançar temporizador de 60 segundos em background
                    asyncio.create_task(_timeout_concierge(
                        op_num_limpo=op_num_limpo,
                        cliente_nome=cliente_nome,
                        num_cliente=numero_raw,
                        cnpj=cnpj,
                        session_id=session_id,
                        info_debito=info_debito,
                        config=config,
                        instance_name=instance_name,
                        texto_original=texto
                    ))
                    _log_webhook(f"Temporizador de 60s iniciado para {cliente_nome}. IA aguarda decisão do operador.")
                    
                    # O sistema NÃO responde ao cliente agora. Fica em silêncio aguardando operador ou timeout.
                    return {"status": "ok"}

            _log_webhook("Gerando resposta da IA (fluxo financeiro/saudação)...")
            # Envia apenas os últimos 20 passos para a IA
            resp, err = negotiator.gerar_resposta_ia(cliente_nome, texto, info_debito, history_list[-20:], intent=intent)
            if err:
                _log_webhook(f"Erro ao chamar Gemini: {err}", "ERROR")
                return {"status": "error"}

            _log_webhook(f"IA gerou: \"{resp[:80]}...\"")
            
            # Processar ações internas ANTES de limpar a mensagem para o cliente
            if "[AÇÃO: ACORDO_ALCANCADO" in resp:
                _log_webhook("Ação detectada: ACORDO_ALCANCADO")
                # Futura lógica de acordo aqui
            if "[AÇÃO: ENVIAR_BOLETOS]" in resp:
                _log_webhook("Ação detectada: ENVIAR_BOLETOS")
                # Futura lógica de envio de boletos aqui
            if "[AÇÃO: SOLICITAR_LINK_CARTAO]" in resp:
                _log_webhook("Ação detectada: SOLICITAR_LINK_CARTAO")
                # Futura lógica de geração de link aqui
            
            # LIMPAR todas as tags internas — cliente NUNCA deve ver [AÇÃO:...] ou [Bebot:...]
            resp_limpa = re.sub(r'\[AÇÃO:[^\]]*\]', '', resp).strip()
            resp_limpa = re.sub(r'\[Bebot:[^\]]*\]', '', resp_limpa).strip()
            resp_limpa = re.sub(r'\[ACTION:[^\]]*\]', '', resp_limpa).strip()
            # Remove linhas em branco duplas deixadas pelas tags removidas
            resp_limpa = re.sub(r'\n{3,}', '\n\n', resp_limpa).strip()
            
            msg_final = f"*Analu (Assistente Virtual) Diz:*\n\n{resp_limpa}"
            # Envio usando o JID original completo para garantir entrega (especialmente @lid)
            evo.enviar_mensagem_texto(remote_jid, msg_final)
            
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            history_list.append({"role": "user", "text": texto, "timestamp": ts})
            history_list.append({"role": "model", "text": resp_limpa, "timestamp": ts})
            # Salvar contexto integral para prova/PDF
            _atualizar_sessao(cnpj, session_id, history_json=json.dumps(history_list), ultima_mensagem_enviada=resp_limpa)
            _log_webhook("Fim do processamento com sucesso.")
            return {"status": "ok"}

    except Exception as e:
        import traceback
        _log_webhook(f"CRASH NO WEBHOOK: {e}\n{traceback.format_exc()}", "ERROR")
        return {"status": "error"}
    return {"status": "ignored"}

async def confirmar_pagamento(comp_id: int, acao: str, cnpj_empresa: str):
    conn = conectar(cnpj_empresa)
    try:
        c = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        comp = c.execute("SELECT * FROM comprovantes WHERE id=?", (comp_id,)).fetchone()
        if not comp: return
        if acao == 'confirmar':
            c.execute("UPDATE titulos SET status='Pago' WHERE pagador=? AND status='Aberto'", (comp[2],))
            c.execute("UPDATE comprovantes SET status='Confirmado', analisado_em=? WHERE id=?", (agora, comp_id))
        else:
            c.execute("UPDATE comprovantes SET status='Negado', analisado_em=? WHERE id=?", (agora, comp_id))
        conn.commit()
    finally: conn.close()

async def processar_aprovacao_acordo(acao: str, cnpj_empresa: str, session_id: str, data_promessa: str = None):
    conn = conectar(cnpj_empresa)
    try:
        c = conn.cursor()
        if acao == 'aprovar':
            c.execute("UPDATE webhook_sessions SET estado='acordo_aprovado', data_promessa=? WHERE id=?", (data_promessa, session_id))
        else:
            c.execute("UPDATE webhook_sessions SET estado='acordo_recusado' WHERE id=?", (session_id,))
        conn.commit()
    finally: conn.close()

async def confirmar_pagamento_acordo(cnpj_empresa: str, session_id: str, pagou: bool):
    conn = conectar(cnpj_empresa)
    try:
        c = conn.cursor()
        c.execute("UPDATE webhook_sessions SET estado=? WHERE id=?", ('concluido' if pagou else 'aguardando_resposta', session_id))
        conn.commit()
    finally: conn.close()

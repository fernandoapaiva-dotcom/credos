from fastapi import APIRouter, Request, Header, HTTPException
from src.database import conectar, carregar_configuracoes_db, carregar_todas_unidades_db, verificar_e_registrar_webhook
from src.group_history import salvar_mensagem_contexto, obter_contexto_grupo
from src.rag_negotiator import RAGNegotiator
from src.evolution_controller import EvolutionController
from src.manager import Manager
from src.cartorio_automation import CartorioAutomation
from src.mail_scanner import MailScanner
from src.mailer_service import MailerService
from datetime import datetime
import sqlite3
from google import genai
import base64
import asyncio
import json
import os
import re

router = APIRouter()

# Armazena o menu de contexto por número do operador
_operator_menus: dict = {}

def _log_webhook(msg: str, level="INFO"):
    """Escreve um log de auditoria para rastreabilidade portátil com redação de chaves."""
    try:
        # Redação de segurança: evita que chaves vazem no log
        msg_redigida = re.sub(r'AIzaSy[a-zA-Z0-9_\-]{33}', '[CHAVE_REDIGIDA]', str(msg))
        msg_redigida = re.sub(r'AQ\.[a-zA-Z0-9_\-]{30,}', '[CHAVE_REDIGIDA]', msg_redigida)

        base_dir = os.getenv("DATABASE_DIR", os.path.join(os.getcwd(), "data"))
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "webhook_debug.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Log para arquivo
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {msg_redigida}\n")
        # Log para terminar (docker logs)
        print(f"[{timestamp}] [{level}] {msg_redigida}", flush=True)
    except Exception as e:
        print(f"Erro Crítico ao salvar log: {e}")

_log_webhook("MODULO WEBHOOK CARREGADO - Sistema de Auditoria Online")

# Configuração Central de Modelo (Sempre o Latest conforme pedido pelo USER)
GEMINI_MODEL_LATEST = "gemini-flash-latest"

def sanitizar_texto_ia(texto: str) -> str:
    """Remove padrões de Gemini API Keys do texto para evitar bloqueios de 'leaked key'."""
    if not texto: return ""
    import re
    # Padrao comum das chaves Google AI: AIzaSy seguido de caracteres alfanumericos e hifens/underscores
    padrao_google = r'AIzaSy[a-zA-Z0-9_\-]{33}'
    # Padrao Vertex AI
    padrao_vertex = r'AQ\.[a-zA-Z0-9_\-]{30,}'
    
    texto = re.sub(padrao_google, '[CHAVE_CONFIDENCIAL]', texto)
    return re.sub(padrao_vertex, '[CHAVE_CONFIDENCIAL]', texto)

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


def _encontrar_empresa_por_numero(numero: str, instance_name: str = None):
    """
    Busca em todas as empresas qual cliente tem este número de WhatsApp.
    Se for um LID (@lid), tenta resolver para número real via Evolution API.
    """
    unidades = carregar_todas_unidades_db()
    numero_raw = str(numero)
    numero_limpo = "".join(filter(str.isdigit, numero_raw))
    
    # --- MAPEAMENTO DE EMERGÊNCIA PARA TESTES DO USUÁRIO (LID FIXO) ---
    tester_lids = {
        "198440541790321": "5561998334833", # Fernando LID -> Tel
        "96087142580386": "554898011718"   # Tiago LID -> Tel
    }
    for lid, tel in tester_lids.items():
        if lid in numero_raw:
            _log_webhook(f"⚠️ [MAPEAMENTO EMERGENCIAL] LID {numero_raw} mapeado para {tel}")
            numero_limpo = tel
            break

    # 1. Se for LID, tenta resolver via Evolution API antes de desistir

    if "@lid" in numero_raw or (numero_limpo and len(numero_limpo) > 12 and not numero_raw.startswith("55")):
        _log_webhook(f"Identificado possível LID: {numero_raw}. Tentando resolver...")
        try:
            # Usa a instância que recebeu a mensagem para tentar resolver o contato
            target_instance = instance_name if instance_name else (unidades[0]['empresa_cnpj'] if unidades else None)
            if target_instance:
                config_inst = carregar_configuracoes_db(target_instance)
                evo = EvolutionController(config=config_inst, nome_empresa_cliente=target_instance)
                contato = evo.get_contact(numero_raw)
                if contato:
                    # Tenta extrair o número real do perfil
                    # A Evolution API costuma retornar o número em 'number' ou no JID real
                    real_jid = contato.get("id") or contato.get("remoteJid") or ""
                    if "@s.whatsapp.net" in real_jid:
                        numero_limpo = "".join(filter(str.isdigit, real_jid))
                        _log_webhook(f"LID {numero_raw} resolvido para número: {numero_limpo}")
        except Exception as e:
            _log_webhook(f"Erro ao tentar resolver LID {numero_raw}: {e}", "WARNING")

    if not numero_limpo: return None, None, None
    
    _log_webhook(f"Buscando cliente para número final: {numero_limpo}")

    # Prioridade 1: Buscar na instância que recebeu a mensagem (evita cross-leaks)


    if instance_name:
        for u in unidades:
            if u['empresa_cnpj'] == instance_name or u['empresa_nome'].lower().replace(" ","") == instance_name.lower():
                cnpj = u['empresa_cnpj']
                conn = conectar(cnpj)
                try:
                    search_pattern = f"%{numero_limpo[-8:]}%"
                    conn.row_factory = __import__('sqlite3').Row
                    cli = conn.cursor().execute(
                        "SELECT nome, cnpj FROM clientes WHERE whatsapp LIKE ?", (search_pattern,)
                    ).fetchone()
                    if cli:
                        _log_webhook(f"✅ [CONTEXTO ATUAL] Cliente '{cli['nome']}' encontrado na empresa {u['empresa_nome']}")
                        return cnpj, cli['nome'], cli['cnpj']
                finally:
                    conn.close()

    # Prioridade 2: Buscar em todas as outras (fallback)
    for u in unidades:
        # Pula se já buscamos acima
        if instance_name and (u['empresa_cnpj'] == instance_name or u['empresa_nome'].lower().replace(" ","") == instance_name.lower()):
            continue
            
        cnpj = u['empresa_cnpj']
        conn = conectar(cnpj)
        try:
            search_pattern = f"%{numero_limpo[-8:]}%"
            conn.row_factory = __import__('sqlite3').Row
            cli = conn.cursor().execute(
                "SELECT nome, cnpj FROM clientes WHERE whatsapp LIKE ?", (search_pattern,)
            ).fetchone()
            if cli:
                _log_webhook(f"⚠️ [CROSS-CHECK] Cliente '{cli['nome']}' encontrado na empresa {u['empresa_nome']} (CNPJ: {cnpj})")
                return cnpj, cli['nome'], cli['cnpj']
        finally:
            conn.close()
    
    _log_webhook(f"❌ Nenhum cliente encontrado para o número {numero_limpo} em nenhuma empresa.")
    return None, None, None



def _obter_sessao_ativa(cnpj, numero):
    conn = conectar(cnpj)
    conn.row_factory = sqlite3.Row
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
        if event not in ["messages.upsert", "message.upsert", "messages_upsert"]:
            return {"status": "ignored"}

        data = payload.get("data", {})
        key = data.get("key", {})
        instance_name = payload.get("instance")
        remote_jid = key.get("remoteJid", "")
        
        # ─── FASE 0.1: BLOQUEIO DE AUTO-RESPOSTA (ANTI-LOOP) ──────
        if key.get("fromMe") is True:
            _log_webhook("MENSAGEM PRÓPRIA (fromMe) - Ignorando para evitar loop.")
            return {"status": "ignored"}

        msg = data.get("message", {})
        texto = (msg.get("conversation") or 
                 msg.get("extendedTextMessage", {}).get("text") or "").strip()

        # ─── FASE 0.2: BLOQUEIO DE AUTO-RESPOSTA ENTRE INSTÂNCIAS (BOT x BOT) ──────
        # Ignora se contiver a assinatura da Analu para evitar loops entre instâncias
        if "*Analu - Assistente Virtual*" in texto:
            _log_webhook("MENSAGEM COM ASSINATURA DA ANALU - Ignorando para evitar loop.")
            return {"status": "ignored"}

        # ─── FASE 0.3: DEDUPLICAÇÃO GERAL DE MENSAGENS ──────
        msg_id = key.get("id", "")
        if msg_id and not verificar_e_registrar_webhook(msg_id):
            _log_webhook(f"MENSAGEM DUPLICADA DETECTADA ({msg_id}) - Descartando via Banco de Dados.")
            return {"status": "ignored"}

        # ─── FASE 0: DETECÇÃO PRIORITÁRIA DO GRUPO DE RELATÓRIO ──────
        GRUPO_RELATORIO_ID = "120363409818857510@g.us"
        
        if remote_jid == GRUPO_RELATORIO_ID:
            _log_webhook(f"MENSAGEM NO GRUPO DE RELATÓRIO: {texto[:100]}")
            
            # Recupera contexto recente do grupo
            contexto_recente = obter_contexto_grupo(remote_jid)
            
            # FILTRAGEM AGUDA: Analu só responde no grupo se for CITADA nominalmente
            # Isso evita que ela fique 'escutando' conversas paralelas ou responda a si mesma
            chamou_analu = "analu" in texto.lower()
            
            if chamou_analu:
                _log_webhook("Analu citada nominalmente no grupo. Iniciando processamento...")
                
                # Salva o input do usuário no contexto
                salvar_mensagem_contexto(remote_jid, "user", texto)
                
                try:
                    # Passo 1: Infra e Config
                    unidades_disponiveis = carregar_todas_unidades_db() or []
                    cfg_temp = carregar_configuracoes_db(instance_name)
                    api_key_gemini = cfg_temp.get('gemini_api_key')
                    
                    if not api_key_gemini:
                        for u in unidades_disponiveis:
                            c_alt = carregar_configuracoes_db(u['empresa_cnpj'])
                            if c_alt.get('gemini_api_key'):
                                api_key_gemini = c_alt['gemini_api_key']
                                break
                    
                    if not api_key_gemini:
                        raise ValueError("CHAVE_GEMINI_AUSENTE")

                    # Passo 2: Inicialização
                    client = genai.Client(api_key=api_key_gemini)
                    evo_temp = EvolutionController(config=cfg_temp, nome_empresa_cliente=instance_name)

                    # Passo 3: Coleta dados REAIS do banco para alimentar a IA (evitar alucinação)
                    hoje_str = datetime.now().strftime("%Y-%m-%d")
                    dados_reais_hoje = []
                    titulos_abertos_resumo = []
                    for u in unidades_disponiveis:
                        try:
                            conn_r = conectar(u['empresa_cnpj'])
                            conn_r.row_factory = sqlite3.Row
                            # Cobranças do dia
                            logs = conn_r.execute(
                                "SELECT cliente, tipo_envio, status, detalhes FROM logs_envio WHERE data_envio LIKE ? ORDER BY id DESC LIMIT 30",
                                (f"{hoje_str}%",)
                            ).fetchall()
                            for l in logs:
                                canal_db = l['tipo_envio']
                                det_raw = l['detalhes']
                                try:
                                    det_json = json.loads(det_raw)
                                    wa = det_json.get('res_wa', False)
                                    mail = det_json.get('res_email', False)
                                    if wa and mail: canal_real = "WhatsApp e Email"
                                    elif wa: canal_real = "WhatsApp"
                                    elif mail: canal_real = "Email"
                                    else: canal_real = canal_db
                                except:
                                    canal_real = canal_db

                                dados_reais_hoje.append({
                                    "empresa": u.get('empresa_nome', u['empresa_cnpj']),
                                    "cliente": l['cliente'],
                                    "canal": canal_real,
                                    "status": l['status']
                                })
                            # Títulos em aberto por cliente
                            titulos = conn_r.execute(
                                "SELECT pagador, COUNT(*) as qtd, SUM(valor) as total FROM titulos WHERE status='Aberto' AND acao='Cobrar' GROUP BY pagador ORDER BY total DESC LIMIT 10"
                            ).fetchall()
                            for t in titulos:
                                titulos_abertos_resumo.append({
                                    "empresa": u.get('empresa_nome', u['empresa_cnpj']),
                                    "cliente": t['pagador'],
                                    "qtd_titulos": t['qtd'],
                                    "valor_total": round(t['total'] or 0, 2)
                                })
                            conn_r.close()
                        except: pass

                    resumo_hoje = f"{len(dados_reais_hoje)} acionamentos registrados hoje." if dados_reais_hoje else "Nenhum acionamento registrado hoje ainda."
                    logs_sucesso = [d for d in dados_reais_hoje if d['status'] == 'Sucesso']
                    logs_falha = [d for d in dados_reais_hoje if d['status'] != 'Sucesso']

                    # Passo 4: Prompt com dados reais injetados
                    prompt_sistema = f"""Você é a Analu, assistente virtual inteligente do Credos System.
Você está em um grupo de supervisores financeiros.

⚠️ REGRA CRÍTICA: Responda APENAS com dados fornecidos abaixo. NUNCA invente nomes de clientes, valores ou informações.

📊 DADOS REAIS DE ACIONAMENTOS DE HOJE ({datetime.now().strftime('%d/%m/%Y')}):
- Resumo: {resumo_hoje}
- Detalhamento de Sucessos: {json.dumps(logs_sucesso, ensure_ascii=False)}
- Detalhamento de Falhas: {json.dumps(logs_falha, ensure_ascii=False)}

INSTRUÇÃO PARA O RELATÓRIO:
1. Agrupe os clientes por EMPRESA.
2. Informe o CANAL utilizado (WhatsApp, E-mail ou ambos).
3. Seja clara e organizada (use tópicos).

📋 CARTEIRA EM ABERTO (top devedores):
{json.dumps(titulos_abertos_resumo, ensure_ascii=False, indent=2)}

📝 HISTÓRICO RECENTE DO GRUPO:
{json.dumps(contexto_recente, ensure_ascii=False)}

MENSAGEM ATUAL DO SUPERVISOR: "{texto}"

CAPACIDADES:
1. RESPONDER detalhadamente com base nos dados. Separe por empresa se houver mais de uma.
2. EXECUTAR AÇÕES:
   - Cobrar um cliente: {{"action": "send_message", "client_name": "NOME_DO_CLIENTE", "text_to_send": "MENSAGEM"}}
   - Gerar Relatório PDF de hoje: {{"action": "generate_report", "reason": "Solicitado pelo supervisor"}}
- Se a lista estiver vazia, diga que não houve cobranças registradas ainda hoje.
- Seja profissional, concisa e direta.
"""
                    
                    res_ia = client.models.generate_content(model=GEMINI_MODEL_LATEST, contents=prompt_sistema)
                    resposta_texto = res_ia.text.strip()
                    _log_webhook(f"IA gerou resposta no grupo: {resposta_texto[:100]}")

                    # Passo 4: Executor de Ações (Agentic Logic)
                    if '{"action":' in resposta_texto:
                        try:
                            # Tenta extrair o JSON puro (o Gemini as vezes coloca markdown)
                            json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
                            if json_match:
                                action_data = json.loads(json_match.group())
                                if action_data.get("action") == "send_message":
                                    cliente_alvo = action_data.get("client_name")
                                    msg_para_cliente = action_data.get("text_to_send")
                                    
                                    _log_webhook(f"AGENTE: Executando envio para {cliente_alvo}")
                                    
                                    sucesso_envio = False
                                    # Busca o número do cliente em todas as unidades
                                    for u_item in unidades_disponiveis:
                                        conn_u = conectar(u_item['empresa_cnpj'])
                                        cli_row = conn_u.cursor().execute(
                                            "SELECT whatsapp, nome FROM clientes WHERE nome LIKE ? OR cnpj LIKE ? LIMIT 1",
                                            (f"%{cliente_alvo}%", f"%{cliente_alvo}%")
                                        ).fetchone()
                                        conn_u.close()
                                        
                                        if cli_row and cli_row[0]:
                                            try:
                                                mgr = Manager(u_item['empresa_cnpj'])
                                                # Dispara a régua de cobrança completa (com títulos, atrasos, multas e PDF)
                                                if mgr.cobrar_cliente_especifico(cli_row[1], canais_selecionados=['WhatsApp']):
                                                    sucesso_envio = True
                                                    resposta_final_grupo = f"Certinho! ✅ Já disparei a cobrança atualizada (com todos os títulos pendentes, dias de atraso e valores corridos) para a carteira de *{cli_row[1]}*."
                                                    break
                                            except Exception as e_mgr:
                                                _log_webhook(f"Erro ao disparar cobrança rica via webhook: {e_mgr}", "ERROR")
                                    
                                    if not sucesso_envio:
                                        resposta_final_grupo = f"⚠️ Não consegui localizar o número do WhatsApp para o cliente '{cliente_alvo}' em nenhuma unidade."
                                
                                elif action_data.get("action") == "generate_report":
                                    _log_webhook("AGENTE: Gerando relatório PDF para TODAS as unidades...")
                                    try:
                                        if not unidades_disponiveis:
                                            unidades_disponiveis = carregar_todas_unidades_db() or []
                                            
                                        if unidades_disponiveis:
                                            enviados = 0
                                            for u_item in unidades_disponiveis:
                                                cnpj_rel = u_item['empresa_cnpj']
                                                nome_emp = u_item.get('empresa_nome', cnpj_rel)
                                                
                                                _log_webhook(f"Gerando relatório para {nome_emp}...")
                                                mgr_rel = Manager(cnpj_rel)
                                                pdf_path = mgr_rel.gerar_relatorio_pdf_operacao_diaria()
                                                
                                                if os.path.exists(pdf_path):
                                                    pdf_abs = os.path.abspath(pdf_path)
                                                    evo_temp.enviar_mensagem_texto(remote_jid, f"📄 *Relatório de Operação:* {nome_emp}")
                                                    evo_temp.enviar_midia(remote_jid, pdf_abs)
                                                    enviados += 1
                                                    try: os.remove(pdf_path)
                                                    except: pass
                                            
                                            resposta_final_grupo = f"Prontinho! ✅ Gereis e enviei {enviados} relatórios individuais (um para cada empresa cadastrada no sistema)."
                                        else:
                                            resposta_final_grupo = "⚠️ Não localizei nenhuma empresa cadastrada para gerar relatórios."
                                    except Exception as e_rel:
                                        _log_webhook(f"Erro ao gerar relatórios em massa: {e_rel}", "ERROR")
                                        resposta_final_grupo = "❌ Ocorreu um erro ao tentar processar os relatórios das empresas."
                        except Exception as e_json:
                            _log_webhook(f"Erro ao processar JSON de ação: {e_json}", "ERROR")
                            resposta_final_grupo = "Ops! Tentei realizar a ação mas o comando veio formatado de um jeito que não entendi."
                    else:
                        # Resposta Conversacional Normal - Sanitiza para evitar leak de JSON
                        resposta_final_grupo = re.sub(r'\{.*"action":.*\}', '', resposta_texto, flags=re.DOTALL).strip()
                        if not resposta_final_grupo:
                            resposta_final_grupo = "Entendido! Estou processando as informações."

                    # Passo 5: Adição da Assinatura e Envio para o Grupo
                    # --- NÃO ALTERAR: INTERAÇÃO DA ANALU BLINDADA CONFORME SOLICITAÇÃO DO USUÁRIO ---
                    # Esta estrutura garante a identidade visual da Analu no grupo de relatórios.
                    resposta_com_assinatura = f"*Analu - Assistente Virtual*\n\n{resposta_final_grupo}"
                    
                    evo_temp.enviar_mensagem_texto(remote_jid, resposta_com_assinatura)
                    salvar_mensagem_contexto(remote_jid, "model", resposta_final_grupo)
                    # ------------------------------------------------------------------------------

                except Exception as e_grp:
                    _log_webhook(f"❌ FALHA NO GRUPO: {e_grp}", "ERROR")
                    evo_temp.enviar_mensagem_texto(remote_jid, f"*Analu - Assistente Virtual*\n\n⚠️ Desculpe, tive um probleminha técnico agora: {str(e_grp)[:50]}")
            else:
                # Se for apenas uma mensagem no grupo sem chamar ela (e ela não foi a última), apenas salva no contexto silenciosamente
                salvar_mensagem_contexto(remote_jid, "user", texto)
            
            return {"status": "ok"}
        # ─── BLOQUEIO GLOBAL DE GRUPOS NÃO AUTORIZADOS ──────────────
        if "@g.us" in remote_jid and remote_jid != GRUPO_RELATORIO_ID:
            _log_webhook(f"MENSAGEM DE GRUPO IGNORADA: {remote_jid}")
            return {"status": "ignored"}

        # ─── FASE 2: RESOLUÇÃO DE NÚMERO (LID) ──────────────────────
        if "@lid" in remote_jid:
            numero_raw = remote_jid.split("@")[0] 
        else:
            numero_raw = remote_jid.split("@")[0]

        _log_webhook(f"--- MENSAGEM PRIVADA: {numero_raw} | Texto: {texto[:50]} ---")

        # ─── FASE 3: COMANDOS DO OPERADOR ────────────────────────────
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


                if texto.startswith("✅ CONFIRMAR_PGTO_") or texto.startswith("✅ CONFIRMAR_"):
                    # Formato: CONFIRMAR_PGTO_{cnpj}_{comp_id}_{titulo_id}_{num_cliente}
                    try:
                        partes = texto.replace("✅ CONFIRMAR_PGTO_","").replace("✅ CONFIRMAR_","").split("_")
                        cnpj_alvo = partes[0]
                        comp_id_str = partes[1] if len(partes) > 1 else None
                        titulo_id_str = partes[2] if len(partes) > 2 else None
                        num_cli = partes[3] if len(partes) > 3 else None

                        conn_conf = conectar(cnpj_alvo)
                        conn_conf.row_factory = __import__('sqlite3').Row
                        agora_conf = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        # Move o título específico (ou todos se comp antigo sem titulo_id)
                        if titulo_id_str and titulo_id_str.isdigit():
                            titulo_row = conn_conf.cursor().execute(
                                "SELECT numero_nf, valor, pagador FROM titulos WHERE id=?", (titulo_id_str,)
                            ).fetchone()
                            conn_conf.cursor().execute(
                                "UPDATE titulos SET status='Pago' WHERE id=?", (titulo_id_str,)
                            )
                            info_pago = f"NF {titulo_row['numero_nf'] if titulo_row else '?'} de R$ {titulo_row['valor']:,.2f if titulo_row else 0}"
                        else:
                            # Legado: pega do comprovante
                            comp_row = conn_conf.cursor().execute(
                                "SELECT cliente_nome FROM comprovantes WHERE id=?", (comp_id_str,)
                            ).fetchone() if comp_id_str else None
                            cliente_pago = comp_row['cliente_nome'] if comp_row else None
                            if cliente_pago:
                                conn_conf.cursor().execute(
                                    "UPDATE titulos SET status='Pago' WHERE pagador=? AND status='Aberto'",
                                    (cliente_pago,)
                                )
                            info_pago = "todos os títulos em aberto"

                        # Atualiza comprovante
                        if comp_id_str and comp_id_str.isdigit():
                            conn_conf.cursor().execute(
                                "UPDATE comprovantes SET status='Confirmado', analisado_em=? WHERE id=?",
                                (agora_conf, comp_id_str)
                            )

                        conn_conf.commit()

                        # Obtém sessão do cliente para agradecer e encerrar
                        if num_cli:
                            sess_cli = _obter_sessao_ativa(cnpj_alvo, num_cli)
                            if sess_cli:
                                _atualizar_sessao(cnpj_alvo, sess_cli['id'], estado='concluido')
                                evo_conf = EvolutionController(config=carregar_configuracoes_db(cnpj_alvo), nome_empresa_cliente=instance_name)
                                evo_conf.enviar_mensagem_texto(
                                    f"{num_cli}@s.whatsapp.net",
                                    "*Analu (Assistente Virtual) Diz:*\n\n"
                                    "Pagamento confirmado! Muito obrigada pela preferência. "
                                    "Qualquer dúvida, estamos à disposição. 😊"
                                )

                        conn_conf.close()
                        evo_op.enviar_mensagem_texto(numero_raw, f"✅ *Pagamento registrado!* {info_pago} marcado como PAGO no sistema.")
                    except Exception as e_conf:
                        _log_webhook(f"Erro ao confirmar pagamento: {e_conf}", "ERROR")
                        evo_op.enviar_mensagem_texto(numero_raw, f"❌ Erro ao confirmar: {e_conf}")
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
                    partes = texto.split("_")
                    cnpj_target = partes[2]
                    cliente_slug = "_".join(partes[3:])
                    conn_c = conectar(cnpj_target)
                    cfg_c = carregar_configuracoes_db(cnpj_target)
                    try:
                        clientes = conn_c.cursor().execute("SELECT nome, whatsapp FROM clientes").fetchall()
                        nome_real = next((c_row[0] for c_row in clientes if c_row[0].replace(' ', '_')[:20] == cliente_slug), None)
                        whatsapp_cli = next((c_row[1] for c_row in clientes if c_row[0].replace(' ', '_')[:20] == cliente_slug), None)
                        if nome_real:
                            titulos = conn_c.cursor().execute(
                                "SELECT id, numero_nf, valor FROM titulos WHERE pagador=? AND status='Aberto'",
                                (nome_real,)
                            ).fetchall()
                            agora_c = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            for t_row in titulos:
                                # Move para Cartório no banco
                                conn_c.cursor().execute(
                                    "UPDATE titulos SET status='Cartório', data_envio_cartorio=?, status_retorno_cartorio='Aguardando' WHERE id=?",
                                    (agora_c, t_row[0])
                                )
                                # Insere na fila noturna
                                conn_c.cursor().execute(
                                    "INSERT INTO cartorio_jobs (titulo_id, status_automacao, data_execucao) VALUES (?, 'Agendado_Noturno', ?)",
                                    (t_row[0], agora_c)
                                )
                            conn_c.commit()

                            # Avisa o cliente sobre o protesto
                            if whatsapp_cli:
                                evo_cli = EvolutionController(config=cfg_c, nome_empresa_cliente=instance_name)
                                numeros_cli = [n.strip() for n in whatsapp_cli.split(';') if n.strip()]
                                nfs_str = ', '.join([f"NF {t[1]}" for t in titulos])
                                for num_cli in numeros_cli:
                                    evo_cli.enviar_mensagem_texto(
                                        num_cli,
                                        f"*Analu (Assistente Virtual) Diz:*\n\n"
                                        f"Informamos que o débito referente à {nfs_str} foi encaminhado para *protesto em cartório*. "
                                        f"Para regularizar sua situação, entre em contato com o nosso financeiro."
                                    )

                            evo_op.enviar_mensagem_texto(numero_raw,
                                f"✅ *Filado!* {len(titulos)} título(s) de '{nome_real}' agendados para cartório. "
                                f"O robô executará esta noite e te enviará um resumo antes de começar."
                            )
                        else:
                            evo_op.enviar_mensagem_texto(numero_raw, f"❌ Não encontrei o cliente '{cliente_slug}'.")
                    finally:
                        conn_c.close()
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
        cnpj, cliente_nome, cliente_cnpj = _encontrar_empresa_por_numero(numero_raw, instance_name=instance_name)

        if not cnpj: 
            _log_webhook(f"Sender desconhecido: {numero_raw}. Enviando resposta de boas-vindas/ajuda.")
            # Tenta pegar uma EvolutionController de qualquer empresa para responder
            unidades_fallback = carregar_todas_unidades_db()
            if unidades_fallback:
                _log_webhook(f"Sender desconhecido: {numero_raw}. IGNORANDO silenciosamente conforme regra estrita.")
            return {"status": "ok", "reason": "unknown_sender_ignored"}

        _log_webhook(f"Cliente identificado: {cliente_nome} (Empresa: {cnpj})")
        # --- CORREÇÃO MULTI-TENANCY: Usa config da instância de ORIGEM ---
        config_inst = carregar_configuracoes_db(instance_name) if len(instance_name) > 10 else carregar_configuracoes_db(cnpj)
        evo = EvolutionController(config=config_inst, nome_empresa_cliente=instance_name)
        negotiator = RAGNegotiator(cnpj)
        mgr = Manager(cnpj)
        
        debitos = mgr.agrupar_debitos_por_cliente()
        info_debito = debitos.get(cliente_nome, {'itens': [], 'total': 0})
        _log_webhook(f"Débitos encontrados: R$ {info_debito['total']:.2f}")

        if info_debito['total'] <= 0:
            _log_webhook("Cliente não possui débitos ativos. IGNORANDO silenciosamente conforme regra estrita.")
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
            try:
                # Extrai dado da imagem ou documento
                img_msg = msg.get("imageMessage", msg.get("documentMessage", {}))
                b64_data = img_msg.get("jpegThumbnail") or img_msg.get("base64", "")
                mimetype = img_msg.get("mimetype", "image/jpeg")
                caption = img_msg.get("caption", "")

                # Salva comprovante no banco
                comp_id = _salvar_comprovante(cnpj, session_id, cliente_nome, b64_data or "", mimetype)

                # Busca títulos em aberto do cliente
                conn_comp = conectar(cnpj)
                conn_comp.row_factory = __import__('sqlite3').Row
                titulos_abertos = conn_comp.cursor().execute(
                    "SELECT id, numero_nf, valor FROM titulos WHERE pagador=? AND status='Aberto'",
                    (cliente_nome,)
                ).fetchall()
                titulos_abertos = [dict(t) for t in titulos_abertos]
                conn_comp.close()

                total_aberto = sum(t['valor'] for t in titulos_abertos)
                op_num = config.get('operador_whatsapp', '')

                if op_num:
                    if len(titulos_abertos) == 1:
                        # Caso simples: 1 título, confirmação direta
                        tit = titulos_abertos[0]
                        msg_op = (
                            f"📸 *COMPROVANTE RECEBIDO*\n"
                            f"Cliente: *{cliente_nome}*\n"
                            f"Título: NF {tit['numero_nf']} | R$ {tit['valor']:,.2f}\n"
                            f"Legenda: \"{caption}\"\n\n"
                            f"Confirma o pagamento e move para PAGO?\n"
                            f"✅ CONFIRMAR_PGTO_{cnpj}_{comp_id}_{tit['id']}_{numero_raw.split('@')[0]}\n"
                            f"❌ NEGAR_PGTO_{cnpj}_{comp_id}\n\n"
                        )
                    else:
                        # Múltiplos títulos: lista todos para o operador identificar qual
                        linhas_tits = "\n".join([f"  • NF {t['numero_nf']} | R$ {t['valor']:,.2f} → CONFIRMAR_PGTO_{cnpj}_{comp_id}_{t['id']}_{numero_raw.split('@')[0]}" for t in titulos_abertos])
                        msg_op = (
                            f"📸 *COMPROVANTE RECEBIDO*\n"
                            f"Cliente: *{cliente_nome}* | Total em aberto: R$ {total_aberto:,.2f}\n"
                            f"Legenda: \"{caption}\"\n\n"
                            f"O cliente tem *{len(titulos_abertos)} títulos* em aberto. Confirme qual foi pago:\n"
                            + linhas_tits +
                            f"\n\n❌ NEGAR_PGTO_{cnpj}_{comp_id} — para negar o comprovante"
                        )

                    evo.enviar_mensagem_texto(op_num, msg_op)

                # Avisa o cliente que recebeu
                evo.enviar_mensagem_texto(remote_jid,
                    "*Analu (Assistente Virtual) Diz:*\n\nRecebi o seu comprovante! "
                    "Já encaminhei para o nosso financeiro conferir. Em breve te confirmo o pagamento. Obrigada! 🙏"
                )
                _atualizar_sessao(cnpj, session_id, estado='comprovante_recebido')

            except Exception as e:
                _log_webhook(f"Erro ao processar comprovante: {e}", "ERROR")
            return {"status": "ok"}

        if texto:
            _log_webhook("Mensagem de texto recebida. Classificando intenção...")
            
            # Deixa a IA classificar a intenção de forma inteligente
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
                # Se a chave for bloqueada, avisa o operador se possível
                if "leaked" in str(err).lower() or "permission_denied" in str(err).lower():
                    op_num = config.get('operador_whatsapp')
                    if op_num:
                        evo.enviar_mensagem_texto(op_num, "⚠️ *ALERTA CRÍTICO: Chave Gemini Bloqueada!*\nA Google desativou sua chave de API por vazamento. Por favor, gere uma nova chave no Google AI Studio e atualize nas configurações.")
                return {"status": "error"}

            _log_webhook(f"IA gerou: \"{resp}\"")
            
            # Processar ações internas ANTES de limpar a mensagem para o cliente
            # Normaliza para facilitar busca insensível a caracteres especiais
            resp_upper = resp.upper()
            
            if "ACORDO_ALCANCADO" in resp_upper or "PROMESSA:" in resp_upper:
                _log_webhook("Ação detectada: ACORDO_ALCANCADO / PROMESSA")
                
            if "ENVIAR_BOLETOS" in resp_upper or "BUSCAR_NF_EMAIL" in resp_upper or "ENVIAR_DOCUMENTOS_EMAIL" in resp_upper:
                _log_webhook("Ação de DOCUMENTOS detectada na resposta da IA.")
            
            if "SOLICITAR_LINK_CARTAO" in resp_upper:
                _log_webhook("Ação detectada: SOLICITAR_LINK_CARTAO")
            
            # --- AÇÃO: BUSCAR_NF_EMAIL e ENVIAR_BOLETOS (Envio via WhatsApp) ---
            # Detecção de tipo de documento solicitado
            wants_boleto = False
            wants_nf = False
            if "ENVIAR_BOLETO" in resp_upper: wants_boleto = True
            if "ENVIAR_NOTA" in resp_upper: wants_nf = True
            if "ENVIAR_TUDO" in resp_upper or "BUSCAR_NF" in resp_upper:
                wants_boleto = True
                wants_nf = True
                
            has_doc_action = wants_boleto or wants_nf

            if has_doc_action or "ENVIAR_DOCUMENTOS_EMAIL" in resp_upper:
                is_email_only = "ENVIAR_DOCUMENTOS_EMAIL" in resp_upper and not has_doc_action

                email_alvo = None
                match_e = re.search(r'ENVIAR_DOCUMENTOS_EMAIL[:\s]+([^]\|]+)', resp_upper)
                if match_e: email_alvo = match_e.group(1).strip()

                _log_webhook(f"🏁 Orquestrando entrega de documentos. Email Alvo: {email_alvo}")
                try:
                    scanner = MailScanner(config_inst)
                    pool_arquivos_global = set()
                    
                    # 1. Coleciona todos os documentos relevantes para todos os títulos em aberto
                    for it in info_debito.get('itens', []):
                        nf_num = it['numero_nf']
                        _log_webhook(f"Buscando Pooling para NF {nf_num}...")
                        arquivos = scanner.baixar_anexos_por_nf_validado(
                            nf_num, cliente_cnpj, cliente_nome,
                            vencimento=it['vencimento'],
                            valor=[it['principal'], it['total']]
                        )
                        if arquivos: pool_arquivos_global.update(arquivos)
                    
                    if pool_arquivos_global:
                        # 2. Envio via WhatsApp (se solicitado)
                        if not is_email_only:
                            for arq in pool_arquivos_global:
                                fname_lower = os.path.basename(arq).lower()
                                eh_xml = fname_lower.endswith('.xml')
                                eh_nf = eh_xml or "procnfe" in fname_lower or "nfe" in fname_lower or "nota" in fname_lower
                                eh_boleto = not eh_nf and fname_lower.endswith('.pdf')
                                
                                enviar_agora = False
                                if wants_boleto and eh_boleto: enviar_agora = True
                                if wants_nf and eh_nf: enviar_agora = True
                                
                                if enviar_agora:
                                    _log_webhook(f"Enviando {os.path.basename(arq)} via WhatsApp...")
                                    r_midia = evo.enviar_midia(remote_jid, arq)
                                    if not r_midia and "55" in str(remote_jid):
                                        partes = str(remote_jid).split("@")
                                        num_base = partes[0]
                                        if len(num_base) == 13:
                                            num_sem_9 = num_base[:4] + num_base[5:]
                                            evo.enviar_midia(f"{num_sem_9}@{partes[1]}", arq)
                                        elif len(num_base) == 12:
                                            num_com_9 = num_base[:4] + "9" + num_base[4:]
                                            evo.enviar_midia(f"{num_com_9}@{partes[1]}", arq)
                        
                        # 3. Envio via E-mail (se solicitado)
                        if email_alvo:
                            _log_webhook(f"Disparando e-mail SMTP para {email_alvo}...")
                            mailer = MailerService(user=config_inst.get('base_mail_user'), password=config_inst.get('base_mail_pass'))
                            corpo_email = f"Olá, {cliente_nome}.\n\nConforme conversamos via WhatsApp, seguem em anexo os documentos (Notas Fiscais/Boletos) referentes ao seu débito com a {config_inst.get('empresa_nome')}.\n\nQualquer dúvida, estamos à disposição."
                            mailer.enviar_email_com_anexos(email_alvo, "Documentos Fiscais - Credos", corpo_email, list(pool_arquivos_global))
                            evo.enviar_mensagem_texto(remote_jid, f"✅ Prontinho! Acabei de enviar os documentos para o e-mail *{email_alvo}*. Dá uma olhadinha lá! 😉")

                    elif not is_email_only:
                        _log_webhook("Nenhum arquivo encontrado no Pooling.")
                        resp = "Poxa, peço sinceras desculpas! Eu tentei anexar a sua nota fiscal e boleto aqui, mas parece que os arquivos em PDF ainda não estão disponíveis no meu sistema no momento. Vou deixar um alerta para que um humano verifique isso para você e envie os arquivos manualmente em breve, tudo bem?"
                except Exception as e:
                    _log_webhook(f"Erro na orquestração de documentos: {e}", "ERROR")
            
            # --- Captura PROMESSA de data de pagamento da IA ---
            match_promessa = re.search(r'\[PROMESSA:(\d{4}-\d{2}-\d{2})\]', resp)
            if match_promessa:
                data_p = match_promessa.group(1)
                _atualizar_sessao(cnpj, session_id, estado='aguardando_comprovante', data_promessa=data_p)
                _log_webhook(f"Promessa de pagamento capturada: {data_p} para {cliente_nome}")

            # LIMPAR todas as tags internas — cliente NUNCA deve ver [AÇÃO:...] ou [ACAO:...]
            resp_limpa = re.sub(r'\[AÇÃO:[^\]]*\]', '', resp).strip()
            resp_limpa = re.sub(r'\[ACAO:[^\]]*\]', '', resp_limpa).strip()
            resp_limpa = re.sub(r'\[Bebot:[^\]]*\]', '', resp_limpa).strip()
            resp_limpa = re.sub(r'\[ACTION:[^\]]*\]', '', resp_limpa).strip()
            resp_limpa = re.sub(r'\[PROMESSA:[^\]]*\]', '', resp_limpa).strip()  # Remove tag interna
            # Remove linhas em branco duplas deixadas pelas tags removidas
            resp_limpa = re.sub(r'\n{3,}', '\n\n', resp_limpa).strip()
            
            msg_final = f"*Analu (Assistente Virtual) Diz:*\n\n{resp_limpa}"
            # --- LOGICA DE ENVIO COM RETRY ---
            _log_webhook(f"Enviando resposta para {remote_jid}...")
            r_envio = evo.enviar_mensagem_texto(remote_jid, msg_final)
            
            # Fallback 1: @lid falhou - tenta converter o numero do @lid para @s.whatsapp.net
            if not r_envio and "@lid" in str(remote_jid):
                num_lid = remote_jid.split("@")[0]
                jid_fallback = f"{num_lid}@s.whatsapp.net"
                _log_webhook(f"@lid falhou. Tentando JID convertido: {jid_fallback}")
                r_envio = evo.enviar_mensagem_texto(jid_fallback, msg_final)

            # Fallback 2: Se é brasileiro com 9º dígito, tenta variação
            if not r_envio and "55" in str(remote_jid):
                _log_webhook("Tentativa falhou. Testando variação do 9º dígito (Brasil)...")
                partes = str(remote_jid).split("@")
                num_base = partes[0]
                if len(num_base) == 13: # 55 + DDD (2) + 9 + 8 digitos
                    num_sem_9 = num_base[:4] + num_base[5:] # Remove o 5º caractere (o 9)
                    jid_sem_9 = f"{num_sem_9}@{partes[1]}"
                    _log_webhook(f"Tentando enviar para JID alternativo: {jid_sem_9}")
                    r_envio = evo.enviar_mensagem_texto(jid_sem_9, msg_final)
                elif len(num_base) == 12: # Tenta ADICIONAR o 9 se tiver 12
                    num_com_9 = num_base[:4] + "9" + num_base[4:]
                    jid_com_9 = f"{num_com_9}@{partes[1]}"
                    _log_webhook(f"Tentando enviar para JID alternativo (com 9): {jid_com_9}")
                    r_envio = evo.enviar_mensagem_texto(jid_com_9, msg_final)
            
            if r_envio:
                _log_webhook("Fim do processamento com sucesso.")
            else:
                _log_webhook("Fim do processamento com falha no envio final.", "ERROR")

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            history_list.append({"role": "user", "text": texto, "timestamp": ts})
            history_list.append({"role": "model", "text": resp_limpa, "timestamp": ts})
            # Salvar contexto integral para prova/PDF
            _atualizar_sessao(cnpj, session_id, history_json=json.dumps(history_list), ultima_mensagem_enviada=resp_limpa)
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

import os
import json
import re
import time
from datetime import datetime
from google import genai
from src.database import conectar, carregar_configuracoes_db, listar_logs_cliente_db

class RAGNegotiator:
    def __init__(self, cnpj_empresa):
        self.cnpj_empresa = cnpj_empresa
        self.config = carregar_configuracoes_db(cnpj_empresa)
        self.api_key = "AIzaSyB5j_H_pvZ-cFaahzdCxvrqk0fgsWVfTJI" # Chave Fixa (Repositório Privado)
        self.model_id = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
        
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _obter_template(self):
        try:
            path = os.path.join("prompts", "negotiation_template.txt")
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return "Negocie com o cliente {cliente_nome} sobre a dívida de R$ {valor_total}."

    def preparar_contexto(self, cliente_nome, info_debitos):
        logs = listar_logs_cliente_db(self.cnpj_empresa, cliente_nome)
        historico_resumo = ""
        if logs:
            historico_resumo = "\nHISTÓRICO DE COBRANÇAS RECENTES:\n"
            for log in logs[:5]:
                historico_resumo += f"- {log['data_hora']}: {log['tipo']} | Status: {log['status']} | Detalhe: {log['detalhe']}\n"
        
        titulos_str = ""
        max_dias = 0
        for it in info_debitos['itens']:
            titulos_str += f"NF {it['numero_nf']} (Venc: {it['vencimento']}, Valor: R$ {it['total']:.2f}, Atraso: {it['dias_atraso']} dias)\n"
            if it['dias_atraso'] > max_dias:
                max_dias = it['dias_atraso']
        
        template = self._obter_template()
        prompt = template.format(
            empresa_nome=self.config.get('empresa_nome', 'Nossa Empresa'),
            cliente_nome=cliente_nome,
            valor_total=f"{info_debitos['total']:.2f}",
            lista_titulos=titulos_str,
            dias_vencidos=max_dias,
            chave_pix=self.config.get('chave_pix', 'não informada'),
            tipo_chave_pix=self.config.get('tipo_chave_pix', 'CNPJ')
        )
        
        if historico_resumo:
            prompt += f"\n\nContexto Adicional de Interações Anteriores:{historico_resumo}"
            
        return prompt

    def _chamar_gemini(self, prompt, system_instruction=None):
        if not self.client:
            return None, "Gemini API Key não configurada."
        
        cfg = {}
        if system_instruction:
            cfg["system_instruction"] = system_instruction
        
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=cfg if cfg else None
                )
                if response and response.text:
                    return response.text.replace("**", "*").strip(), None
                return None, "Resposta vazia da IA."
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [WARNING] Limite de velocidade do Google atingido. A Analu aguardará 35s em silêncio... (Tentativa {attempt+1}/3)")
                    time.sleep(35) # Tolerância pro Google API (exigiu 31s)
                    continue
                return None, str(e)
        return None, "Tentativas esgotadas."

    def gerar_proposta_ia(self, cliente_nome, info_debitos, dia_numero=1, history_list=None):
        """Gera mensagem de cobrança para o dia N do ciclo (1-20), considerando o histórico se existir."""
        prompt = self.preparar_contexto(cliente_nome, info_debitos)
        
        hist_text = ""
        if history_list:
            hist_text = "\n--- HISTÓRICO RECENTE DA CONVERSA ---\n"
            for msg in history_list[-10:]:
                rolename = "Cliente" if msg.get('role') == 'user' else "Analu"
                hist_text += f"{rolename}: {msg.get('text')}\n"
            hist_text += "---\n"
            prompt += f"\n\n{hist_text}\nINSTRUÇÃO DE MEMÓRIA: Utilize o histórico acima para dar continuidade à conversa de onde pararam. "
            prompt += "Se o cliente não respondeu sua última mensagem, mencione que ainda aguarda um retorno dele."
        
        if dia_numero <= 5:
            tom = "cordial e amigável, como um primeiro aviso"
        elif dia_numero <= 10:
            tom = "firme e profissional, reforçando a urgência"
        elif dia_numero <= 17:
            tom = "sério e urgente, alertando que o prazo está se encerrando"
        else:
            tom = "muito sério, informando que em poucos dias o título será protestado"
        
        agora_br = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        instrucao = (
            f"Você é Analu, colaboradora do setor financeiro da {self.config.get('empresa_nome', 'nossa empresa')}. "
            f"DATA E HORA ATUAL (BR): {agora_br}. "
            f"Escreva como um ser humano real, numa mensagem de WhatsApp. Tom: {tom}. "
            "Máximo 3 frases. Termine perguntando quando consegue pagar."
        )
        
        mensagem, erro = self._chamar_gemini(prompt, instrucao)
        if erro:
            return f"Falha ao gerar mensagem: {erro}"
        
        self.registrar_negociacao_db(cliente_nome, info_debitos, mensagem)
        return mensagem

    def gerar_resposta_ia(self, cliente_nome, mensagem_cliente, contexto_debito, history_list=None, intent='financeiro'):
        """
        Analu responde como uma pessoa real. A conversa se desenvolve de forma gradual.
        Primeiro: cria rapport. Depois: entra no assunto da dívida naturalmente.
        """
        if history_list is None:
            history_list = []
        
        total = 0
        dias_max_atraso = 0
        titulos_str = ""
        for it in contexto_debito.get('itens', []):
            titulos_str += f"NF {it['numero_nf']} — R$ {it.get('total', 0):.2f} (vencida há {it.get('dias_atraso', 0)} dias)\n"
            total += it.get('total', 0)
            if it.get('dias_atraso', 0) > dias_max_atraso:
                dias_max_atraso = it.get('dias_atraso', 0)
        
        chave_pix = self.config.get('chave_pix', '')
        tipo_pix = self.config.get('tipo_chave_pix', '')
        pix_info = f"PIX disponível: {tipo_pix} — {chave_pix}" if chave_pix else ""
        empresa = self.config.get('empresa_nome', 'nossa empresa')

        # Montar histórico
        num_trocas = len(history_list)
        hist_text = ""
        if history_list:
            hist_text = "--- Histórico da conversa ---\n"
            for msg in history_list[-12:]:
                rolename = "Cliente" if msg.get('role') == 'user' else "Analu"
                hist_text += f"{rolename}: {msg.get('text')}\n"
            hist_text += "---\n\n"

        agora_br = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        # ─── PERSONA DA ANALU ──────────────────────────────────────────────────
        system_instruction = (
            f"Você é Analu, colaboradora do setor financeiro da {empresa}. "
            f"DATA E HORA ATUAL (BR): {agora_br}. "
            "Você conversa pelo WhatsApp com clientes de forma completamente natural e humana. "
            "Você é simpática, direta e profissional — como uma pessoa real, não um chatbot. "
            "\n\nSEU ESTILO DE COMUNICAÇÃO E REGRAS:"
            "\n- Responda SOMENTE ao que o cliente acabou de dizer. Uma coisa de cada vez."
            "\n- Máximo 1 a 2 frases por mensagem. Curto como WhatsApp."
            "\n- Utilize a hora atual fornecida acima para escolher a saudação correta (Bom dia/Boa tarde/Boa noite)."
            "\n- Não faça listas, não numere, não use bullet points."
            "\n- Nunca mencione nomes de colegas internos."
            "\n- IMPORTANTE: NÃO FAÇA ROLEPLAY. Você TEM os dados na mesma hora. NUNCA Diga 'Um momento, vou verificar', 'So um instante estou puxando as infos'. APENAS DÊ A RESPOSTA (ex: 'Seu débito é de R$ 10,00')."
            "\n\nSUA MISSÃO DOCUMENTAL (VELOCIDADE MÁXIMA):"
            "\n- Se o cliente pedir o Boleto ou a NF, você DEVE disparar a tag [ACAO: ENVIAR_BOLETOS] no mesmo instante. NÃO ENROLE."
            "\n- ENTREGUE PRIMEIRO, PERGUNTE DEPOIS: Envie o arquivo no WhatsApp e só depois pergunte se ele quer no e-mail também."
            "\n- É PROIBIDO TENTAR CONVENCER O CLIENTE A USAR PIX SE ELE PEDIU O BOLETO. Entregue o boleto primeiro."
            "\n- Se o cliente pediu o Boleto, sua resposta deve ser: 'Tudo bem, estou te mandando o boleto agora por aqui'. [ACAO: ENVIAR_BOLETOS]"
        )

        # ─── PROMPT DO MOMENTO ─────────────────────────────────────────────────
        if intent == 'saudacao':
            # SAUDAÇÃO PURA — Não gasta cota da API. Responde direto do código.
            import random
            respostas = [
                "Oi! Tudo bem? Como posso ajudar você hoje?",
                "Olá! Tudo ótimo por aqui 😊 Em que posso ser útil?",
                "Oi, tudo bem? Como posso ajudar a sua empresa?"
            ]
            return random.choice(respostas), None
        elif num_trocas == 0:
            # PRIMEIRO CONTATO
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                f"[Contexto financeiro (uso estrito)]\n"
                f"Débito em aberto: R$ {total:.2f}\n"
                f"{titulos_str}\n"
                "INSTRUÇÃO: É o primeiro contato. Se o cliente disser apenas 'Oi' ou não perguntar nada específico, responda apenas com uma saudação calorosa sem mencionar dívida. "
                "MAS, SE ELE JÁ CHEGOU PERGUNTANDO O VALOR DA DÍVIDA OU O QUE ESTÁ DEVENDO, VOCÊ TEM A OBRIGAÇÃO DE FORNECER O VALOR IMEDIATAMENTE (Ex: 'Olá! Consultando aqui vi que o débito é R$ X,XX'). NÃO FAÇA O CLIENTE ESPERAR NUNCA."
            )
        elif num_trocas <= 3:
            # CONVERSA INICIAL — responda ao que foi dito, pode surgir abertura
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                f"[Contexto financeiro exato (uso imediato)]\n"
                f"Débito em aberto: R$ {total:.2f} ({dias_max_atraso} dias de atraso)\n"
                f"{titulos_str}\n"
                "INSTRUÇÃO IMPORTANTE: Responda diretamente e passe a informação solicitada. SE o cliente pedir o débito, MOSTRE O VALOR IMEDIATAMENTE (Ex: 'Seu débito é de R$ X,XX'). É PROIBIDO PEDIR PARA O CLIENTE AGUARDAR OU DIZER 'SÓ UM INSTANTE'."
            )
        elif intent == 'suporte_para_financeiro':
            # Analu atuando como "ombro amigo" do suporte, ouvindo o problema e puxando pra dívida
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                f"[Contexto financeiro]\n"
                f"Débito em aberto: R$ {total:.2f}\n"
                f"{titulos_str}\n"
                "INSTRUÇÃO: O cliente está descrevendo um problema não financeiro (ex: suporte, loja, etc) porque os atendentes estão ocupados. "
                "Responda ao problema dele ('Empatia, diga que já está anotando tudo para passar para a equipe técnica/responsável'). "
                "Se a conversa permitir naturalidade, comece a introduzir o assunto da pendência financeira de forma bem leve (ex: 'Ah, e aproveitando que estamos conversando, vi que tem uma pendência...'). "
                "Cuidado para não parecer um robô ignorando o problema dele."
            )
        else:
            # CONVERSA AVANÇADA FINANCEIRA — pode ser mais direta sobre a dívida
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                f"[Contexto financeiro]\n"
                f"Débito em aberto: R$ {total:.2f} ({dias_max_atraso} dias de atraso)\n"
                f"{titulos_str}"
                f"{pix_info}\n\n"
                "INSTRUÇÃO: Responda ao que foi dito de forma fluida e natural. "
                "Caso contrário, conduza gentilmente para a resolução do débito. "
                "Se o cliente der data de pagamento: |||ACAO: ACORDO_ALCANCADO: DATA|||. "
                "Se pedir PIX: informe. Se pedir boleto: [ACAO: ENVIAR_BOLETOS]. "
                "Esses marcadores NÃO aparecem para o cliente."
            )
            
        # Injeção de Segurança Anti-Repetição e Força-Tarefa de Documentos
        system_instruction += "\n\nREGRA CRÍTICA DE SOBREVIVÊNCIA: NUNCA repita a mesma frase ou pergunta de cobrança que você já usou nas últimas mensagens do histórico."
        
        # Hook de Detecção de Envio de Documento
        if intent != 'saudacao' and num_trocas > 0:
            # Verifica se o histórico tem promessa de boleto
            hist_str = " ".join([m.get('text', '') for m in history_list]).lower()
            cliente_pediu_boleto = any(w in hist_str or w in mensagem_cliente.lower() 
                                       for w in ['boleto', 'nota fiscal', 'nf ', 'documento', 'arquivo'])
            cliente_reclamou = any(w in mensagem_cliente.lower() 
                                   for w in ['cade', 'cadê', 'não chegou', 'nao chegou', 'deu certo', 'chegou', 'enviou', 'não enviou', 'nao enviou'])
            
            if cliente_pediu_boleto or cliente_reclamou:
                prompt += (
                    "\n\n[ALERTA VERMELHO]: O cliente quer o documento aguardado. "
                    "É OBRIGATÓRIO incluir a TAG exata do que ele pediu para liberar o arquivo no sistema! "
                    "\n- Se ele pediu SÓ BOLETO: [ACAO: ENVIAR_BOLETO]"
                    "\n- Se ele pediu SÓ NOTA/NF: [ACAO: ENVIAR_NOTA]"
                    "\n- Se ele pediu AMBOS: [ACAO: ENVIAR_TUDO]"
                    "\nNUNCA pergunte se ele quer os demais documentos. APENAS envie o que ele pedir e não sugira e-mail."
                )
            else:
                prompt += (
                    "\n1. INTERPRETE o tipo de documento solicitado:"
                    "\n   - Quer SÓ o boleto? Despache com [ACAO: ENVIAR_BOLETO]"
                    "\n   - Quer SÓ a Nota/XML? Despache com [ACAO: ENVIAR_NOTA]"
                    "\n   - Quer ambos? Despache com [ACAO: ENVIAR_TUDO]"
                    "\n2. NUNCA pergunte se o cliente quer a nota fiscal se ele pediu apenas o boleto."
                    "\n3. INTERPRETE: Ele passou um e-mail? Use [ACAO: ENVIAR_DOCUMENTOS_EMAIL: [email]]."
                    "\n4. NUNCA faça o cliente esperar. Você já tem os dados. Aja mediatamente."
                )
            
        resposta, erro = self._chamar_gemini(prompt, system_instruction)
        if erro:
            return None, erro
        
        # Extrai ações e adiciona ao final da resposta limpa
        acoes = re.findall(r'\[ACAO:[^\]]*\]', resposta or '')
        resposta_limpa = re.sub(r'\|\|\|ACAO:[^|]*\|\|\|', '', resposta or '').strip()
        # Remove tags vazadas no texto 
        resposta_limpa = re.sub(r'\[A[ÇC]O:[^\]]*\]', '', resposta_limpa).strip()  # Remove [AÇÃO:..] e [ACAO:..]
        resposta_limpa = re.sub(r'\[ACTION:[^\]]*\]', '', resposta_limpa).strip()
        # Remove qualquer tag [ACAO:] limpa também para não duplicar
        resposta_limpa = re.sub(r'\[ACAO:[^\]]*\]', '', resposta_limpa).strip()
        resposta_limpa = re.sub(r'\n{3,}', '\n\n', resposta_limpa).strip()

        # Recoloca as tags ACAO no final (o webhook as detecta por lá)
        for acao in acoes:
            resposta_limpa += f" {acao}"
        resposta_limpa = resposta_limpa.strip()
        
        return resposta_limpa, None

    def classificar_intencao_concierge(self, mensagem_cliente):
        """
        Classifica se o assunto é financeiro ou não.
        MÉTODO OTIMIZADO: Agora usa um motor local sem internet para poupar a cota da IA e não estourar o limite de burst do Google.
        """
        msg = mensagem_cliente.lower().strip()
        
        # 1. Financeiro Puro
        fin_words = ['boleto', 'pix', 'nota', 'nf', 'fatura', 'pagar', 'pagamento', 'devo', 'devendo', 'divida', 'valor', 'atraso', 'desconto', 'parcelar', 'juros', 'pendente', 'pendencia', 'aberto', 'situacao']
        if any(w in msg for w in fin_words):
            return 'financeiro'
            
        # 2. Comprovantes
        if any(w in msg for w in ['comprovante', 'anexo', 'recibo', 'transferencia', 'segue']):
            return 'comprovante'
            
        # 3. Não Financeiro (Suporte/Peças)
        if any(w in msg for w in ['problema', 'suporte', 'garantia', 'peça', 'orcamento', 'atendente', 'humano', 'falar com']):
            return 'nao_financeiro'
            
        # 4. Saudações Simples
        saudacoes = ['oi', 'olá', 'ola', 'bom dia', 'boa tarde', 'boa noite', 'tudo bem', 'tudo joia', 'opa']
        if len(msg) < 40 and any(w in msg for w in saudacoes):
            return 'saudacao'
            
        # Fallback: Se não for saudação simples nem outras, deixa a IA tratar como financeiro e analisar.
        return 'financeiro'

    def classificar_intencao(self, mensagem_cliente):
        prompt = (
            f"Classifique a intenção desta mensagem: '{mensagem_cliente}'\n"
            "Responda APENAS: pago / nao_pago / comprovante / duvida / reclamacao / outro"
        )
        resultado, _ = self._chamar_gemini(prompt)
        if resultado:
            r = resultado.strip().lower()
            for op in ['pago', 'nao_pago', 'comprovante', 'duvida', 'reclamacao', 'outro']:
                if op in r:
                    return op
        return 'outro'

    def registrar_negociacao_db(self, cliente_nome, info_debitos, mensagem):
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        try:
            ids_titulos = ",".join([str(it['id']) for it in info_debitos['itens']])
            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO negociacoes (cliente, titulos_ids, mensagem_gerada, criado_em, status_resposta)
                VALUES (?, ?, ?, ?, ?)
            """, (cliente_nome, ids_titulos, mensagem, agora, "Enviado"))
            conn.commit()
        except Exception as e:
            print(f"Erro ao registrar negociação: {e}")
        finally:
            conn.close()

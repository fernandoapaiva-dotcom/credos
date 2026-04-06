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
        self.api_key = self.config.get("gemini_api_key")
        self.model_id = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
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
            dias_vencidos=max_dias
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
                    time.sleep(5 * (attempt + 1))
                    continue
                return None, str(e)
        return None, "Tentativas esgotadas."

    def gerar_proposta_ia(self, cliente_nome, info_debitos, dia_numero=1):
        """Gera mensagem de cobrança para o dia N do ciclo (1-20)."""
        prompt = self.preparar_contexto(cliente_nome, info_debitos)
        
        if dia_numero <= 5:
            tom = "cordial e amigável, como um primeiro aviso"
        elif dia_numero <= 10:
            tom = "firme e profissional, reforçando a urgência"
        elif dia_numero <= 17:
            tom = "sério e urgente, alertando que o prazo está se encerrando"
        else:
            tom = "muito sério, informando que em poucos dias o título será protestado"
        
        instrucao = (
            f"Você é Analu, do setor financeiro da {self.config.get('empresa_nome', 'nossa empresa')}. "
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

        # ─── PERSONA DA ANALU ──────────────────────────────────────────────────
        system_instruction = (
            f"Você é Analu, colaboradora do setor financeiro da {empresa}. "
            "Você conversa pelo WhatsApp com clientes de forma completamente natural e humana. "
            "Você é simpática, direta e profissional — como uma pessoa real, não um chatbot. "
            "\n\nSEU ESTILO DE COMUNICAÇÃO:"
            "\n- Responda SOMENTE ao que o cliente acabou de dizer. Uma coisa de cada vez."
            "\n- Máximo 1 a 2 frases por mensagem. Curto como WhatsApp."
            "\n- Não faça listas, não numere, não use bullet points."
            "\n- Não jogue informação demais de uma vez. Deixe a conversa fluir."
            "\n- Nunca mencione nomes de colegas internos."
            "\n- Não comece mensagem com 'Claro!', 'Com certeza!', 'Entendido!' — seja mais natural."
            "\n\nSUA MISSÃO (execute com inteligência, no momento certo):"
            "\n- Se o cliente pedir um documento (NF, Boleto, Segunda Via), seja 100% solícita e prestativa."
            "\n- **REGRA DE OURO:** Se estiver enviando um documento, NÃO mencione a dívida, NÃO fale de valores e NÃO peça datas de pagamento na mesma mensagem. Apenas preste o serviço e encerre de forma gentil."
            "\n- Use a tag |||ACAO: BUSCAR_NF_EMAIL||| ou |||ACAO: ENVIAR_BOLETOS||| apenas quando o cliente pedir explicitamente."
            "\n- Nunca diga que não consegue enviar arquivos por aqui. Você consegue."
        )

        # ─── PROMPT DO MOMENTO ─────────────────────────────────────────────────
        if intent == 'saudacao':
            # SAUDAÇÃO PURA — apenas cumprimentar de volta de forma natural
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                "INSTRUÇÃO: O cliente mandou apenas uma saudação curta ('Oi', 'Bom dia', etc). "
                "Responda cumprimentando de volta de forma natural. Se a conversa já estiver em andamento, responda de acordo com o contexto anterior. "
                "Resgate o assunto da dívida apenas se o cliente perguntar ou se houver abertura. "
                "Apenas cumprimente de forma humana."
            )
        elif num_trocas == 0:
            # PRIMEIRO CONTATO — apenas cumprimentar, absolutamente nada de dívida
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                "INSTRUÇÃO: É o primeiro contato da conversa. Responda apenas com uma saudação calorosa e breve. "
                "Pergunte como pode ajudar. NÃO mencione dívida, NF, valores ou pendências. "
                "Apenas abra a conversa de forma natural."
            )
        elif num_trocas <= 3:
            # CONVERSA INICIAL — responda ao que foi dito, pode surgir abertura
            prompt = (
                f"{hist_text}"
                f"Mensagem do cliente: \"{mensagem_cliente}\"\n\n"
                f"[Contexto interno — use com cuidado, no momento certo]\n"
                f"Débito em aberto: R$ {total:.2f} ({dias_max_atraso} dias de atraso)\n"
                f"{titulos_str}\n"
                "INSTRUÇÃO: Responda ao que o cliente disse agora. Se a conversa der abertura natural, "
                "você PODE mencionar sutilmente que tem 'um assunto financeiro pra tratar' — mas sem detalhar ainda. "
                "Não force. Deixe fluir."
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
                "Se pedir PIX: informe. Se pedir boleto: |||ACAO: ENVIAR_BOLETOS|||. "
                "Esses marcadores NÃO aparecem para o cliente."
            )
            
        # Injeção de Segurança Anti-Repetição e Força-Tarefa de Documentos
        system_instruction += "\n\nREGRA CRÍTICA DE SOBREVIVÊNCIA: NUNCA repita a mesma frase ou pergunta de cobrança que você já usou nas últimas mensagens do histórico."
        
        if any(w in mensagem_cliente.lower() for w in ['nota', 'nf', 'boleto', 'pdf', 'arquivo', 'segunda via']):
            prompt += (
                "\n\n[ATENÇÃO MÁXIMA PARA ESTE TURNO]: O cliente acabou de solicitar um arquivo/documento. "
                "Sua ÚNICA missão agora é falar 'Claro, estou enviando por aqui!' de forma simpática. "
                "É ESTRITAMENTE PROIBIDO fazer perguntas, mencionar a palavra 'dívida', falar valores ou adicionar o hook de cobrança (ex: 'Aproveitando...'). "
                "VOCÊ DEVE OBRIGATORIAMENTE incluir a tag |||ACAO: BUSCAR_NF_EMAIL||| no final do seu texto gerado."
            )
            
        resposta, erro = self._chamar_gemini(prompt, system_instruction)
        if erro:
            return None, erro
        
        # Extrai ações ocultas e converte para tags internas do webhook
        acoes = re.findall(r'\|\|\|ACAO:[^|]*\|\|\|', resposta or '')
        resposta_limpa = re.sub(r'\|\|\|ACAO:[^|]*\|\|\|', '', resposta or '').strip()
        # Remove qualquer tag técnica vazada
        resposta_limpa = re.sub(r'\[AÇÃO:[^\]]*\]', '', resposta_limpa).strip()
        resposta_limpa = re.sub(r'\[ACTION:[^\]]*\]', '', resposta_limpa).strip()
        resposta_limpa = re.sub(r'\n{3,}', '\n\n', resposta_limpa).strip()
        for acao in acoes:
            nome = acao.replace('|||ACAO:', '').replace('|||', '').strip()
            resposta_limpa += f" [AÇÃO: {nome}]"
        
        return resposta_limpa, None

    def classificar_intencao_concierge(self, mensagem_cliente):
        """Classifica se o assunto é financeiro ou não."""
        prompt = (
            f"Analise a mensagem: '{mensagem_cliente}'\n\n"
            "Responda APENAS com uma categoria:\n"
            "FINANCEIRO: boletos, pix, pagamentos, dívida, descontos, prazos.\n"
            "NAO_FINANCEIRO: suporte, peças, orçamentos novos, saudações simples, assuntos não financeiros.\n"
            "COMPROVANTE: enviando comprovante ou anexo de pagamento."
        )
        resultado, _ = self._chamar_gemini(prompt)
        if resultado:
            r = resultado.strip().upper()
            if "FINANCEIRO" in r and "NAO" not in r: return 'financeiro'
            if "NAO_FINANCEIRO" in r: return 'nao_financeiro'
            if "COMPROVANTE" in r: return 'comprovante'
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

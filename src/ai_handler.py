import os
import time
from google import genai
from dotenv import load_dotenv

# 1. Carregamento Seguro
load_dotenv(dotenv_path=".env")

# 2. Cliente com modelo de 2026
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def get_ai_response(user_query):
    """
    Consulta o Gemini 2.5 Flash com otimização de tokens e retry automático.
    """
    
    # 3. Carregar Conhecimento (com limpeza simples para economizar tokens)
    try:
        with open("prompts/negotiation_template.txt", "r", encoding="utf-8") as f:
            # Pegamos apenas os primeiros 2000 caracteres das regras (o essencial)
            knowledge_base = f.read()[:2000] 
    except FileNotFoundError:
        knowledge_base = "Regras: Negociação amigável, profissional e focada em prazos."

    # 4. Configuração do Modelo (Focado no Gemini 2.5 Flash conforme sua lista)
    model_id = "gemini-2.5-flash"
    
    config = {
        "system_instruction": (
            "Você é o assistente Credos. Use o contexto abaixo para responder ao cliente. "
            "Seja extremamente conciso para economizar espaço.\n\n"
            f"REGRAS:\n{knowledge_base}"
        )
    }

    # 5. Execução com Retentativa Inteligente para Erro 429
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Envia apenas a query do usuário (o contexto vai na system_instruction)
            response = client.models.generate_content(
                model=model_id,
                contents=user_query,
                config=config
            )
            
            if response.text:
                # Formatação para WhatsApp
                return response.text.replace("**", "*").strip()
            return "IA processou, mas não gerou texto."

        except Exception as e:
            erro_str = str(e)
            
            # Se for erro de cota (429), esperamos o tempo de resfriamento
            if "429" in erro_str or "RESOURCE_EXHAUSTED" in erro_str:
                tempo_espera = 35 * (attempt + 1)
                print(f"⚠️ Cota atingida. Tentativa {attempt + 1}/{max_retries}. "
                      f"Aguardando {tempo_espera}s para limpeza de cache do Google...")
                time.sleep(tempo_espera)
                continue
            
            return f"Erro na IA: {erro_str}"

    return "O servidor de IA está com alta demanda. Tente novamente em 1 minuto."

if __name__ == "__main__":
    # Teste rápido
    print("\n🤖 Iniciando Cérebro do Credos (Otimizado)...")
    pergunta = "Quais as formas de pagamento disponíveis?"
    print(f"Pergunta: {pergunta}")
    print("-" * 30)
    print(f"RESPOSTA:\n{get_ai_response(pergunta)}")
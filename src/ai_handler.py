import os
import time
import streamlit as st
from google import genai
from dotenv import load_dotenv

def get_ai_response(user_query, api_key=None):
    """
    Consulta o Gemini 2.5 Flash usando a chave fornecida ou da sessão.
    """
    
    # 1. Prioriza a chave passada via argumento (Robô de Background)
    if not api_key:
        # 2. Tenta a chave da sessão do Streamlit (Configurada no Front-end)
        try:
            api_key = st.session_state.config.get("gemini_api_key") or st.session_state.config.get("gemini_key")
        except:
            api_key = None
            
    # 3. Fallback para o .env global
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        return "❌ Erro: Gemini API Key não configurada no sistema."

    try:
        client = genai.Client(api_key=api_key)
        
        # Carregar Conhecimento do Prompt
        knowledge_base = ""
        try:
            # Tenta múltiplos caminhos possíveis para o template
            paths = ["prompts/negotiation_template.txt", "../prompts/negotiation_template.txt", "src/prompts/negotiation_template.txt"]
            for p in paths:
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        knowledge_base = f.read()[:2000]
                    break
        except:
            pass
            
        if not knowledge_base:
            knowledge_base = "Regras: Negociação amigável, profissional e focada em resultados."

        model_id = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
        config = {
            "system_instruction": (
                "Você é o assistente Credos. Use o contexto abaixo para cobrar clientes. "
                "Seja conciso, cordial e use emojis profissionais.\n\n"
                f"REGRAS:\n{knowledge_base}"
            )
        }

        # Execução com retry para erro de cota
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=user_query,
                    config=config
                )
                
                if response and response.text:
                    return response.text.replace("**", "*").strip()
                return "IA não gerou texto."

            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    time.sleep(30 * (attempt + 1))
                    continue
                return f"Erro na IA: {err_str}"

    except Exception as general_error:
        return f"Falha crítica na conexão com Gemini: {str(general_error)}"

    return "Servidor ocupado. Tente em breve."
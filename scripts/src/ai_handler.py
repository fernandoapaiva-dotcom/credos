import os
import time
import streamlit as st
from google import genai
from dotenv import load_dotenv

def get_ai_response(user_query):
    """
    Consulta o Gemini 2.5 Flash usando a chave da sessão do cliente (SaaS).
    """
    
    # Prioriza a chave da sessão do Streamlit (Configurada no Front-end)
    api_key = st.session_state.config.get("gemini_key")
    
    if not api_key:
        return "❌ Erro: Gemini API Key não configurada no sistema."

    try:
        client = genai.Client(api_key=api_key)
        
        # Carregar Conhecimento do Prompt
        try:
            with open("prompts/negotiation_template.txt", "r", encoding="utf-8") as f:
                knowledge_base = f.read()[:2000] 
        except FileNotFoundError:
            knowledge_base = "Regras: Negociação amigável, profissional e focada em resultados."

        model_id = "gemini-2.5-flash"
        
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
                
                if response.text:
                    return response.text.replace("**", "*").strip()
                return "IA não gerou texto."

            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    time.sleep(30 * (attempt + 1))
                    continue
                return f"Erro na IA: {str(e)}"

    except Exception as general_error:
        return f"Falha crítica na conexão com Gemini: {str(general_error)}"

    return "Servidor ocupado. Tente em breve."
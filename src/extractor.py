import os
import json
import re
import PyPDF2
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

def extrair_dados_boletos(caminho_pdf, cnpj_credor):
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    texto_pdf = ""
    try:
        with open(caminho_pdf, "rb") as f:
            leitor = PyPDF2.PdfReader(f)
            # Vamos ler apenas as primeiras 2 páginas para não estourar a cota
            for i in range(min(2, len(leitor.pages))):
                texto_pdf += leitor.pages[i].extract_text()
        
        # Limpeza agressiva de espaços para economizar tokens
        texto_pdf = re.sub(r'\s+', ' ', texto_pdf).strip()
        print(f"DEBUG: Texto reduzido para {len(texto_pdf)} caracteres (otimização de cota).")

    except Exception as e:
        print(f"Erro PDF: {e}")
        return []

    # Prompt ultra-curto (cada palavra custa cota!)
    prompt = f"JSON list de titulos do CNPJ {cnpj_credor}: nosso_numero, numero_nf, cnpj_cliente, razao_social, valor, vencimento(YYYY-MM-DD). Texto: {texto_pdf}"

    try:
        print("DEBUG: Aguardando 5s para limpeza de cota...")
        time.sleep(5) # Pausa maior antes de enviar
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        
        texto_limpo = re.sub(r'```json|```', '', response.text).strip()
        dados = json.loads(texto_limpo)
        print(f"✅ SUCESSO: {len(dados)} títulos extraídos.")
        return dados
        
    except Exception as e:
        print(f"❌ Falha: {e}")
        return []
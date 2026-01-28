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
    
    # Configuração de economia: 8000 caracteres é um bloco seguro para o Free Tier
    MAX_CHARS_PER_CHUNK = 8000 

    texto_completo_limpo = ""
    try:
        with open(caminho_pdf, "rb") as f:
            leitor = PyPDF2.PdfReader(f)
            for page in leitor.pages:
                t = page.extract_text()
                # --- LIMPEZA DE COLUNAS (Eliminação de dados inúteis) ---
                # Remove Nosso Número (sequências de 9 ou mais dígitos)
                t = re.sub(r'\d{9,}', '', t)
                # Remove palavras-chave das colunas que você quer ignorar
                t = re.sub(r'(Carteira|Nosso Número|DDA|Situação|VENCIDO|SIM|NÃO)', '', t, flags=re.IGNORECASE)
                texto_completo_limpo += t
    except Exception as e:
        print(f"Erro ao ler PDF: {e}")
        return []

    # Divide o texto limpo em partes para garantir o envio
    partes = [texto_completo_limpo[i:i+MAX_CHARS_PER_CHUNK] for i in range(0, len(texto_completo_limpo), MAX_CHARS_PER_CHUNK)]
    
    todas_extracoes = []
    print(f"📦 O arquivo foi dividido em {len(partes)} partes para segurança de cota.")

    for idx, chunk in enumerate(partes):
        print(f"🚀 Processando parte {idx+1}/{len(partes)}...")
        
        prompt = (
            f"Atue como um extrator de dados financeiro para o CNPJ credor {cnpj_credor}. "
            "Converta o texto abaixo em uma lista JSON de objetos. "
            "IGNORE TOTALMENTE: Carteira, Nosso Número, DDA e Situação. "
            "CAMPOS OBRIGATÓRIOS (use string vazia se não encontrar): "
            "vencimento (YYYY-MM-DD), numero_nf, valor, razao_social, nosso_numero. " # Adicionamos aqui
            f"Texto: {chunk}"
        )

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            # Captura apenas o que estiver entre colchetes [ ] (o JSON)
            match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if match:
                dados = json.loads(match.group())
                todas_extracoes.extend(dados)
                print(f"✅ Parte {idx+1} processada.")

            # Pausa obrigatória para o Google não bloquear a chave por velocidade
            if idx < len(partes) - 1:
                print("⏳ Pausa de 15s para recuperação de cota...")
                time.sleep(15)

        except Exception as e:
            if "429" in str(e):
                print("⚠️ Cota estourada! Pausando 45s para reset do Google...")
                time.sleep(45)
            else:
                print(f"❌ Erro na parte {idx+1}: {e}")

    return todas_extracoes

if __name__ == "__main__":
    # Teste prático com seu arquivo
    resultado = extrair_dados_boletos("data/BoletosAberto-SERVSOLDA (1).PDF", "SUA_EMPRESA_LTDA")
    print(f"\n🎯 Extração concluída! {len(resultado)} títulos encontrados.")
    print(json.dumps(resultado[:3], indent=2, ensure_ascii=False)) # Mostra os 3 primeiros
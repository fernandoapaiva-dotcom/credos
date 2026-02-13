import requests
import json
import os
from dotenv import load_dotenv

# Carrega as variáveis do seu arquivo .env
load_dotenv()

# Pegue a chave do .env ou cole diretamente aqui APENAS PARA ESTE TESTE
API_KEY = "AIzaSyDbjgUI-X-M9YDZwo8dQQGpfgCMvgqgqj8"
# Vamos testar o 2.0-flash
MODELO = "gemini-2.0-flash-lite"

# Essa é a URL exata (endpoint) que a biblioteca tenta acessar por debaixo dos panos
url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent?key={API_KEY}"

headers = {
    'Content-Type': 'application/json'
}

# Esse é o "pacote" exato de dados que enviamos
payload = {
    "contents": [
        {
            "parts": [
                {"text": "Diga apenas: TESTE DE ROTA BÁSICO"}
            ]
        }
    ]
}

print("==================================================")
print(f"🚀 Iniciando Teste Cru de Rota da API Gemini")
print(f"📡 Destino: {url.split('?key=')[0]}...") # Esconde a chave no print
print("==================================================")

try:
    print("⏳ Aguardando resposta do servidor do Google...")
    
    # Dispara a requisição POST diretamente
    resposta = requests.post(url, headers=headers, json=payload)
    
    print("\n✅ Resposta Recebida!")
    print(f"Código HTTP (Status): {resposta.status_code}\n")
    
    # Vamos ver os cabeçalhos que o Google nos devolve (aqui ficam os limites de cota invisíveis)
    print("--- 📦 CABEÇALHOS DA RESPOSTA (O que o Google nos diz em segredo) ---")
    headers_importantes = ['x-ratelimit-limit', 'x-ratelimit-remaining', 'x-ratelimit-reset']
    for header, value in resposta.headers.items():
        if header.lower() in headers_importantes or 'quota' in header.lower():
            print(f"{header}: {value}")
            
    print("\n--- 📝 CORPO DA RESPOSTA (O erro ou o texto real) ---")
    # Imprime o JSON cru, formatado para facilitar a leitura
    print(json.dumps(resposta.json(), indent=2, ensure_ascii=False))

except Exception as e:
    print(f"\n❌ Falha na conexão de rede: {e}")
import requests
import os
import json
from dotenv import load_dotenv

# Carrega .env do diretório raiz
load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8080").rstrip('/')
API_KEY = os.getenv("AUTHENTICATION_API_KEY", "42a24fa6-403d-4c7b-b30a-9359e9a4f783")
# O endereço da Webhook do nosso Backend (Usando host.docker.internal para que o Docker consiga ver o Windows)
WEBHOOK_URL = "http://host.docker.internal:8001/api/webhook/evolution"

headers = {
    "apikey": API_KEY,
    "Content-Type": "application/json"
}

def reconnect():
    print(f"🚀 Iniciando reconexão da AI com Evolution API...")
    print(f"🔗 Backend Webhook: {WEBHOOK_URL}")
    print(f"🌍 Evolution URL: {SERVER_URL}")

    try:
        # 1. Buscar Instâncias
        r_instances = requests.get(f"{SERVER_URL}/instance/fetchInstances", headers=headers)
        if r_instances.status_code != 200:
            print(f"❌ Erro ao buscar instâncias: {r_instances.status_code} - {r_instances.text}")
            return

        instances = r_instances.json()
        if not instances:
            print("⚠️ Nenhuma instância encontrada.")
            return

        for inst in instances:
            name = inst.get('instanceName') or inst.get('name')
            print(f"\n📦 Configurando Webhook para instância: {name}...")
            
            # 2. Configurar Webhook
            # Documentação Evolution: POST /webhook/set/{instance}
            payload = {
                "webhook": {
                    "url": WEBHOOK_URL,
                    "enabled": True,
                    "webhook_by_events": False,
                    "events": [
                        "MESSAGES_UPSERT"
                    ]
                }
            }
            
            r_set = requests.post(f"{SERVER_URL}/webhook/set/{name}", json=payload, headers=headers)
            
            if r_set.status_code in [200, 201]:
                print(f"✅ Webhook configurado com sucesso para {name}!")
            else:
                print(f"❌ Falha ao configurar {name}: {r_set.status_code} - {r_set.text}")

    except Exception as e:
        print(f"💥 Erro Crítico: {e}")

if __name__ == "__main__":
    reconnect()

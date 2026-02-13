import requests
import base64
import os

class EvolutionController:
    def __init__(self, config=None, nome_empresa_cliente=None):
        config = config or {}
        
        # Ajustado para ler EXATAMENTE as chaves do seu .env
        url_raw = os.getenv('SERVER_URL') or config.get('evo_url') or ''
        key_raw = os.getenv('AUTHENTICATION_API_KEY') or config.get('evo_key') or ''

        self.url = url_raw.strip().rstrip('/')
        if self.url and not self.url.startswith('http'):
            self.url = 'http://' + self.url
            
        self.apikey = key_raw.strip()
        
        # Dinamismo para Multi-tenant
        inst_raw = nome_empresa_cliente or os.getenv('INSTANCE_NAME') or "Credos_SaaS"
        self.instance = inst_raw.strip().replace(" ", "_").lower()
        
        self.headers = {
            "apikey": self.apikey,
            "Content-Type": "application/json"
        }

    def debug_log(self, acao, endpoint, resposta, payload=None):
        print(f"\n--- 🕵️ RASTREIO EVOLUTION ({acao}) ---")
        print(f"URL: {endpoint}")
        if payload: print(f"Payload Enviado: {payload if 'media' not in str(payload) else 'Mídia (Base64 Omitido)'}")
        print(f"Status Code: {resposta.status_code}")
        print(f"Resposta: {resposta.text}")
        print("-" * 40 + "\n")

    def checar_status(self):
        try:
            if not self.url or not self.apikey: 
                return "config_error"
            
            endpoint = f"{self.url}/instance/connectionState/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=5)
            
            if r.status_code == 200:
                return r.json().get("instance", {}).get("state") or "disconnected"
            elif r.status_code == 404:
                # Agora ele só retorna desconectado, sem tentar criar escondido
                return "disconnected"
            return "error"
        except Exception as e:
            print(f"Erro Status: {e}")
            return "error"

    def criar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/create"
            
            # Payload corrigido com aspas e vírgulas nos lugares certos
            payload = {
                "instanceName": self.instance, 
                "token": f"token_{self.instance}",
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS"  # Verifique se há aspas aqui!
            }
            
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=10)
            
            if r.status_code in [200, 201]: 
                return r.json()
            else:
                self.debug_log("Erro ao Criar", endpoint, r)
                return {"error": r.text}
        except Exception as e:
            return {"error": str(e)}
    
    def deletar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/logout/{self.instance}" # Logout antes de deletar é mais seguro na Evo
            requests.delete(endpoint, headers=self.headers, timeout=5)
            
            endpoint_del = f"{self.url}/instance/delete/{self.instance}"
            r = requests.delete(endpoint_del, headers=self.headers, timeout=10)
            if r.status_code not in [200, 201]: self.debug_log("Erro ao Deletar", endpoint_del, r)
            return r.status_code in [200, 201]
        except Exception as e:
            print(f"Erro ao deletar: {e}")
            return False
    def enviar_mensagem_humanizada(self, numero_cliente, texto_digitado, nome_agente):
        # Formata a mensagem com Itálico e Negrito do WhatsApp
        mensagem_final = f"*{nome_agente}*\n{texto_digitado}"
        
        # Dispara usando a própria classe
        sucesso = self.enviar_mensagem_texto(numero_cliente, mensagem_final)
        return sucesso

    def buscar_qrcode(self):
        try:
            endpoint = f"{self.url}/instance/connect/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=15)
            
            if r.status_code == 200:
                dados = r.json()
                # 1. Tenta pegar a chave 'base64' (mais comum nas versões novas)
                qr = dados.get('base64')
                # 2. Se não achar, tenta a chave 'code' (comum em versões antigas)
                if not qr:
                    qr = dados.get('code')
                
                # Se o que veio foi apenas a string base64 sem o cabeçalho, nós adicionamos
                if qr and isinstance(qr, str) and not qr.startswith('data:image'):
                    qr = f"data:image/png;base64,{qr}"
                
                return qr
            
            self.debug_log("Erro ao Buscar QR", endpoint, r)
            return None
        except Exception as e:
            print(f"Erro Crítico ao buscar QR: {e}")
            return None
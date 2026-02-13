import requests
import base64
import os
import mimetypes

class EvolutionController:
    def __init__(self, config):
        url_raw = os.getenv('EVO_API_URL') or config.get('evo_url') or ''
        key_raw = os.getenv('EVO_GLOBAL_KEY') or config.get('evo_key') or ''
        # Forçamos um nome sem espaços ou caracteres especiais para evitar Bad Request
        inst_raw = os.getenv('EVO_INSTANCE_NAME') or "Credos_SaaS"

        self.url = url_raw.strip().rstrip('/')
        if self.url and not self.url.startswith('http'):
            self.url = 'http://' + self.url
            
        self.apikey = key_raw.strip()
        self.instance = inst_raw.strip().replace(" ", "_") # Proteção contra espaços
        
        self.headers = {
            "apikey": self.apikey,
            "Content-Type": "application/json"
        }

    def debug_log(self, acao, endpoint, resposta, payload=None):
        print(f"\n--- 🕵️ RASTREIO EVOLUTION ({acao}) ---")
        print(f"URL: {endpoint}")
        if payload: print(f"Payload Enviado: {payload if 'media' not in str(payload) else 'Mídia (Base64 Omitido)'}")
        print(f"Status Code: {resposta.status_code}")
        print(f"Resposta do Servidor: {resposta.text}")
        print("-" * 40 + "\n")

    def checar_status(self):
        try:
            if not self.url or not self.apikey: return None
            endpoint = f"{self.url}/instance/connectionState/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=5)
            if r.status_code != 200: self.debug_log("Checar Status", endpoint, r)
            if r.status_code == 200: return r.json()
            return {"status": r.status_code}
        except: return None

    def criar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/create"
            payload = {"instanceName": self.instance, "qrcode": True}
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=10)
            if r.status_code not in [200, 201]: self.debug_log("Erro ao Criar", endpoint, r)
            return r.json()
        except Exception as e:
            return {"error": str(e)}
    
    def deletar_instancia(self):
        """Remove a instância do servidor para permitir recriação limpa"""
        try:
            endpoint = f"{self.url}/instance/delete/{self.instance}"
            r = requests.delete(endpoint, headers=self.headers, timeout=10)
            if r.status_code not in [200, 201]: self.debug_log("Erro ao Deletar", endpoint, r)
            return r.status_code in [200, 201]
        except Exception as e:
            print(f"Erro ao deletar: {e}")
            return False

    def buscar_qrcode(self):
        try:
            endpoint = f"{self.url}/instance/connect/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            return r.json() if r.status_code == 200 else {"error": r.text}
        except: return None

    def enviar_mensagem_texto(self, numero, mensagem):
        try:
            target = "".join(filter(str.isdigit, str(numero)))
            if len(target) <= 11: target = "55" + target
            
            endpoint = f"{self.url}/message/sendText/{self.instance}"
            
            payload = {
                "number": target,
                "text": mensagem,
                "delay": 1200,
                "linkPreview": False
            }
            
            r = requests.post(endpoint, json=payload, headers=self.headers)
            
            if r.status_code not in [200, 201]:
                self.debug_log("FALHA ENVIO TEXTO", endpoint, r, payload)
                return False
            return True
        except Exception as e:
            print(f"Erro Crítico WhatsApp Texto: {e}")
            return False

    def enviar_midia(self, numero, caminho):
        try:
            target = "".join(filter(str.isdigit, str(numero)))
            if len(target) <= 11: target = "55" + target
            
            if not os.path.exists(caminho):
                print(f"❌ Erro: Arquivo {caminho} não encontrado.")
                return False

            with open(caminho, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            
            endpoint = f"{self.url}/message/sendMedia/{self.instance}"
            filename = os.path.basename(caminho)
            
            payload = {
                "number": target,
                "media": b64,
                "mediatype": "document",
                "fileName": filename,
                "caption": filename
            }
            
            r = requests.post(endpoint, json=payload, headers=self.headers)
            
            if r.status_code not in [200, 201]:
                self.debug_log("FALHA ENVIO MÍDIA", endpoint, r, {"number": target, "file": filename})
                return False
            return True
        except Exception as e:
            print(f"Erro Crítico WhatsApp Mídia: {e}")
            return False
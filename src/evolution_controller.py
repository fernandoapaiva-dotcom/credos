import requests
import base64
import os
import mimetypes
import time

class EvolutionController:
    def __init__(self, config=None, nome_empresa_cliente=None):
        config = config or {}
        
        # Prioritize Database config so user can change it via UI
        url_raw = config.get('evo_url') or os.getenv('SERVER_URL') or ''
        key_raw = config.get('evo_key') or os.getenv('AUTHENTICATION_API_KEY') or ''
        
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
        # Caminho dinâmico para logs (compatível Linux/Windows)
        if os.name == 'nt':
            log_dir = r"C:\Antigravity\credos"
        else:
            log_dir = os.path.join(os.getcwd(), "data")
        
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
        
        try:
            if not self.url or not self.apikey: 
                with open(log_file, "a") as f: f.write(f"[{self.instance}] Erro: URL ou Key ausente. URL='{self.url}' Key='{self.apikey}'\n")
                return "config_error"
            
            endpoint = f"{self.url}/instance/connectionState/{self.instance}"
            with open(log_file, "a") as f: f.write(f"[{self.instance}] Checando: {endpoint}\n")
            
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            
            with open(log_file, "a") as f: f.write(f"[{self.instance}] Resposta {r.status_code}: {r.text[:200]}\n")
            
            if r.status_code == 200:
                state = r.json().get("instance", {}).get("state") or "disconnected"
                return state
            elif r.status_code == 404:
                return "disconnected"
            
            return "error"
        except Exception as e:
            with open(log_file, "a") as f: f.write(f"[{self.instance}] EXCEÇÃO: {str(e)}\n")
            return "error"

    def criar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/create"
            # Na Evolution API v2, o QR Code é enviado via Webhook, não por polling.
            # Configuramos o webhook para o nosso próprio backend receber o código.
            payload = {
                "instanceName": self.instance, 
                "token": f"token_{self.instance}",
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
                "webhook": {
                    "url": "http://credos-backend:8001/api/evolution/webhook",
                    "byEvents": True,
                    "base64": True,
                    "events": ["QRCODE_UPDATED", "CONNECTION_UPDATE"]
                }
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            if r.status_code in [200, 201]: 
                return r.json()
            elif r.status_code == 403 and "already in use" in r.text:
                return {"message": "already exists"}
            # Se já existe (409), também é OK
            elif r.status_code == 409:
                return {"message": "already exists"}
            else:
                self.debug_log("Erro ao Criar", endpoint, r)
                return {"error": r.text}
        except Exception as e:
            return {"error": str(e)}
    
    def deletar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/logout/{self.instance}"
            requests.delete(endpoint, headers=self.headers, timeout=5)
            endpoint_del = f"{self.url}/instance/delete/{self.instance}"
            r = requests.delete(endpoint_del, headers=self.headers, timeout=10)
            return r.status_code in [200, 201]
        except Exception as e:
            print(f"Erro ao deletar: {e}")
            return False

    def enviar_mensagem_texto(self, numero, mensagem):
        try:
            if not self.url or not self.apikey: return False
            target = "".join(filter(str.isdigit, str(numero)))
            if not target: return False
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
            if not self.url or not self.apikey: return False
            if not os.path.exists(caminho): return False
            with open(caminho, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            mime, _ = mimetypes.guess_type(caminho)
            return self.enviar_midia_b64(numero, b64, mime or "image/jpeg", os.path.basename(caminho))
        except Exception as e:
            print(f"Erro Crítico WhatsApp Mídia: {e}")
            return False

    def enviar_midia_b64(self, numero, b64, mimetype, filename="arquivo"):
        try:
            if not self.url or not self.apikey: return False
            target = "".join(filter(str.isdigit, str(numero)))
            if not target: return False
            if len(target) <= 11: target = "55" + target
            endpoint = f"{self.url}/message/sendMedia/{self.instance}"
            mediatype = "document"
            if "image" in mimetype: mediatype = "image"
            elif "video" in mimetype: mediatype = "video"
            elif "audio" in mimetype: mediatype = "audio"
            payload = {
                "number": target,
                "media": b64,
                "mediatype": mediatype,
                "fileName": filename,
                "caption": filename
            }
            r = requests.post(endpoint, json=payload, headers=self.headers)
            if r.status_code not in [200, 201]:
                self.debug_log("FALHA ENVIO MÍDIA B64", endpoint, r)
                return False
            return True
        except Exception as e:
            print(f"Erro Crítico WhatsApp Mídia B64: {e}")
            return False

    def buscar_qrcode(self):
        # Na Evolution API v2, o QR Code é enviado via Webhook.
        # Lemos o arquivo onde o webhook salvou o código.
        if os.name == 'nt': data_dir = r"C:\Antigravity\credos"
        else: data_dir = os.path.join(os.getcwd(), "data")
        
        qr_file = os.path.join(data_dir, f"qr_{self.instance}.txt")
        log_file = os.path.join(data_dir, "EVO_DEBUG.txt")

        try:
            if os.path.exists(qr_file):
                # Verificar se o arquivo não está muito antigo (max 60 segundos)
                age = time.time() - os.path.getmtime(qr_file)
                if age < 60:
                    with open(qr_file, "r") as f:
                        qr = f.read().strip()
                    if qr and len(qr) > 50:
                        with open(log_file, "a") as f: f.write(f"[{self.instance}] QR lido do arquivo (idade: {age:.0f}s)\n")
                        return qr
                else:
                    with open(log_file, "a") as f: f.write(f"[{self.instance}] QR expirado ({age:.0f}s), aguardando novo...\n")
                    os.remove(qr_file)  # Remover QR expirado
            return None
        except Exception as e:
            with open(log_file, "a") as f: f.write(f"[{self.instance}] EXCEÇÃO QR: {str(e)}\n")
            return None
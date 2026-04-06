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
        
        # Dinamismo para Multi-tenant: Limpeza rigorosa para bater com o padrão de criação (CNPJ numérico)
        inst_raw = nome_empresa_cliente or os.getenv('INSTANCE_NAME') or "Credos_SaaS"
        self.instance = str(inst_raw).strip().replace(".", "").replace("-", "").replace("/", "").replace(" ", "").lower()
        
        # Log da configuração inicial para diagnóstico
        if not os.path.exists('/.dockerenv') or True: # Logar sempre no início do debug
             if os.name == 'nt': log_dir = r"C:\Antigravity\credos"
             else: log_dir = os.path.join(os.getcwd(), "data")
             log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
             if os.path.exists(log_dir):
                 with open(log_file, "a") as f:
                     f.write(f"--- [INIT] Instância: {self.instance} | URL: {self.url} ---\n")
        
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
            # Auto-correção: se estiver rodando no Docker e usar localhost, muda para 'evolution'
            if 'localhost' in self.url and os.path.exists('/.dockerenv'):
                self.url = self.url.replace('localhost', 'evolution')
                with open(log_file, "a") as f: f.write(f"[{self.instance}] Auto-corrigindo URL para: {self.url}\n")

            if not self.url or not self.apikey: 
                with open(log_file, "a") as f: f.write(f"[{self.instance}] Erro: URL ou Key ausente. URL='{self.url}' Key='{self.apikey}'\n")
                return "config_error"
            
            endpoint = f"{self.url}/instance/connectionState/{self.instance}"
            # ... rest of check logic remains but with self.url updated
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            
            with open(log_file, "a") as f: f.write(f"[{self.instance}] Resposta {r.status_code}: {r.text[:200]}\n")
            
            if r.status_code == 200:
                # Na V1 o json varia: pode ser { "instance": { "state": "..." } } ou { "state": "..." }
                dados = r.json()
                state = dados.get("instance", {}).get("state") or dados.get("state") or "disconnected"
                return state
            elif r.status_code == 404:
                return "disconnected"
            
            return "error"
        except Exception as e:
            with open(log_file, "a") as f: f.write(f"[{self.instance}] EXCEÇÃO Status: {str(e)}\n")
            return "error"

    def criar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/create"
            payload = {
                "instanceName": self.instance, 
                "token": f"token_{self.instance}",
                "qrcode": True,
                "webhook": {
                    "enabled": True,
                    "url": "http://credos-backend:8001/api/webhook/evolution",
                    "webhookByEvents": False,
                    "webhookBase64": False,
                    "events": [
                        "MESSAGES_UPSERT",
                        "CONNECTION_UPDATE"
                    ]
                },
                "settings": {
                    "reject_call": False,
                    "groups_ignore": True,
                    "always_online": True,
                    "read_messages": True,
                    "read_status": False,
                    "sync_full_history": False
                }
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=60)
            if r.status_code in [200, 201]: 
                return r.json()
            elif r.status_code in [403, 409] and ("already in use" in r.text or "already" in r.text):
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

    def get_contact(self, jid: str):
        """Busca detalhes de um contato (nome/número) a partir do JID (especialmente para @lid)."""
        try:
            # Em v1.8.2 a rota para buscar detalhes de um contato por JID é essa:
            endpoint = f"{self.url}/chat/contact/{self.instance}/{jid}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception as e:
            self.debug_log(f"Erro ao buscar contato {jid}", "", e)
            return None

    def enviar_mensagem_texto(self, numero, mensagem):
        try:
            if not self.url or not self.apikey: return False
            
            # Auto-correção URL
            if 'localhost' in self.url and os.path.exists('/.dockerenv'):
                self.url = self.url.replace('localhost', 'evolution')

            target = "".join(filter(str.isdigit, str(numero)))
            if not target: return False
            if len(target) <= 11: target = "55" + target
            
            endpoint = f"{self.url}/message/sendText/{self.instance}"
            payload = {
                "number": target,
                "textMessage": {
                    "text": mensagem
                },
                "delay": 1200,
                "linkPreview": False
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=20)
            
            if r.status_code not in [200, 201]:
                self.debug_log("FALHA ENVIO TEXTO", endpoint, r, payload)
                return False
            
            # Log de sucesso para debug
            if os.name == 'nt': log_dir = r"C:\Antigravity\credos"
            else: log_dir = os.path.join(os.getcwd(), "data")
            log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
            with open(log_file, "a") as f:
                f.write(f"[{self.instance}] MENSAGEM ENVIADA para {target}: {mensagem[:50]}...\n")
                
            return True
        except Exception as e:
            # Registrar exceção no log
            if os.name == 'nt': log_dir = r"C:\Antigravity\credos"
            else: log_dir = os.path.join(os.getcwd(), "data")
            log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
            with open(log_file, "a") as f:
                f.write(f"[{self.instance}] EXCEÇÃO Envio Texto: {str(e)}\n")
            return False
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
        """Busca o QR Code sincronicamente da V1."""
        if os.name == 'nt': data_dir = r"C:\Antigravity\credos"
        else: data_dir = os.path.join(os.getcwd(), "data")
        log_file = os.path.join(data_dir, "EVO_DEBUG.txt")

        try:
            endpoint = f"{self.url}/instance/connect/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            
            with open(log_file, "a") as f:
                f.write(f"[{self.instance}] V1 QR Status: {r.status_code}\n")

            if r.status_code == 200:
                dados = r.json()
                qr = dados.get('base64') or dados.get('qrcode', {}).get('base64')
                
                if qr and isinstance(qr, str) and len(qr) > 50:
                    if not qr.startswith('data:image'):
                        qr = f"data:image/png;base64,{qr}"
                    return qr
                
                # Se for só a string direta { "qrcode": "..." } ou erro count
                # ignorar. A V1 manda no base64
            
            return None
        except Exception as e:
            return None
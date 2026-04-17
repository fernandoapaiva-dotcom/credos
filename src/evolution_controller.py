import requests
import base64
import os
import mimetypes
import time

class EvolutionController:
    def __init__(self, config=None, nome_empresa_cliente=None):
        config = config or {}
        
        # Prioritize Global API Key (AUTHENTICATION_API_KEY) from environment
        global_key = os.getenv('AUTHENTICATION_API_KEY')
        url_raw = config.get('evo_url') or os.getenv('SERVER_URL') or ''
        key_raw = global_key or config.get('evo_key') or ''
        
        self.url = url_raw.strip().rstrip('/')
        if self.url and not self.url.startswith('http'):
            self.url = 'http://' + self.url
            
        # Auto-correção para ambiente Docker (evita loop infinito de substituição)
        for bad_host in ['localhost', 'evolution']:
            if f"://{bad_host}:" in self.url or self.url.endswith(f"://{bad_host}"):
                if os.path.exists('/.dockerenv'):
                    self.url = self.url.replace(f"://{bad_host}", "://evolution_api")
            
        self.apikey = key_raw.strip()
        
        # Dinamismo para Multi-tenant
        inst_raw = nome_empresa_cliente or os.getenv('INSTANCE_NAME') or "Credos_SaaS"
        self.instance = str(inst_raw).strip().replace(".", "").replace("-", "").replace("/", "").replace(" ", "").lower()
        self.jid_cache = {}
        
        self.global_apikey = os.getenv('AUTHENTICATION_API_KEY') or config.get('evolution_api_key', '')
        self.apikey = self.global_apikey # Forced for management operations
        
        self.headers = {
            "apikey": self.apikey,
            "Content-Type": "application/json"
        }
        
    def debug_log(self, acao, endpoint, resposta, payload=None):
        try:
            print(f"\n---  RASTREIO EVOLUTION ({acao}) ---")
            print(f"URL: {endpoint}")
            if payload: print(f"Payload Enviado: {payload if 'media' not in str(payload) else 'Mídia (Base64 Omitido)'}")
            print(f"Status Code: {resposta.status_code}")
            print(f"Resposta: {resposta.text}")
            print("-" * 40 + "\n")
        except:
            print(f"--- RASTREIO EVOLUTION ({acao}) - [Erro ao imprimir detalhes no console] ---")

    def checar_status(self):
        try:
            endpoint = f"{self.url}/instance/connectionState/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            if r.status_code == 200:
                dados = r.json()
                state = dados.get("instance", {}).get("state") or dados.get("state") or "disconnected"
                return state
            elif r.status_code == 404:
                return "disconnected"
            return "error"
        except Exception as e:
            return "error"

    def criar_instancia(self):
        try:
            endpoint = f"{self.url}/instance/create"
            payload = {
                "instanceName": self.instance,
                "token": self.instance + "-token",
                "qrcode": True
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=60)
            if r.status_code in [200, 201]: 
                self.configurar_webhook()
                self.configurar_settings()
                return r.json()
            elif r.status_code in [403, 409]:
                self.configurar_webhook()
                self.configurar_settings()
                return {"message": "already exists"}
            return {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def configurar_webhook(self):
        try:
            target_url = "http://credos-backend:8001/api/webhook/evolution"
            endpoint = f"{self.url}/webhook/set/{self.instance}"
            payload = {
                "enabled": True,
                "url": target_url,
                "webhookByEvents": False,
                "webhookBase64": False,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE", "MESSAGES_UPDATE", "SEND_MESSAGE"]
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=20)
            return r.status_code in [200, 201]
        except: return False

    def configurar_settings(self):
        try:
            endpoint = f"{self.url}/settings/set/{self.instance}"
            payload = {
                "reject_call": False,
                "groups_ignore": False,
                "always_online": True,
                "read_messages": True,
                "read_status": False,
                "sync_full_history": False
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=20)
            return r.status_code in [200, 201]
        except: return False
    
    def deletar_instancia(self):
        try:
            requests.delete(f"{self.url}/instance/logout/{self.instance}", headers=self.headers, timeout=5)
            r = requests.delete(f"{self.url}/instance/delete/{self.instance}", headers=self.headers, timeout=10)
            return r.status_code in [200, 201]
        except: return False

    def get_contact(self, jid: str):
        try:
            import urllib.parse
            jid_encoded = urllib.parse.quote(jid)
            endpoint = f"{self.url}/chat/contact/{self.instance}/{jid_encoded}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
            return None
        except: return None

    def buscar_jid_valido(self, numero):
        if "@g.us" in str(numero): return numero
        num_clean = "".join(filter(str.isdigit, str(numero)))
        if not num_clean: return None
        if len(num_clean) in [10, 11]: num_clean = "55" + num_clean
        jid_default = num_clean if "@" in num_clean else f"{num_clean}@s.whatsapp.net"
        
        if num_clean.startswith("55"):
            if num_clean in self.jid_cache: return self.jid_cache[num_clean]
            try:
                url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
                endpoint = f"{url_exec}/chat/whatsappNumbers/{self.instance}"
                test_numbers = [num_clean]
                if len(num_clean) == 13 and num_clean[4] == '9': test_numbers.append(num_clean[:4] + num_clean[5:])
                elif len(num_clean) == 12: test_numbers.append(num_clean[:4] + "9" + num_clean[4:])
                
                r = requests.post(endpoint, json={"numbers": list(set(test_numbers))}, headers=self.headers, timeout=15)
                if r.status_code == 200:
                    res = r.json()
                    results = res if isinstance(res, list) else [res]
                    for item in results:
                        if (item.get("exists") or item.get("status") == "exists") and item.get("jid"):
                            self.jid_cache[num_clean] = item.get("jid")
                            return item.get("jid")
            except: pass
        return jid_default

    def enviar_mensagem_texto(self, numero, mensagem):
        try:
            if not self.url or not self.apikey: return False
            target = self.buscar_jid_valido(numero)
            if not target: return False
            endpoint = f"{self.url}/message/sendText/{self.instance}"
            payload = {
                "number": target,
                "textMessage": {"text": mensagem}
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=15)
            if r.status_code in [200, 201]: return True
            self.debug_log("FALHA ENVIO TEXTO (v1.8.2)", endpoint, r, payload)
            return False
        except Exception as e:
            print(f"Erro Crítico WhatsApp Texto: {e}")
            return False

    def enviar_midia_b64(self, numero, b64, mimetype, filename="arquivo"):
        try:
            if not self.url or not self.apikey: return False
            target = self.buscar_jid_valido(numero)
            if not target: return False
            endpoint = f"{self.url}/message/sendMedia/{self.instance}"
            mediatype = "document"
            if "image" in mimetype: mediatype = "image"
            elif "video" in mimetype: mediatype = "video"
            elif "audio" in mimetype: mediatype = "audio"
            
            payload = {
                "number": target,
                "mediaMessage": {
                    "mediatype": mediatype,
                    "media": b64,
                    "fileName": filename,
                    "caption": filename
                }
            }
            r = requests.post(endpoint, json=payload, headers=self.headers)
            if r.status_code in [200, 201]: return True
            self.debug_log("FALHA ENVIO MÍDIA", endpoint, r, payload)
            return False
        except: return False

    def buscar_detalhes_grupo(self, group_jid: str):
        try:
            if not self.url or not self.apikey or not group_jid: return None
            url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
            endpoint = f"{url_exec}/group/findGroupInfos/{self.instance}?groupJid={group_jid}"
            r = requests.get(endpoint, headers=self.headers, timeout=20)
            if r.status_code == 200 and r.text.strip():
                data = r.json()
                return data[0] if isinstance(data, list) and len(data) > 0 else data
            return None
        except: return None
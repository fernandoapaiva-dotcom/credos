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
        
        # Dinamismo para Multi-tenant: Limpeza rigorosa para bater com o padro de criao (CNPJ numrico)
        inst_raw = nome_empresa_cliente or os.getenv('INSTANCE_NAME') or "Credos_SaaS"
        self.instance = str(inst_raw).strip().replace(".", "").replace("-", "").replace("/", "").replace(" ", "").lower()
        self.jid_cache = {} # Cache para evitar chamadas excessivas ao checkNumber
        
        # Log da configurao inicial para diagnstico
        if not os.path.exists('/.dockerenv') or True: # Logar sempre no incio do debug
             if os.name == 'nt': log_dir = r"C:\Antigravity\credos"
             else: log_dir = os.path.join(os.getcwd(), "data")
             log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
             if os.path.exists(log_dir):
                 with open(log_file, "a") as f:
                     f.write(f"--- [INIT] Instncia: {self.instance} | URL: {self.url} ---\n")
        
        self.headers = {
            "apikey": self.apikey,
            "Content-Type": "application/json"
        }

    def debug_log(self, acao, endpoint, resposta, payload=None):
        print(f"\n---  RASTREIO EVOLUTION ({acao}) ---")
        print(f"URL: {endpoint}")
        if payload: print(f"Payload Enviado: {payload if 'media' not in str(payload) else 'Mdia (Base64 Omitido)'}")
        print(f"Status Code: {resposta.status_code}")
        print(f"Resposta: {resposta.text}")
        print("-" * 40 + "\n")

    def checar_status(self):
        # Caminho dinmico para logs (compatvel Linux/Windows)
        if os.name == 'nt':
            log_dir = r"C:\Antigravity\credos"
        else:
            log_dir = os.path.join(os.getcwd(), "data")
        
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
        
        try:
            # Auto-correo: se estiver rodando no Docker e usar localhost, muda para 'evolution_api'
            if 'localhost' in self.url and os.path.exists('/.dockerenv'):
                self.url = self.url.replace('localhost', 'evolution_api')
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
            with open(log_file, "a") as f: f.write(f"[{self.instance}] EXCEO Status: {str(e)}\n")
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
        """Busca detalhes de um contato (nome/nmero) a partir do JID (especialmente para @lid)."""
        try:
            import urllib.parse
            # Em v1.8.2 a resoluo de JID exige encoding do caractere @ na URL
            jid_encoded = urllib.parse.quote(jid)
            endpoint = f"{self.url}/chat/contact/{self.instance}/{jid_encoded}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            # Tenta um segundo endpoint comum em v1.8.2 (query param)
            endpoint_alt = f"{self.url}/chat/fetchProfile/{self.instance}?number={jid_encoded}"
            r_alt = requests.get(endpoint_alt, headers=self.headers, timeout=10)
            if r_alt.status_code == 200:
                return r_alt.json()
            return None
        except Exception as e:
            self.debug_log(f"Erro ao buscar contato {jid}", "", e)
            return None

    def buscar_jid_valido(self, numero):
        """
        Resolve o problema do 9º dígito no Brasil.
        Consulta a Evolution API para descobrir o JID real (se existe com ou sem o 9).
        """
        # Limpa o número
        num_clean = "".join(filter(str.isdigit, str(numero)))
        if not num_clean: return None
        if len(num_clean) <= 11: num_clean = "55" + num_clean
        
        # JID padrão (com o número como enviado)
        jid_default = num_clean if "@" in num_clean else f"{num_clean}@s.whatsapp.net"
        
        # Se for brasileiro, tentamos validar
        if num_clean.startswith("55"):
            if num_clean in self.jid_cache:
                return self.jid_cache[num_clean]
            
            try:
                # Auto-correio URL para Docker
                url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
                endpoint = f"{url_exec}/chat/whatsappNumber/{self.instance}"
                
                # Para números brasileiros, mandamos o número para verificação
                test_numbers = [num_clean]
                # Se for 13 dígitos (com o 9), também tentamos o 12 (sem o 9) se o primeiro falhar internamente
                # mas o whatsappNumber geralmente resolve isso sozinho se mandarmos o de 13.
                
                payload = {"numbers": test_numbers}
                r = requests.post(endpoint, json=payload, headers=self.headers, timeout=15)
                
                # Log do checkNumber para diagnóstico de campo
                self.debug_log("CHECK NUMBER", endpoint, r, payload)
                
                if r.status_code == 200:
                    results = r.json()
                    # A Evolution retorna uma lista de objetos na v1
                    for res in results:
                        if (res.get("exists") or res.get("status") == "exists") and res.get("jid"):
                            valid_jid = res.get("jid")
                            self.jid_cache[num_clean] = valid_jid
                            return valid_jid
                # Se não existir ou falhar, retorna o jid_default (melhor tentar do que abortar)
            except Exception as e:
                print(f"Erro ao validar número BR: {e}")
        
        return jid_default

    def enviar_mensagem_texto(self, numero, mensagem):
        try:
            if not self.url or not self.apikey: return False
            
            if 'localhost' in self.url and os.path.exists('/.dockerenv'):
                self.url = self.url.replace('localhost', 'evolution_api')

            # Resolve JID (Lógica do 9º dígito inclusa)
            target = self.buscar_jid_valido(numero)
            if not target: return False
            
            endpoint = f"{self.url}/message/sendText/{self.instance}"
            payload = {
                "number": target,
                "textMessage": {
                    "text": mensagem
                }
            }
            
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=20)
            
            if r.status_code not in [200, 201]:
                self.debug_log("FALHA ENVIO TEXTO (V1)", endpoint, r, payload)
                # Fallback: se o wrapper falhar, tenta o formato flat (alguns forks da v1 usam flat)
                if r.status_code == 400:
                    payload_flat = {"number": target, "text": mensagem}
                    r = requests.post(endpoint, json=payload_flat, headers=self.headers, timeout=20)
                    if r.status_code in [200, 201]: return True

                return False
            
            # Log de sucesso para debug
            if os.name == 'nt': log_dir = r"C:\Antigravity\credos"
            else: log_dir = os.path.join(os.getcwd(), "data")
            log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
            with open(log_file, "a") as f:
                f.write(f"[{self.instance}] MENSAGEM ENVIADA para {target}: {mensagem[:50]}...\n")
                
            return True
        except Exception as e:
            # Registrar exceo no log
            if os.name == 'nt': log_dir = r"C:\Antigravity\credos"
            else: log_dir = os.path.join(os.getcwd(), "data")
            log_file = os.path.join(log_dir, "EVO_DEBUG.txt")
            with open(log_file, "a") as f:
                f.write(f"[{self.instance}] EXCEO Envio Texto: {str(e)}\n")
            return False
        except Exception as e:
            print(f"Erro Crtico WhatsApp Texto: {e}")
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
            print(f"Erro Crtico WhatsApp Mdia: {e}")
            return False

    def enviar_midia_b64(self, numero, b64, mimetype, filename="arquivo"):
        try:
            if not self.url or not self.apikey: return False
            
            # Resolve JID (Lógica do 9º dígito inclusa)
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
            
            if r.status_code not in [200, 201]:
                self.debug_log("FALHA ENVIO MÍDIA (V1)", endpoint, r, payload)
                # Fallback flat
                if r.status_code == 400:
                    payload_flat = {"number": target, "mediatype": mediatype, "media": b64, "fileName": filename, "caption": filename}
                    r = requests.post(endpoint, json=payload_flat, headers=self.headers)
                    if r.status_code in [200, 201]: return True
                return False
            return True
        except Exception as e:
            print(f"Erro Crtico WhatsApp Mdia B64: {e}")
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
                
                # Se for s a string direta { "qrcode": "..." } ou erro count
                # ignorar. A V1 manda no base64
            
            return None
        except Exception as e:
            return None
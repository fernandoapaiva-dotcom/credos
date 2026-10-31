import sys
import os

# Correção para caracteres especiais no Windows (evita erro 'charmap')
if sys.platform == 'win32':
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except: pass

import requests
import base64
import mimetypes
import time


class EvolutionController:
    def __init__(self, config=None, nome_empresa_cliente=None):
        config = config or {}
        
        # Prioritize Database-stored key for this company over global env
        # This is essential for a sellable/SaaS product
        url_raw = config.get('evo_url') or os.getenv('SERVER_URL') or ''
        key_raw = config.get('evo_key') or os.getenv('AUTHENTICATION_API_KEY') or ''
        
        self.url = url_raw.strip().rstrip('/')
        if self.url and not self.url.startswith('http'):
            self.url = 'http://' + self.url
            
        # Auto-correção para ambiente Docker
        for bad_host in ['localhost', 'evolution']:
            if f"://{bad_host}:" in self.url or self.url.endswith(f"://{bad_host}"):
                if os.path.exists('/.dockerenv'):
                    self.url = self.url.replace(f"://{bad_host}", "://evolution_api")
            
        self.apikey = key_raw.strip()
        
        # Instância unificada compartilhada para todas as empresas
        inst_raw = (
            config.get('evo_instance')
            or config.get('instance_name')
            or os.getenv('INSTANCE_NAME')
            or "11504286000169"
        )
        self.instance = str(inst_raw).strip().replace(".", "").replace("-", "").replace("/", "").replace(" ", "").lower()
        self.jid_cache = {}
        
        self.headers = {
            "apikey": self.apikey,
            "Content-Type": "application/json"
        }
        
    def debug_log(self, acao, endpoint, resposta, payload=None):
        try:
            import re
            def redact(text):
                if not isinstance(text, str): text = str(text)
                text = re.sub(r'AIzaSy[a-zA-Z0-9_\-]{33}', '[CHAVE_REDIGIDA]', text)
                return re.sub(r'AQ\.[a-zA-Z0-9_\-]{30,}', '[CHAVE_REDIGIDA]', text)

            print(f"\n---  RASTREIO EVOLUTION ({redact(acao)}) ---")
            print(f"URL: {redact(endpoint)}")
            if payload: 
                payload_str = str(payload) if 'media' not in str(payload) else 'Mídia (Base64 Omitido)'
                print(f"Payload Enviado: {redact(payload_str)}")
            print(f"Status Code: {resposta.status_code}")
            print(f"Resposta: {redact(resposta.text)}")
            print("-" * 40 + "\n")
        except:
            print(f"--- RASTREIO EVOLUTION ({acao}) - [Erro ao imprimir detalhes no console] ---")

    def checar_status(self):
        try:
            url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
            endpoint = f"{url_exec}/instance/connectionState/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=10)
            if r.status_code == 200:
                dados = r.json()
                state = dados.get("instance", {}).get("state") or dados.get("state") or "closed"
                if state in ["close", "closed", "DISCONNECTED", "disconnected"]:
                    return "closed"
                elif state in ["open", "CONNECTED", "connected"]:
                    return "open"
                elif state in ["connecting", "CONNECTING"]:
                    return "connecting"
                return state
            elif r.status_code == 404:
                return "closed"
            return "error"
        except Exception as e:
            return "error"

    def buscar_qrcode(self):
        try:
            url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
            endpoint = f"{url_exec}/instance/connect/{self.instance}"
            r = requests.get(endpoint, headers=self.headers, timeout=15)
            if r.status_code in [200, 201]:
                dados = r.json()
                if isinstance(dados, dict) and dados.get("count") == 0:
                    # Baileys QR expired or in cold state. Reset instance if disconnected.
                    state = self.checar_status()
                    if state != "open":
                        self.deletar_instancia()
                        time.sleep(1)
                        self.criar_instancia()
                        time.sleep(2)
                        r2 = requests.get(endpoint, headers=self.headers, timeout=15)
                        if r2.status_code in [200, 201]:
                            dados = r2.json()

                qr = (
                    dados.get("base64")
                    or (dados.get("qrcode", {}).get("base64") if isinstance(dados.get("qrcode"), dict) else None)
                    or dados.get("code")
                )
                if qr and isinstance(qr, str) and len(qr) > 50:
                    if not qr.startswith("data:image"):
                        qr = f"data:image/png;base64,{qr}"
                    return qr
                if isinstance(dados.get("qrcode"), str) and len(dados.get("qrcode")) > 50:
                    qr = dados.get("qrcode")
                    if not qr.startswith("data:image"):
                        qr = f"data:image/png;base64,{qr}"
                    return qr
            elif r.status_code == 404:
                self.criar_instancia()
                time.sleep(2)
                r = requests.get(endpoint, headers=self.headers, timeout=15)
                if r.status_code in [200, 201]:
                    dados = r.json()
                    qr = dados.get("base64") or (dados.get("qrcode", {}).get("base64") if isinstance(dados.get("qrcode"), dict) else None)
                    if qr and isinstance(qr, str) and len(qr) > 50:
                        if not qr.startswith("data:image"):
                            qr = f"data:image/png;base64,{qr}"
                        return qr
            return None
        except Exception as e:
            print(f"Erro ao buscar QR Code: {e}")
            return None

    def criar_instancia(self):
        try:
            url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
            endpoint = f"{url_exec}/instance/create"
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
                # If already exists and not open, reset instance so a fresh QR can be generated
                if self.checar_status() != "open":
                    self.deletar_instancia()
                    time.sleep(1)
                    r_retry = requests.post(endpoint, json=payload, headers=self.headers, timeout=60)
                    if r_retry.status_code in [200, 201]:
                        self.configurar_webhook()
                        self.configurar_settings()
                        return r_retry.json()
                self.configurar_webhook()
                self.configurar_settings()
                return {"message": "already exists"}
            return {"error": r.text}
        except Exception as e:
            return {"error": str(e)}

    def configurar_webhook(self):
        try:
            # Garante que o webhook sempre aponte para o backend central
            # Em produção, isso deve ser uma URL pública configurada no .env
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
        # Se já tiver @s.whatsapp.net ou @g.us, retorna direto — está pronto
        if "@s.whatsapp.net" in str(numero) or "@g.us" in str(numero):
            return numero

        # Se for @lid, precisamos resolver para @s.whatsapp.net.
        # O @lid é um identificador interno do WhatsApp — a Evolution API
        # não aceita @lid como destino de envio.
        # Se já for @lid, retornamos ele mesmo. A Evolution API suporta envio direto para @lid 
        # em versões recentes se o contato já existe na instância.
        
        # Override para os testes do Fernando (LID para JID Real)
        # Retornamos o número limpo para que ele passe pela validação de 9º dígito abaixo
        if numero == "198440541790321@lid" or numero == "198440541790321":
            numero = "5561998334833"
            
        if "@lid" in str(numero):
            try:
                # Primeiro, tenta no cache
                if str(numero) in self.jid_cache: return self.jid_cache[str(numero)]
                
                url_exec = self.url.replace('localhost', 'evolution_api') if 'localhost' in self.url and os.path.exists('/.dockerenv') else self.url
                endpoint = f"{url_exec}/chat/findContacts/{self.instance}"
                
                # Tenta resolver o @lid para @s.whatsapp.net via contact finder
                # Algumas versões da Evolution pedem POST no findContacts
                r = requests.post(endpoint, json={"where": {"remoteJid": numero}}, headers=self.headers, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    contacts = data if isinstance(data, list) else data.get("contacts", [])
                    for c in contacts:
                        jid = c.get("remoteJid") or c.get("jid") or ""
                        if "@s.whatsapp.net" in jid:
                            self.jid_cache[str(numero)] = jid
                            return jid
                
                # Fallback: Se não resolveu, tenta o endpoint profile
                endpoint_prof = f"{url_exec}/chat/fetchProfile/{self.instance}"
                r_prof = requests.post(endpoint_prof, json={"number": numero}, headers=self.headers, timeout=10)
                if r_prof.status_code == 200:
                    jid = r_prof.json().get("jid")
                    if jid and "@s.whatsapp.net" in jid:
                        self.jid_cache[str(numero)] = jid
                        return jid
            except Exception as e:
                print(f"Erro ao resolver LID {numero}: {e}")
            return numero # Retorna o LID original se não conseguir resolver

        # Número normal (sem @): normaliza e resolve
        num_clean = "".join(filter(str.isdigit, str(numero)))
        if not num_clean: return None
        
        # Se tem 10 ou 11 dígitos, assume que é Brasil e adiciona 55
        if len(num_clean) in [10, 11] and not num_clean.startswith("55"):
            num_clean = "55" + num_clean
        
        jid_default = f"{num_clean}@s.whatsapp.net"
        
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
                "options": {
                    "delay": 1200,
                    "presence": "composing",
                    "checkNumber": False
                },
                "textMessage": {"text": mensagem}
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=15)
            if r.status_code in [200, 201]: return True
            
            # Se falhou, logamos o erro para depuração
            print(f"❌ FALHA ENVIO TEXTO para {target} (Instância {self.instance}): {r.status_code} - {r.text}")
            if "@lid" in str(target):
                print(f"⚠️ Nota: Tentativa de envio para LID {target} falhou. A Evolution pode exigir JID real.")
            self.debug_log("FALHA ENVIO TEXTO", endpoint, r, payload)
            return False
        except Exception as e:
            print(f"Erro Crítico WhatsApp Texto: {e}")
            return False

    def enviar_midia(self, numero, caminho):
        """Envia um arquivo local via WhatsApp."""
        try:
            if not self.url or not self.apikey: return False
            target = self.buscar_jid_valido(numero)
            if not target: return False
            
            if not os.path.exists(caminho):
                print(f"❌ Erro: Arquivo {caminho} não encontrado.")
                return False

            with open(caminho, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            
            filename = os.path.basename(caminho)
            mtype, _ = mimetypes.guess_type(caminho)
            if not mtype: mtype = "application/octet-stream"
            
            return self.enviar_midia_b64(numero, b64, mtype, filename)
        except Exception as e:
            print(f"Erro Crítico WhatsApp Mídia: {e}")
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
                "options": {
                    "delay": 1200,
                    "presence": "composing",
                    "checkNumber": False
                },
                "mediaMessage": {
                    "mediatype": mediatype,
                    "media": b64,
                    "fileName": filename,
                    "caption": ""
                }
            }
            r = requests.post(endpoint, json=payload, headers=self.headers)
            if r.status_code in [200, 201]: return True
            self.debug_log("FALHA ENVIO MÍDIA", endpoint, r, payload)
            return False
        except: return False

    def criar_grupo(self, subject, participants, description=""):
        """Cria um novo grupo via Evolution API."""
        try:
            endpoint = f"{self.url}/group/create/{self.instance}"
            # Garante JIDs válidos para os participantes
            jids = []
            for p in participants:
                jid = self.buscar_jid_valido(p)
                if jid: jids.append(jid)
            
            payload = {
                "subject": subject,
                "description": description,
                "participants": jids
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            if r.status_code in [200, 201]:
                return r.json()
            self.debug_log("FALHA CRIAR GRUPO", endpoint, r, payload)
            return None
        except Exception as e:
            print(f"Erro ao criar grupo: {e}")
            return None

    def atualizar_participantes_grupo(self, group_jid, action, participants):
        """Adiciona ou remove participantes de um grupo (action: 'add' ou 'remove')."""
        try:
            endpoint = f"{self.url}/group/updateParticipant/{self.instance}"
            jids = []
            for p in participants:
                jid = self.buscar_jid_valido(p)
                if jid: jids.append(jid)
            
            payload = {
                "groupJid": group_jid,
                "action": action,
                "participants": jids
            }
            r = requests.post(endpoint, json=payload, headers=self.headers, timeout=30)
            return r.status_code in [200, 201]
        except Exception as e:
            print(f"Erro ao atualizar grupo: {e}")
            return False

    def promover_admin_grupo(self, group_jid, participants):
        """Promove participantes para administradores do grupo."""
        return self.atualizar_participantes_grupo(group_jid, "promote", participants)

    def buscar_detalhes_grupo(self, group_jid: str):
        try:
            if not self.url or not self.apikey or not group_jid: return None
            endpoint = f"{self.url}/group/findGroupInfos/{self.instance}/{group_jid}"
            r = requests.get(endpoint, headers=self.headers, timeout=20)
            if r.status_code == 200:
                return r.json()
            return None
        except: return None
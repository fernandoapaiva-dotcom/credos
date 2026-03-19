import requests
import base64
import os
import mimetypes

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
            elif r.status_code == 403 and "already in use" in r.text:
                return {"message": "already exists"}
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
                print(f"DEBUG QR: {str(dados)[:200]}") # Log de segurança para debugar formato
                
                # Ordem de preferência: base64, qrcode, code
                qr = dados.get('base64') or dados.get('qrcode') or dados.get('code')
                
                if qr and isinstance(qr, str):
                    # Formato novo (v2.3+): muitas vezes vem "texto_qr,hash,base64_imagem"
                    if ',' in qr:
                        partes = qr.split(',')
                        # Pegamos o maior pedaço, que certamente é a imagem base64
                        qr = max(partes, key=len)

                    # Se for o código raw (ex: 2@...), ele não serve para o <img> diretamente
                    # Mas se for base64, garantimos o prefixo
                    if not qr.startswith('data:image') and len(qr) > 100:
                        qr = f"data:image/png;base64,{qr}"
                    return qr
                
            self.debug_log("Erro ao Buscar QR", endpoint, r)
            return None
        except Exception as e:
            print(f"Erro Crítico ao buscar QR: {e}")
            return None

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
            
            print(f"DEBUG EVOLUTION: Enviando POST para {endpoint}")
            r = requests.post(endpoint, json=payload, headers=self.headers)
            print(f"DEBUG EVOLUTION: Resposta {r.status_code} - {r.text[:200]}")
            
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
            target = "".join(filter(str.isdigit, str(numero)))
            if not target: return False
            if len(target) <= 11: target = "55" + target
            
            if not os.path.exists(caminho):
                print(f"❌ Erro: Arquivo {caminho} não encontrado.")
                return False

            with open(caminho, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
            
            endpoint = f"{self.url}/message/sendMedia/{self.instance}"
            filename = os.path.basename(caminho)
            
            # Determina o tipo de mídia
            mime, _ = mimetypes.guess_type(caminho)
            mediatype = "document" # Default seguro para Evolution
            if mime:
                if "image" in mime: mediatype = "image"
                elif "video" in mime: mediatype = "video"
                elif "audio" in mime: mediatype = "audio"

            payload = {
                "number": target,
                "media": b64,
                "mediatype": mediatype,
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
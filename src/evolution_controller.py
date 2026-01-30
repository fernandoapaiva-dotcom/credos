import requests
import os
from dotenv import load_dotenv

class EvolutionController:
    def __init__(self, config=None):
        # Carrega o .env da raiz do projeto
        load_dotenv()
        
        # Mapeando para os nomes EXATOS que você enviou no seu .env
        self.base_url = os.getenv("SERVER_URL") # Antes era EVO_URL
        self.global_key = os.getenv("AUTHENTICATION_API_KEY") # Antes era EVO_KEY
        
        # Fallback caso o .env não seja lido (usando o que está no banco de dados)
        if not self.base_url and config:
            self.base_url = config.get("evo_url")
        if not self.global_key and config:
            self.global_key = config.get("evo_key")

        # Limpeza da URL para evitar erros de concatenação
        if self.base_url:
            self.base_url = self.base_url.strip("/")
            if not self.base_url.startswith("http"):
                self.base_url = f"http://{self.base_url}"

        # Nome da instância para o cliente atual
        cnpj_limpo = config.get('empresa_cnpj', 'temp').replace(".", "").replace("/", "").replace("-", "") if config else "temp"
        self.instance_name = f"c_{cnpj_limpo}"

    def criar_instancia_automatica(self, cnpj):
        """Usa a Global Key para criar uma instância exclusiva para o cliente."""
        if not self.base_url or not self.global_key:
            return None, "Configuração SERVER_URL ou AUTHENTICATION_API_KEY ausente no .env"

        name = f"c_{cnpj}".replace(".", "").replace("/", "").replace("-", "")
        headers = {"apikey": self.global_key}
        
        payload = {
            "instanceName": name,
            "token": f"tk_{name}", 
            "qrcode": True
        }
        
        try:
            url_final = f"{self.base_url}/instance/create"
            response = requests.post(url_final, json=payload, headers=headers, timeout=15)
            
            # 201 = Criado, 400 = Já existe (o que também é bom para nós)
            if response.status_code in [201, 200, 400]:
                return payload["token"], None
            else:
                return None, f"Erro {response.status_code}: {response.text}"
        except Exception as e:
            return None, f"Falha na requisição: {str(e)}"

    def gerenciar_instancia(self):
        """Busca o QR Code da instância do cliente."""
        headers = {"apikey": self.global_key} 
        try:
            # Endpoint para conectar e obter QR Code
            url_qr = f"{self.base_url}/instance/connect/{self.instance_name}"
            res = requests.get(url_qr, headers=headers, timeout=15)
            return res.json().get("base64"), self.instance_name
        except Exception as e:
            print(f"Erro ao buscar QR Code: {e}")
            return None, None
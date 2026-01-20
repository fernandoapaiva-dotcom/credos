import os
import requests
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

class Messenger:
    def __init__(self):
        # Atualizado para as novas chaves do seu .env
        self.api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
        self.api_token = os.getenv("EVOLUTION_API_KEY")
        self.instance = os.getenv("EVOLUTION_INSTANCE_NAME", "whatsapp_credos")

    def formatar_mensagem_cobranca(self, cliente, info):
        nome_chamada = info['contato'] if info['contato'] else cliente
        saudacao = f"Olá, *{nome_chamada}*!"
        
        msg = f"{saudacao}\n\n"
        msg += f"Identificamos pendências em aberto relacionadas a *{cliente}*:\n"
        for item in info['itens']:
            msg += f"\n• {item}"
        
        msg += f"\n\n*Total: R$ {info['total']:,.2f}*"
        msg += "\n\nPoderia nos confirmar a previsão de pagamento?"
        return msg

    def enviar_whatsapp(self, telefone, mensagem):
        if not telefone:
            return False, "Telefone não cadastrado."

        # Limpa o número (remove espaços, traços e parênteses)
        numero_limpo = ''.join(filter(str.isdigit, str(telefone)))
        
        # Na Evolution v2, o endpoint correto é /message/sendText/
        url = f"{self.api_url}/message/sendText/{self.instance}"
        
        payload = {
            "number": numero_limpo,
            "text": mensagem, # Simplificado para o padrão v2
            "delay": 1200,
            "linkPreview": False
        }
        
        headers = {
            "Content-Type": "application/json",
            "apikey": self.api_token
        }

        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code in [200, 201]:
                return True, "Mensagem enviada com sucesso!"
            else:
                return False, f"Erro na API: {response.text}"
        except Exception as e:
            return False, f"Falha na conexão: {str(e)}"
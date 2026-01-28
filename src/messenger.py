import requests
import os

class Messenger:
    def __init__(self):
        # O Python exige 4 espaços de recuo aqui dentro
        self.base_url = os.getenv("SERVER_URL")
        self.api_key = os.getenv("AUTHENTICATION_API_KEY")
        self.instance = os.getenv("INSTANCE_NAME")

    def enviar_whatsapp(self, numero, mensagem):
        """Envia mensagem de texto via Evolution API"""
        if not numero:
            return False, "❌ Número de telefone não cadastrado."

        # Limpa o número: deixa apenas dígitos
        numero_limpo = "".join(filter(str.isdigit, str(numero)))
        
        # Garante o código do país (55 para Brasil)
        if not numero_limpo.startswith("55"):
            numero_limpo = "55" + numero_limpo

        url = f"{self.base_url}/message/sendText/{self.instance}"
        
        headers = {
            "Content-Type": "application/json",
            "apikey": self.api_key
        }
        
        payload = {
            "number": numero_limpo,
            "text": mensagem,
            "delay": 1200,
            "linkPreview": True
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code in [200, 201]:
                return True, "✅ Mensagem enviada via WhatsApp!"
            else:
                return False, f"❌ Erro na API ({response.status_code}): {response.text}"
        except Exception as e:
            return False, f"❌ Falha de conexão: {str(e)}"

    def formatar_mensagem_cobranca(self, cliente, info):
        """Formata o texto da cobrança padrão"""
        notas = ", ".join(info.get('itens', []))
        total = info.get('total', 0)
        
        msg = (
            f"Olá! Somos da equipe financeira.\n\n"
            f"Identificamos uma pendência para *{cliente}* referente às Notas: {notas}.\n"
            f"Valor total: *R$ {total:,.2f}*.\n\n"
            f"Poderia nos enviar o comprovante ou uma previsão de pagamento?"
        )
        return msg
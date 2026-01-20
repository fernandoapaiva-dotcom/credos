import smtplib
import os
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Carrega as variáveis do arquivo .env
load_dotenv()

class Mailer:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        # Busca os dados das variáveis de ambiente
        self.sender_email = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_PASS")
        
    def enviar_email_cobranca(self, destinatario, cliente_razao, info):
        if not self.sender_email or not self.password:
            return False, "Configurações de e-mail (env) não encontradas."
            
        if not destinatario:
            return False, "E-mail do destinatário não cadastrado."

        nome_chamada = info['contato'] if info['contato'] else cliente_razao
        
        msg = MIMEMultipart()
        msg['From'] = self.sender_email
        msg['To'] = destinatario
        msg['Subject'] = f"Pendência Financeira - {cliente_razao}"

        corpo = f"""
        <html>
            <body style="font-family: sans-serif;">
                <h2>Olá, {nome_chamada}!</h2>
                <p>Identificamos pendências em aberto relacionadas à <b>{cliente_razao}</b>.</p>
                <p><b>Total: R$ {info['total']:,.2f}</b></p>
                <p>Poderia nos enviar o comprovante ou uma previsão de pagamento?</p>
            </body>
        </html>
        """
        msg.attach(MIMEText(corpo, 'html'))

        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.password)
            server.send_message(msg)
            server.quit()
            return True, "E-mail enviado com sucesso!"
        except Exception as e:
            return False, f"Erro: {str(e)}"
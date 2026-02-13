import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class Mailer:
    def __init__(self):
        self.host = os.getenv("EMAIL_HOST")
        self.port = int(os.getenv("EMAIL_PORT", 587))
        self.user = os.getenv("EMAIL_USER")
        self.password = os.getenv("EMAIL_PASS")

    def enviar_email_cobranca(self, destinatario, cliente, info):
        msg = MIMEMultipart()
        msg['From'] = f"Financeiro Servweld <{self.user}>"
        msg['To'] = destinatario
        msg['Subject'] = f"PENDÊNCIA FINANCEIRA - {cliente}"

        # Criando o corpo do e-mail em HTML para um visual profissional
        notas_html = "".join([f"<li>Nota Fiscal: <b>{item}</b></li>" for item in info['items']])
        
        corpo_html = f"""
        <html>
            <body style="font-family: sans-serif; color: #333;">
                <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                    <h2 style="color: #d9534f;">Aviso de Débito Pendente</h2>
                    <p>Olá, <b>{cliente}</b>,</p>
                    <p>Identificamos em nosso sistema que as seguintes faturas ainda não tiveram a confirmação de pagamento:</p>
                    <ul>
                        {notas_html}
                    </ul>
                    <p style="font-size: 18px;">Total em aberto: <span style="color: #d9534f; font-weight: bold;">R$ {info['total']:,.2f}</span></p>
                    <p>Pedimos a gentileza de verificar junto ao seu setor financeiro. Caso o pagamento já tenha sido efetuado, favor desconsiderar este e-mail e nos enviar o comprovante.</p>
                    <hr>
                    <p style="font-size: 12px; color: #777;">Este é um e-mail automático enviado pelo sistema Credos da Servweld.</p>
                </div>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(corpo_html, 'html'))

        try:
            server = smtplib.SMTP(self.host, self.port)
            server.starttls()
            server.login(self.user, self.password)
            server.send_message(msg)
            server.quit()
            return True, "📧 E-mail HTML enviado com sucesso!"
        except Exception as e:
            return False, f"❌ Erro no e-mail: {str(e)}"
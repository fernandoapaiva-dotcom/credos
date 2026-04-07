import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

class MailerService:
    def __init__(self, user, password, server="smtp.gmail.com", port=587):
        self.user = user
        self.password = password
        self.server = server
        self.port = port

    def enviar_email_com_anexos(self, destinatario, assunto, corpo, anexos):
        """Envia e-mail com múltiplos anexos PDFs/XMLs."""
        if not self.user or not self.password:
            print("❌ Erro: Configurações de SMTP ausentes.")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.user
            msg['To'] = destinatario
            msg['Subject'] = assunto

            msg.attach(MIMEText(corpo, 'plain'))

            for fpath in anexos:
                if not os.path.exists(fpath): continue
                
                filename = os.path.basename(fpath)
                with open(fpath, "rb") as attachment:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f"attachment; filename= {filename}")
                    msg.attach(part)

            server = smtplib.SMTP(self.server, self.port)
            server.starttls()
            server.login(self.user, self.password)
            text = msg.as_string()
            server.sendmail(self.user, destinatario, text)
            server.quit()
            
            print(f"📧 E-mail enviado com sucesso para {destinatario}!")
            return True
        except Exception as e:
            print(f"❌ Erro ao enviar e-mail: {e}")
            return False

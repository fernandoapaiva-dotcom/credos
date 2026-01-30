import imaplib
import email
import os
from email.header import decode_header

def conectar_email(user, password, imap_server):
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(user, password)
        return mail, "Conectado"
    except Exception as e:
        return None, str(e)

class MailScanner:
    def __init__(self, config):
        self.user = config.get('mail_base_user')
        self.password = config.get('mail_base_pass')
        self.server = config.get('imap_server')
        self.download_folder = "data/downloads"
        os.makedirs(self.download_folder, exist_ok=True)

    def buscar_nf_enviada(self, numero_nf):
        """
        Busca na caixa de SAÍDA (Sent) por e-mails que contenham o número da NF.
        """
        mail, msg = conectar_email(self.user, self.password, self.server)
        if not mail:
            return []

        try:
            # Tenta selecionar pasta de enviados (nomes comuns)
            pastas_comuns = ['"[Gmail]/Sent Mail"', '"[Gmail]/Enviados"', 'Sent', 'Itens Enviados']
            pasta_selecionada = None
            
            for pasta in pastas_comuns:
                status, _ = mail.select(pasta)
                if status == 'OK':
                    pasta_selecionada = pasta
                    break
            
            if not pasta_selecionada:
                return [] # Não achou pasta de enviados

            # Busca no Assunto ou Corpo
            # Filtro IMAP: SUBJECT "numero_nf"
            status, messages = mail.search(None, f'(SUBJECT "{numero_nf}")')
            
            arquivos_baixados = []
            
            if status == 'OK':
                for num in messages[0].split():
                    _, data = mail.fetch(num, '(RFC822)')
                    msg_email = email.message_from_bytes(data[0][1])
                    
                    # Baixa anexos
                    for part in msg_email.walk():
                        if part.get_content_maintype() == 'multipart': continue
                        if part.get('Content-Disposition') is None: continue
                        
                        filename = part.get_filename()
                        if filename and filename.lower().endswith('.pdf'):
                            filepath = os.path.join(self.download_folder, filename)
                            with open(filepath, 'wb') as f:
                                f.write(part.get_payload(decode=True))
                            arquivos_baixados.append(filepath)
                            
            mail.logout()
            return arquivos_baixados

        except Exception as e:
            print(f"Erro no scanner: {e}")
            return []
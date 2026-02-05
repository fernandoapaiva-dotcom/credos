import imaplib
import email
from email.header import decode_header
import os
import shutil

class MailScanner:
    def __init__(self, config):
        self.user = config.get('mail_base_user')
        self.password = config.get('mail_base_pass')
        self.server = config.get('imap_server')
        
        # --- ORGANIZAÇÃO DE PASTAS ---
        self.base_temp = "temp_data"
        self.pasta_destino = os.path.join(self.base_temp, "attachments")
        
        if not os.path.exists(self.pasta_destino):
            os.makedirs(self.pasta_destino)

    def _conectar(self):
        try:
            if not self.user or not self.password or not self.server:
                return None
            mail = imaplib.IMAP4_SSL(self.server)
            mail.login(self.user, self.password)
            return mail
        except Exception as e:
            print(f"❌ Erro ao conectar no IMAP: {e}")
            return None

    def limpar_assunto(self, subject):
        if not subject: return "sem_assunto"
        decoded_list = decode_header(subject)
        assunto_limpo = ""
        for decoded_bytes, charset in decoded_list:
            if isinstance(decoded_bytes, bytes):
                assunto_limpo += decoded_bytes.decode(charset or 'utf-8', errors='ignore')
            else:
                assunto_limpo += str(decoded_bytes)
        # Limpa caracteres inválidos para nome de arquivo
        return "".join([c for c in assunto_limpo if c.isalnum() or c in (' ', '.', '_', '-')]).strip()

    def _obter_pastas_busca(self, mail):
        pastas_provaveis = []
        pastas_comuns = ['"[Gmail]/E-mails enviados"', '"[Gmail]/Sent Mail"', 'Sent', '"Itens Enviados"', 'INBOX']
        try:
            status, folders = mail.list()
            if status == "OK":
                todas = [f.decode() for f in folders]
                for p in pastas_comuns:
                    for t in todas:
                        if p.replace('"', '') in t: pastas_provaveis.append(t.split(' "/" ')[-1] if ' "/" ' in t else t)
        except: pass
        if not pastas_provaveis: pastas_provaveis = ['INBOX']
        return list(set(pastas_provaveis))

    def baixar_anexos_por_nf(self, numero_nf):
        mail = self._conectar()
        if not mail: return []

        arquivos_baixados = []
        nf_str = str(numero_nf).strip()
        
        try:
            pastas = self._obter_pastas_busca(mail)
            encontrou = False
            for pasta in pastas:
                if encontrou: break
                try:
                    mail.select(pasta)
                    # Busca otimizada
                    status, messages = mail.search(None, f'(SUBJECT "{nf_str}")')
                    if status != "OK" or not messages[0]: continue

                    ids = messages[0].split()
                    for e_id in reversed(ids[-3:]): # Olha só os 3 últimos
                        if encontrou: break
                        _, msg_data = mail.fetch(e_id, "(RFC822)")
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                for part in msg.walk():
                                    if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                                    fname = part.get_filename()
                                    if fname and '.pdf' in fname.lower():
                                        fname = self.limpar_assunto(fname)
                                        fpath = os.path.join(self.pasta_destino, f"{nf_str}_{fname}")
                                        with open(fpath, "wb") as f: f.write(part.get_payload(decode=True))
                                        arquivos_baixados.append(fpath)
                                        encontrou = True
                except: continue
            mail.close()
            mail.logout()
        except: pass
        return arquivos_baixados

    def listar_pastas_debug(self):
        mail = self._conectar()
        if not mail: return []
        _, folders = mail.list()
        mail.logout()
        return [f.decode() for f in folders] if folders else []

    def testar_busca_manual(self, pasta, termo):
        return "Função de teste simplificada."
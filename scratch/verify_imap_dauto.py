import imaplib
import email
import datetime

# Credenciais recuperadas
USER = "nfe@servsolda.com.br"
PASS = "esnq ivkr bmsx czqi"
IMAP_SERVER = "imap.gmail.com"

def targeted_search():
    print(f"🔌 Conectando ao IMAP...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(USER, PASS)
    
    # 1. Buscar na pasta de Enviados
    folder = '"[Gmail]/E-mails enviados"'
    mail.select(folder)
    
    # Buscar por DAUTO em Março 2026
    # A NFS 382 foi UID 1240. Vamos buscar ao redor.
    print(f"\n🔍 Buscando e-mails de março ao redor do UID 1240...")
    
    # SINCE 01-Mar-2026 BEFORE 10-Mar-2026
    status, data = mail.search(None, '(SINCE 01-Mar-2026 BEFORE 10-Mar-2026 SUBJECT "DAUTO")')
    if status == 'OK':
        uids = data[0].split()
        print(f"Encontrados {len(uids)} e-mails no período.")
        for uid in uids:
            # Pegar envelope (Assunto e Data)
            status, msg_data = mail.fetch(uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
            if status == 'OK':
                header = msg_data[0][1].decode()
                print(f"UID {uid.decode().ljust(5)} | {header.strip().replace('\\n', ' | ')}")
                
    mail.logout()

if __name__ == "__main__":
    targeted_search()

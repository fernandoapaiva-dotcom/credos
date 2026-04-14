import imaplib
import email

USER = "nfe@servsolda.com.br"
PASS = "esnq ivkr bmsx czqi"
IMAP_SERVER = "imap.gmail.com"

def targeted_search():
    print(f"🔌 Conectando ao IMAP...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(USER, PASS)
    
    folder = '"[Gmail]/E-mails enviados"'
    mail.select(folder)
    
    print(f"\n🔍 Buscando e-mails de março ao redor do UID 1240...")
    
    status, data = mail.search(None, '(SINCE 01-Mar-2026 BEFORE 10-Mar-2026 SUBJECT "DAUTO")')
    if status == 'OK':
        uids = data[0].split()
        print(f"Encontrados {len(uids)} e-mails no período.")
        for uid in uids:
            uid_str = uid.decode()
            status, msg_data = mail.fetch(uid, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
            if status == 'OK':
                header_raw = msg_data[0][1].decode()
                clean_header = header_raw.replace('\r', '').replace('\n', ' ')
                print(f"UID {uid_str}: {clean_header}")
                
    mail.logout()

if __name__ == "__main__":
    targeted_search()

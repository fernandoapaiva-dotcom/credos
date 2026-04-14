import imaplib
import email

USER = "nfe@servsolda.com.br"
PASS = "esnq ivkr bmsx czqi"
IMAP_SERVER = "imap.gmail.com"

def targeted_search():
    print(f"🔌 Conectando ao IMAP...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(USER, PASS)
    
    # 1. Tentar Todos os e-mails (All Mail) que é mais completo
    folder = '"[Gmail]/Todos os e-mails"'
    mail.select(folder)
    
    # A NFS 382 foi UID 1914 em 'Todos os e-mails'.
    # Vamos buscar UIDs entre 1900 e 1930.
    print(f"\n🔍 Listando UIDs 1910 a 1925 na pasta '{folder}'...")
    
    for uid in range(1910, 1926):
        status, msg_data = mail.fetch(str(uid), '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
        if status == 'OK' and msg_data[0]:
            header_raw = msg_data[0][1].decode()
            clean_header = header_raw.replace('\r', '').replace('\n', ' ')
            print(f"UID {uid}: {clean_header}")
            
    mail.logout()

if __name__ == "__main__":
    targeted_search()

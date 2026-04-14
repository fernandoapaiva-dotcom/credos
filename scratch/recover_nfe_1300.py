import sys
import os
import imaplib
import email
import sqlite3

sys.path.insert(0, '/app')

from src.mail_scanner import MailScanner
from src.manager import Manager

CNPJ_EMPRESA = "54804458000122"
USER = "nfe@servsolda.com.br"
PASS = "esnq ivkr bmsx czqi"
IMAP_SERVER = "imap.gmail.com"

def main():
    # Inicializa scanner
    m = Manager(CNPJ_EMPRESA)
    scanner = MailScanner(m.config)
    
    print(f"🔌 Conectando ao IMAP para recuperar UID 1915...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(USER, PASS)
    
    folder = '"[Gmail]/Todos os e-mails"'
    mail.select(folder)
    
    status, data = mail.fetch("1915", '(RFC822)')
    if status == 'OK' and data[0]:
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        print(f"✅ E-mail recuperado: {msg.get('Subject')}")
        
        # Processar e indexar
        result = scanner.processar_email(msg, 1915, folder.replace('"', ''))
        if result:
            print("🚀 NF-e 1300 indexada com sucesso!")
        else:
            print("⚠️ Falha ao indexar NF-e 1300.")
    else:
        print("❌ UID 1915 não encontrado ou erro no fetch.")
        
    mail.logout()

if __name__ == "__main__":
    main()

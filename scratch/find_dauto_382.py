import sys
import os
import email
from email.header import decode_header
import imaplib

# Adiciona o diretório atual ao path para importar src
sys.path.append('/app')

from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

def find_dauto_382_anywhere():
    cnpj_servsolda = "54804458000122"
    config = carregar_configuracoes_db(cnpj_servsolda)
    
    scanner = MailScanner(config)
    mail = scanner.conectar()
    if not mail:
        print("❌ Falha na conexão IMAP")
        return

    print("🔍 Buscando por 'DAUTO' em toda a conta...")
    
    pastas = ['INBOX', '[Gmail]/Sent Mail', 'Sent', 'Enviados', '[Gmail]/Todos os e-mails']
    
    found_any = False
    for folder_name in pastas:
        status, _ = mail.select(f'"{folder_name}"')
        if status != 'OK': continue
        
        # Busca por "DAUTO" (nome único o suficiente)
        typ, data = mail.search(None, '(OR SUBJECT "DAUTO" BODY "DAUTO")')
        if not data[0]: continue
        
        ids = data[0].split()
        print(f"📂 Pasta {folder_name}: {len(ids)} e-mails.")
        
        for mid in ids:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            if not msg_data or not msg_data[0]: continue
            msg = email.message_from_bytes(msg_data[0][1])
            
            subj = decode_header(msg.get("Subject", ""))[0][0]
            if isinstance(subj, bytes):
                subj = subj.decode(errors='ignore')
            
            # Verificamos se 382 está em algum lugar (Assunto, Corpo ou Anexos)
            all_text = (subj + str(msg.get("From", "")) + str(msg.get("To", ""))).upper()
            
            # Pega anexos
            attachments = []
            for part in msg.walk():
                if part.get_filename():
                    attachments.append(part.get_filename())
            
            all_text += " ".join(attachments).upper()
            
            if "382" in all_text:
                found_any = True
                print(f"   🎯 MATCH! ID:{mid.decode()} Data: {msg.get('Date')}")
                print(f"      Assunto: {subj}")
                print(f"      Anexos: {', '.join(attachments)}")

    if not found_any:
        print("❌ Nada encontrado para 'DAUTO' + '382'.")

    mail.logout()

if __name__ == "__main__":
    find_dauto_382_anywhere()

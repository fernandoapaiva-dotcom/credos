import sys
import os
import email
from email.header import decode_header
import imaplib

# Adiciona o diretório atual ao path para importar src
sys.path.append('/app')

from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

def search_nf_382_dauto():
    cnpj_servsolda = "54804458000122"
    config = carregar_configuracoes_db(cnpj_servsolda)
    
    scanner = MailScanner(config)
    mail = scanner.conectar()
    if not mail:
        print("❌ Falha na conexão IMAP")
        return

    print("🔍 Iniciando busca profunda por '382' e 'DAUTO'...")
    
    # Lista pastas candidatas
    pastas = ['INBOX', '[Gmail]/Sent Mail', 'Sent', 'Enviados', '[Gmail]/Todos os e-mails']
    
    for folder_name in pastas:
        print(f"📂 Verificando pasta: {folder_name}")
        status, _ = mail.select(f'"{folder_name}"')
        if status != 'OK': continue
        
        # Busca por QUALQUER e-mail que mencione 382
        typ, data = mail.search(None, 'BODY "382"')
        if data[0]:
            ids = data[0].split()
            print(f"   Mencão a '382': {len(ids)} e-mails.")
            for mid in ids:
                _, msg_data = mail.fetch(mid, "(RFC822)")
                if not msg_data or not msg_data[0]: continue
                msg = email.message_from_bytes(msg_data[0][1])
                
                # Verifica se é para o Dauto
                body = ""
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body += part.get_payload(decode=True).decode(errors='ignore')
                
                if "DAUTO" in body.upper() or "DAUTO" in str(msg.get("Subject", "")).upper():
                    print(f"   🌟 ENCONTRADO! ID:{mid.decode()} Subject: {msg.get('Subject')}")
                    for part in msg.walk():
                        if part.get_filename():
                            print(f"      📎 {part.get_filename()}")

    mail.logout()

if __name__ == "__main__":
    search_nf_382_dauto()

import sys
import os
import email
from email.header import decode_header
import imaplib

# Adiciona o diretório atual ao path para importar src
sys.path.append('/app')

from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

def diagnose_dauto_emails():
    cnpj_servsolda = "54804458000122"
    config = carregar_configuracoes_db(cnpj_servsolda)
    
    scanner = MailScanner(config)
    mail = scanner.conectar()
    if not mail:
        print("❌ Falha na conexão IMAP")
        return

    print("🔍 Buscando por 'DAUTO' em todas as pastas...")
    
    # Lista pastas
    _, folders = mail.list()
    for f_raw in folders:
        folder_name = f_raw.decode().split('"/"')[-1].strip().replace('"', '')
        if any(x in folder_name.lower() for x in ['spam', 'trash', 'lixeira', 'drafts']): continue
        
        status, _ = mail.select(f'"{folder_name}"')
        if status != 'OK': continue
        
        print(f"\n📂 Verificando pasta: {folder_name}")
        
        # Busca por DAUTO
        typ, data = mail.search(None, '(OR SUBJECT "DAUTO" BODY "DAUTO")')
        if not data[0]:
            continue
            
        ids = data[0].split()
        print(f"   Encontrados {len(ids)} e-mails.")
        
        for mid in ids[-10:]: # Pega os 10 mais recentes
            _, msg_data = mail.fetch(mid, "(RFC822)")
            if not msg_data or not msg_data[0]: continue
            msg = email.message_from_bytes(msg_data[0][1])
            
            subj = decode_header(msg.get("Subject", ""))[0][0]
            if isinstance(subj, bytes):
                subj = subj.decode(errors='ignore')
            
            date = msg.get("Date")
            print(f"   - [{date}] ID:{mid.decode()} Subject: {subj}")
            
            # Lista anexos
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                fname = part.get_filename()
                if fname:
                    print(f"     📎 Anexo: {fname}")

    mail.logout()

if __name__ == "__main__":
    diagnose_dauto_emails()

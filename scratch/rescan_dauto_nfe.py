"""
Script de re-escaneamento IMAP para recuperar NFe companheira da NFS 382 do Dauto.
"""
import sys
import os
import imaplib
import email as email_lib
import sqlite3

sys.path.insert(0, '/app')

CNPJ_EMPRESA = "54804458000122"
DB_PATH = f"/app/data/db_{CNPJ_EMPRESA}.db"

def get_config():
    """Carrega config da empresa usando o mesmo padrão do Manager."""
    from src.manager import Manager
    m = Manager(CNPJ_EMPRESA)
    return m.config

def check_already_indexed(uid_str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM documentos_fiscais WHERE email_uid = ?", (uid_str,))
    r = c.fetchone()
    conn.close()
    return r is not None

def main():
    config = get_config()
    email_cfg = config.get('email', {})
    
    user     = email_cfg.get('email') or email_cfg.get('username') or email_cfg.get('user')
    password = email_cfg.get('app_password') or email_cfg.get('password')
    server   = email_cfg.get('imap_server', 'imap.gmail.com')
    
    if not user or not password:
        # Tenta carregar das variáveis de ambiente
        user     = os.environ.get('EMAIL_USER')
        password = os.environ.get('EMAIL_PASS')
    
    print(f"USER: {user}")
    print(f"SERVER: {server}")
    print(f"HAS PASS: {bool(password)}")
    
    if not user or not password:
        print("❌ Credenciais não encontradas. Verifique a configuração.")
        print("Config email keys:", list(email_cfg.keys()))
        return
    
    print(f"\n🔌 Conectando ao IMAP...")
    mail = imaplib.IMAP4_SSL(server)
    mail.login(user, password)
    print("✅ Conectado!")
    
    # Busca na pasta Enviados, UIDs ao redor da NFS 382 (UID 1240)
    # A NFe companheira deve estar entre 1241-1250
    folder = '[Gmail]/E-mails enviados'
    status, _ = mail.select(f'"{folder}"')
    print(f"\n📁 Selecionando '{folder}': {status}")
    
    if status != 'OK':
        folder = 'Sent'
        status, _ = mail.select(folder)
        print(f"📁 Tentando 'Sent': {status}")
    
    # Busca e-mails com DAUTO no assunto a partir de março 2026
    print("\n🔍 Buscando e-mails DAUTO de março 2026...")
    status, ids = mail.search(None, '(SINCE 01-Mar-2026 BEFORE 31-Mar-2026 SUBJECT "DAUTO")')
    print(f"Resultado da busca: {status}, IDs: {ids}")
    
    if status == 'OK' and ids[0]:
        uid_list = ids[0].split()
        print(f"Encontrados {len(uid_list)} e-mails do DAUTO em março 2026")
        
        for uid in uid_list:
            status, data = mail.fetch(uid, '(RFC822 ENVELOPE)')
            if status != 'OK':
                continue
            raw = data[0][1]
            msg = email_lib.message_from_bytes(raw)
            print(f"\n  UID:{uid.decode()} | Assunto: {msg.get('Subject', 'N/A')[:70]}")
            print(f"  From: {msg.get('From','N/A')}")
    
    mail.logout()

if __name__ == "__main__":
    main()

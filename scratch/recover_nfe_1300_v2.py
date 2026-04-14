import sys
import os
import imaplib
import email
import sqlite3
import datetime

sys.path.insert(0, '/app')

from src.manager import Manager

CNPJ_EMPRESA = "54804458000122"
USER = "nfe@servsolda.com.br"
PASS = "esnq ivkr bmsx czqi"
IMAP_SERVER = "imap.gmail.com"
DB_PATH = f"/app/data/db_{CNPJ_EMPRESA}.db"
REPO_DIR = "/app/data/repository_v2"

def index_manually(cnpj_cli, num_nf, tipo, fpath_local, email_uid, nome_cli):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("""
            INSERT INTO documentos_fiscais 
            (cnpj_cliente, num_nf, tipo, fpath_local, email_uid, created_at, nome_cliente)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (cnpj_cli, num_nf, tipo, fpath_local, email_uid, agora, nome_cli))
        conn.commit()
        print(f"✅ Indexado no banco: {fpath_local}")
    except Exception as e:
        print(f"❌ Erro ao indexar: {e}")
    finally:
        conn.close()

def main():
    m = Manager(CNPJ_EMPRESA)
    
    print(f"🔌 Conectando ao IMAP para recuperar NF-e 1300 (UID 1915)...")
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(USER, PASS)
    
    folder = '"[Gmail]/Todos os e-mails"'
    mail.select(folder)
    
    status, data = mail.fetch("1915", '(RFC822)')
    if status == 'OK' and data[0]:
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        print(f"✅ E-mail recuperado: {msg.get('Subject')}")
        
        cnpj_dauto = "24934648000284"
        nome_dauto = "DAUTO COELHO DOS SANTOS"
        nf_num = "1300"
        
        # Salva anexos
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None:
                continue
            
            fname = part.get_filename()
            if not fname: continue
            
            # Sanitização básica
            fname = "".join([c for c in fname if c.isalnum() or c in ('.', '_', '-')]).strip()
            
            # Caminho de armazenamento
            tipo_detectado = "NF-E" if fname.lower().endswith('.xml') or "danfe" in fname.lower() or "nfe" in fname.lower() else "BOLETO"
            if "boleto" in fname.lower(): tipo_detectado = "BOLETO"
            
            subfolder = tipo_detectado.lower().replace("nf-e", "nf-e").replace("nf-s", "nfs")
            dest_dir = os.path.join(REPO_DIR, f"{cnpj_dauto}_{nome_dauto.replace(' ', '_')}", subfolder, nf_num)
            os.makedirs(dest_dir, exist_ok=True)
            
            fpath = os.path.join(dest_dir, f"manual_1915_{fname}")
            with open(fpath, "wb") as f:
                f.write(part.get_payload(decode=True))
            print(f"💾 Salvo: {fpath}")
            
            # Indexa
            index_manually(cnpj_dauto, nf_num, tipo_detectado, fpath, f"nfe@servsolda.com.br_Todos os e-mails_1915", nome_dauto)
            
    else:
        print("❌ UID 1915 não encontrado.")
        
    mail.logout()

if __name__ == "__main__":
    main()

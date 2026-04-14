import os
import sqlite3
import imaplib
import email
import re
from src.database import carregar_configuracoes_db
from src.mail_scanner import MailScanner

UNIT_CNPJ = "54804458000122" # Servsolda
DAUTO_CNPJ = "24934648000284"

def final_rescue():
    config = carregar_configuracoes_db(UNIT_CNPJ)
    user = config.get('base_mail_user')
    password = config.get('base_mail_pass')
    server = config.get('imap_server')
    
    print(f"🚀 INICIANDO RESGATE AUTÔNOMO: {user}")
    
    # Conexão Scanner
    scanner = MailScanner(config)
    mail = scanner.conectar()
    if not mail:
        print("❌ Falha na conexão IMAP")
        return

    # DB Connection
    db_path = f"/app/data/db_{UNIT_CNPJ}.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # 1. Limpeza de resíduos
        cur.execute("DELETE FROM documentos_fiscais WHERE email_uid LIKE 'financeiro%'")
        conn.commit()

        # 2. Varredura Profunda
        # Buscamos por e-mails com anexos PDF/XML nas últimas 2 semanas em todas as pastas
        _, folders_raw = mail.list()
        pastas = []
        for f in folders_raw:
            match = re.search(r'"(.*?)"$', f.decode())
            if match: pastas.append(match.group(1))

        total_encontrados = 0
        for pasta in pastas:
            if any(x in pasta.lower() for x in ['trash', 'spam', 'lixeira']): continue
            try:
                status, _ = mail.select(f'"{pasta}"')
                if status != "OK": continue
                
                # Busca e-mails das últimas 2 semanas para ser exaustivo
                from datetime import datetime, timedelta
                data_busca = (datetime.now() - timedelta(days=14)).strftime("%d-%b-%Y")
                status, data = mail.search(None, f'SINCE "{data_busca}"')
                
                if not data[0]: continue
                ids = data[0].split()
                
                print(f"   🔍 Analisando {len(ids)} e-mails em {pasta}...")
                
                for mid in ids:
                    _, msg_data = mail.fetch(mid, '(RFC822)')
                    msg = email.message_from_bytes(msg_data[0][1])
                    uid = f"{user}_{pasta}_{mid.decode()}"
                    
                    for part in msg.walk():
                        if part.get_content_disposition() is None: continue
                        fname = scanner.limpar_nome_arquivo(part.get_filename())
                        if not fname.lower().endswith(('.pdf', '.xml')): continue
                        
                        # Download e Sniper V5
                        fpath = os.path.join("/app/data/repository", f"{mid.decode()}_{fname}")
                        payload = part.get_payload(decode=True)
                        with open(fpath, "wb") as f:
                            f.write(payload)
                        
                        meta = scanner.extrair_meta_documento(fpath, DAUTO_CNPJ, "DAUTO", None, None)
                        
                        if meta['pertence_cliente']:
                            # Tenta extrair NF num
                            texto = scanner._extrair_texto_arquivo(fpath)
                            nf_match = re.search(r'(?:N[Ff][Ee]|Nota|Número):\s*(\d+)', texto, re.I)
                            nf_num = nf_match.group(1) if nf_match else ""
                            
                            print(f"      ✅ DAUTO ENCONTRADO: {fname} | Tipo: {meta['tipo_detectado']} | NF: {nf_num}")
                            cur.execute("""
                                INSERT OR REPLACE INTO documentos_fiscais 
                                (cnpj_cliente, num_nf, tipo, email_uid, fpath_local, created_at)
                                VALUES (?, ?, ?, ?, ?, datetime('now'))
                            """, (DAUTO_CNPJ, nf_num, meta['tipo_detectado'], uid, fpath))
                            total_encontrados += 1
            except Exception as e_pasta:
                print(f"   ⚠️ Erro na pasta {pasta}: {e_pasta}")

        conn.commit()
        print(f"\n✅ RESGATE FINALIZADO. {total_encontrados} documentos vinculados ao Dauto.")

    finally:
        mail.logout()
        conn.close()

if __name__ == "__main__":
    final_rescue()

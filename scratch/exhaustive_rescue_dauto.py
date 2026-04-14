import os
import sqlite3
import imaplib
import email
import re
from datetime import datetime, timedelta
from src.database import carregar_configuracoes_db
from src.mail_scanner import MailScanner

UNIT_CNPJ = "54804458000122" # Servsolda
DAUTO_CNPJ = "24934648000284"

def exhaustive_rescue():
    config = carregar_configuracoes_db(UNIT_CNPJ)
    user = config.get('base_mail_user')
    password = config.get('base_mail_pass')
    server = config.get('imap_server')
    
    print(f"🚀 INICIANDO RESGATE EXAUSTIVO EM: {user}")
    
    scanner = MailScanner(config)
    mail = scanner.conectar()
    if not mail:
        print("❌ Falha na conexão IMAP")
        return

    db_path = f"/app/data/db_{UNIT_CNPJ}.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # 1. Busca a data da NF 382 se possível
        # Se não souber, usa uma janela de 01-Apr a 15-Apr
        data_inicio = "01-Apr-2026"
        data_fim = "15-Apr-2026"
        
        # 2. Varre todas as pastas
        _, folders_raw = mail.list()
        pastas = []
        for f in folders_raw:
            # Padrão flexível para pegar o nome da pasta
            f_decoded = f.decode()
            match = re.search(r'"([^"]+)"$', f_decoded)
            if match: pastas.append(match.group(1))
            else: pastas.append(f_decoded.split()[-1].replace('"', ''))

        encontrados = []
        for pasta in pastas:
            if any(x in pasta.lower() for x in ['trash', 'spam', 'lixeira']): continue
            try:
                # Usa select com aspas para evitar erros de shell
                status, _ = mail.select(f'"{pasta}"')
                if status != "OK": continue
                
                print(f"   📂 Pesquisando na pasta: {pasta}")
                
                # Busca e-mails no intervalo
                status, data = mail.search(None, f'(SINCE "{data_inicio}" BEFORE "{data_fim}")')
                if not data[0]: continue
                
                ids = data[0].split()
                for mid in ids:
                    _, msg_data = mail.fetch(mid, '(RFC822)')
                    msg = email.message_from_bytes(msg_data[0][1])
                    uid = f"{user}_{pasta}_{mid.decode()}"
                    
                    for part in msg.walk():
                        if part.get_content_disposition() is None: continue
                        fname = scanner.limpar_nome_arquivo(part.get_filename())
                        if not fname.lower().endswith(('.pdf', '.xml')): continue
                        
                        # Download e Sniper V5
                        fpath = os.path.join("/app/data/repository", f"resgate_{mid.decode()}_{fname}")
                        payload = part.get_payload(decode=True)
                        with open(fpath, "wb") as f:
                            f.write(payload)
                        
                        # Sniper V5: Tenta detectar Dauto/382
                        meta = scanner.extrair_meta_documento(fpath, DAUTO_CNPJ, "DAUTO", None, None)
                        
                        if meta['pertence_cliente']:
                            # Extração de número da NF
                            texto = scanner._extrair_texto_arquivo(fpath)
                            nf_match = re.search(r'(?:N[Ff][Ee]|Nota|Número):\s*(\d+)', texto, re.I)
                            nf_num = nf_match.group(1) if nf_match else ""
                            
                            tipo = meta['tipo_detectado']
                            print(f"      🔎 ENCONTRADO: {fname} (ID: {mid.decode()}) | Tipo: {tipo} | NF: {nf_num}")
                            
                            cur.execute("""
                                INSERT OR REPLACE INTO documentos_fiscais 
                                (cnpj_cliente, num_nf, tipo, email_uid, fpath_local, created_at)
                                VALUES (?, ?, ?, ?, ?, datetime('now'))
                            """, (DAUTO_CNPJ, nf_num, tipo, uid, fpath))
                            encontrados.append(fname)
            except Exception as e_p:
                print(f"      ⚠️ Erro na pasta {pasta}: {e_p}")

        conn.commit()
        print(f"\n✅ RESGATE EXAUSTIVO FINALIZADO. {len(encontrados)} arquivos processados.")

    finally:
        mail.logout()
        conn.close()

if __name__ == "__main__":
    exhaustive_rescue()

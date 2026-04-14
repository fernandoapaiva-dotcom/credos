import sqlite3
import os
import sys
import imaplib
import email
import re
from datetime import datetime, timedelta
from src.database import carregar_configuracoes_db
from src.mail_scanner import MailScanner
from src.fiscal_repository import FiscalRepository

def extract_client_name_from_email_address(email_address):
    # Tenta extrair um nome de um email ex: "DAUTO COELHO" <dauto@gmail.com>
    match = re.match(r'(?:"?([^"]*)"?\s)?<?.*>', email_address)
    if match and match.group(1):
        return match.group(1).strip()
    return "CLIENTE_DESCONHECIDO"

def main():
    print("=== INICIANDO DUMP HISTÓRICO DO REPOSITÓRIO FISCAL ===")
    
    # 1. Parâmetros de data
    data_inicio = "01-Oct-2025" # A partir de outubro!
    
    db_dir = "/app/data"
    dbs = [f for f in os.listdir(db_dir) if f.startswith('db_') and f.endswith('.db')]
    repo = FiscalRepository()
    
    for db_name in dbs:
        cnpj_empresa = db_name.replace('db_', '').replace('.db', '')
        print(f"\n📂 UNIDADE: {cnpj_empresa}")
        
        config = carregar_configuracoes_db(cnpj_empresa)
        user = config.get('base_mail_user')
        password = config.get('base_mail_pass')
        server = config.get('imap_server')
        
        if not all([user, password, server]):
            print("   ❌ Credenciais de email inválidas.")
            continue
            
        scanner = MailScanner(config)
        mail = scanner.conectar()
        
        if not mail:
             print("   ❌ Falha na conexão com o servidor IMAP.")
             continue
             
        try:
             # Varre envios
             pastas_enviados = ['INBOX', '"[Gmail]/Sent Mail"', 'Sent', 'Enviados']
             
             for pasta in pastas_enviados:
                 try:
                     status, _ = mail.select(pasta)
                     if status != "OK": continue
                     print(f"   🔍 Analisando pasta: {pasta}")
                     
                     status, data = mail.search(None, f'SINCE "{data_inicio}"')
                     if not data[0]: continue
                     
                     ids = data[0].split()
                     print(f"      📥 Encontrados {len(ids)} e-mails para análise.")
                     
                     processados = 0
                     for mid in ids:
                         try:
                             _, msg_data = mail.fetch(mid, '(RFC822)')
                             msg = email.message_from_bytes(msg_data[0][1])
                             uid = f"{user}_{pasta}_{mid.decode()}"
                             
                             to_addr = msg.get("To", "")
                             cc_addr = msg.get("Cc", "")
                             
                             for part in msg.walk():
                                 if part.get_content_disposition() is None: continue
                                 fname = scanner.limpar_nome_arquivo(part.get_filename())
                                 if not fname.lower().endswith(('.pdf', '.xml')): continue
                                 
                                 fpath_temp = os.path.join("/app/data/repository", f"dump_{mid.decode()}_{fname}")
                                 with open(fpath_temp, "wb") as f:
                                     f.write(part.get_payload(decode=True))
                                     
                                 # Análise com Sniper
                                 meta = scanner.extrair_meta_documento(fpath_temp, None, None, None, None, extra_context=f"{to_addr} {cc_addr}")
                                 
                                 if meta.get("cnpj_detectado"):
                                        nome_cliente = extract_client_name_from_email_address(to_addr)
                                        
                                        texto = scanner._extrair_texto_arquivo(fpath_temp)
                                        nf_match = re.search(r'(?:N[Ff][Ee]|Nota|Número):\s*(\d+)', texto, re.I)
                                        nf_num = nf_match.group(1) if nf_match else "DESCONHECIDO"

                                        # Move pro Repo Permanente
                                        repo.organizar_arquivo(
                                            cnpj_empresa, 
                                            meta["cnpj_detectado"], 
                                            nome_cliente, 
                                            meta["tipo_detectado"], 
                                            nf_num, 
                                            fpath_temp
                                        )
                                        processados += 1
                                        
                                 # Remove o temp original do repository normal
                                 if os.path.exists(fpath_temp):
                                     os.remove(fpath_temp)
                                     
                         except Exception as e_msg:
                                print(f"      ⚠️ Erro processando email {mid}: {e_msg}")
                                
                     print(f"      ✅ {processados} arquivos indexados e guardados.")
                 except Exception as e_pst:
                     print(f"   ⚠️ Erro lendo pasta {pasta}: {e_pst}")
                     
        finally:
             mail.logout()

if __name__ == "__main__":
    main()

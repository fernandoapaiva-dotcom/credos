import os
import sqlite3
import imaplib
import email
import re
from src.database import carregar_configuracoes_db, conectar
from src.mail_scanner import MailScanner

# CONFIGURAÇÕES
CONFIG_CNPJ = "54804458000122" # Servsolda
CONTA = "comercial@servweld.com.br" # Recomendada pelo contexto anterior

config = carregar_configuracoes_db(CONFIG_CNPJ)
# Override mail se necessário (o banco pode ter vários)
scanner = MailScanner(config)
mail = scanner.conectar()

if not mail:
    print("Erro conexão")
    exit()

print("=== RE-INDEXAÇÃO AMPLA V6 (Busca por DAUTO e NF 382) ===")

try:
    # Busca em todas as pastas possíveis
    _, folders = mail.list()
    pastas = [f.decode().split('"/"')[-1].strip().replace('"', '') for f in folders]
    
    conn = conectar(CONFIG_CNPJ)
    c = conn.cursor()
    
    # Termos de Busca
    termos = ['SUBJECT "DAUTO"', 'BODY "DAUTO"', 'SUBJECT "382"', 'BODY "382"']
    
    ids_encontrados = set()
    for pasta in pastas:
        if any(x in pasta.lower() for x in ['spam', 'trash', 'lixeira']): continue
        status, _ = mail.select(pasta)
        if status != "OK": continue
        
        for termo in termos:
            typ, data = mail.search(None, termo)
            if data[0]:
                for mid in data[0].split():
                    ids_encontrados.add((pasta, mid))
    
    print(f"Encontrados {len(ids_encontrados)} e-mails potenciais.")
    
    for pasta, e_id in ids_encontrados:
        mail.select(pasta)
        _, msg_data = mail.fetch(e_id, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        uid = f"{pasta}_{e_id.decode()}"
        
        assunto = msg.get('Subject', '')
        print(f"   📧 Analisando: {assunto}")
        
        for part in msg.walk():
            if part.get_content_disposition() is None: continue
            fname = scanner.limpar_nome_arquivo(part.get_filename())
            if not fname.lower().endswith(('.pdf', '.xml')): continue
            
            fpath = os.path.join("/app/data/repository", f"{uid}_{fname}")
            payload = part.get_payload(decode=True)
            with open(fpath, "wb") as f:
                f.write(payload)
            
            # Extrai Metadados com a lógica V5 (sem filtro de CNPJ alvo)
            meta = scanner.extrair_meta_documento(fpath, None, None, None, None)
            
            tipo = meta.get('tipo_detectado', 'BOLETO')
            cnpj_det = meta.get('cnpj_detectado', '00000000000000')
            
            # Tenta pegar número da NF
            texto = scanner._extrair_texto_arquivo(fpath)
            nf_match = re.search(r'(?:N[Ff][Ee]|Nota|Número):\s*(\d+)', texto, re.I)
            nf_num = nf_match.group(1) if nf_match else ""
            
            print(f"      📎 {fname} | Tipo: {tipo} | CNPJ: {cnpj_det} | NF: {nf_num}")
            
            c.execute("""
                INSERT OR REPLACE INTO documentos_fiscais 
                (cnpj_cliente, num_nf, tipo, email_uid, fpath_local, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (cnpj_det, nf_num, tipo, uid, fpath))
            
    conn.commit()
    conn.close()

finally:
    mail.logout()

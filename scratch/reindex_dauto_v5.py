import os
import sqlite3
import imaplib
import email
import re
from src.database import carregar_configuracoes_db, conectar
from src.mail_scanner import MailScanner

# CONFIGURAÇÕES
CONFIG_CNPJ = "54804458000122" # Servsolda
CLIENTE_CNPJ = "24934648000284" # Dauto
BUSCA_SINC = "01-Mar-2026" # Sincronizar desde Março

config = carregar_configuracoes_db(CONFIG_CNPJ)
scanner = MailScanner(config)
mail = scanner.conectar()

if not mail:
    print("Erro conexão")
    exit()

print(f"=== RE-INDEXAÇÃO SNIPER V5: {CLIENTE_CNPJ} ===")

try:
    scanner.descobrir_pasta_enviados(mail)
    # Busca ampla por CNPJ do Dauto
    cnpj_limpo = re.sub(r'\D', '', CLIENTE_CNPJ)
    status, data = mail.search(None, f'(OR SUBJECT "{cnpj_limpo}" BODY "{cnpj_limpo}")')
    
    if status == "OK" and data[0]:
        ids = data[0].split()
        print(f"Encontrados {len(ids)} e-mails potenciais.")
        
        conn = conectar(CONFIG_CNPJ)
        c = conn.cursor()
        
        for e_id in ids:
            _, msg_data = mail.fetch(e_id, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            uid = e_id.decode()
            
            for part in msg.walk():
                if part.get_content_disposition() is None: continue
                fname = scanner.limpar_nome_arquivo(part.get_filename())
                if not fname.lower().endswith(('.pdf', '.xml')): continue
                
                # Salva e Processa com a NOVA LÓGICA V5
                fpath = os.path.join("/app/data/repository", f"{uid}_{fname}")
                payload = part.get_payload(decode=True)
                
                with open(fpath, "wb") as f:
                    f.write(payload)
                
                # Extrai usando a nova lógica de precisão
                # Passamos o cnpj_alvo para o scanner validar o pertencimento
                meta = scanner.extrair_meta_documento(fpath, CLIENTE_CNPJ, "DAUTO", None, None)
                
                if meta['pertence_cliente']:
                    tipo = meta.get('tipo_detectado', 'BOLETO')
                    # Tenta extrair número da NF do conteúdo se for XML/NFE
                    nf_num = ""
                    if tipo in ['NF-E', 'NF-S']:
                        texto = scanner._extrair_texto_arquivo(fpath)
                        # Busca por NF no texto
                        nf_match = re.search(r'Número:\s*(\d+)', texto, re.I)
                        if nf_match: nf_num = nf_match.group(1)
                    
                    print(f"✅ Indexado: {fname} | Tipo: {tipo} | NF: {nf_num} | UID: {uid}")
                    
                    c.execute("""
                        INSERT OR REPLACE INTO documentos_fiscais 
                        (cnpj_cliente, num_nf, tipo, email_uid, fpath_local, created_at)
                        VALUES (?, ?, ?, ?, ?, datetime('now'))
                    """, (cnpj_limpo, nf_num, tipo, uid, fpath))
            
        conn.commit()
        conn.close()
    else:
        print("Nenhum e-mail encontrado para este CNPJ.")

finally:
    mail.logout()

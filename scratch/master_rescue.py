import os
import sqlite3
import imaplib
import email
import re
from src.database import carregar_configuracoes_db
from src.mail_scanner import MailScanner

DB_DIR = "/app/data"
CLIENTE_CNPJ_RE = "24934648"  # DAUTO
NF_ALVO = "382"

def main():
    dbs = [f for f in os.listdir(DB_DIR) if f.startswith('db_') and f.endswith('.db')]
    print(f"🔍 Iniciando resgate em {len(dbs)} unidades...")

    for db_name in dbs:
        path = os.path.join(DB_DIR, db_name)
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cnpj_unidade = db_name.replace('db_', '').replace('.db', '')
        
        # 1. Verifica se o Dauto pertence a esta unidade
        cur.execute("SELECT nome, cnpj FROM clientes WHERE cnpj LIKE ?", (f"%{CLIENTE_CNPJ_RE}%",))
        cliente = cur.fetchone()
        
        if not cliente:
            conn.close()
            continue
            
        print(f"\n✅ DAUTO LOCALIZADO na unidade: {cnpj_unidade} ({cliente[0]})")
        
        # 2. Pega o E-mail Base oficial
        config = carregar_configuracoes_db(cnpj_unidade)
        base_email = config.get('base_mail_user')
        base_pass = config.get('base_mail_pass')
        imap_server = config.get('imap_server')
        
        print(f"   📧 E-mail Base Oficial: {base_email}")
        
        if not base_email or not base_pass:
            print("   ❌ Erro: Configuração de e-mail incompleta no banco.")
            conn.close()
            continue
            
        # 3. Limpeza de resíduos de diagnósticos anteriores (arquivos ZIP ou da conta financeira)
        print("   🧹 Limpando resíduos de diagnósticos anteriores...")
        cur.execute("DELETE FROM documentos_fiscais WHERE email_uid LIKE 'financeiro%' OR fpath_local LIKE '%.zip'")
        conn.commit()
        
        # 4. Varredura Sniper V5 no E-mail Base
        print(f"   🎯 Iniciando Varredura Sniper para NF {NF_ALVO}...")
        scanner = MailScanner(config)
        mail = scanner.conectar()
        if not mail:
            print("   ❌ Erro: Falha na conexão IMAP.")
            conn.close()
            continue
            
        try:
            # Busca profunda em todas as pastas
            _, folders_raw = mail.list()
            pastas = []
            for f in folders_raw:
                res = re.search(r'"(.*?)"$', f.decode())
                if res: pastas.append(res.group(1))
                else: 
                    parts = f.decode().split('"/"')
                    if len(parts) > 1: pastas.append(parts[-1].strip().replace('"', ''))

            encontrados = 0
            for pasta in pastas:
                if any(x in pasta.lower() for x in ['trash', 'spam', 'lixeira']): continue
                try:
                    status, _ = mail.select(f'"{pasta}"')
                    if status != "OK": continue
                except: continue
                
                # Busca por NF ou CNPJ
                typ, data = mail.search(None, f'(OR SUBJECT "{NF_ALVO}" BODY "{NF_ALVO}")')
                if data[0]:
                    for mid in data[0].split():
                        _, msg_data = mail.fetch(mid, '(RFC822)')
                        msg = email.message_from_bytes(msg_data[0][1])
                        uid = f"{base_email}_{pasta}_{mid.decode()}"
                        
                        for part in msg.walk():
                            if part.get_content_disposition() is None: continue
                            fname = scanner.limpar_nome_arquivo(part.get_filename())
                            if not fname.lower().endswith(('.pdf', '.xml')): continue
                            
                            fpath = os.path.join("/app/data/repository", f"{mid.decode()}_{fname}")
                            with open(fpath, "wb") as f:
                                f.write(part.get_payload(decode=True))
                            
                            # LOGICA V5: Validação de Pertencimento
                            meta = scanner.extrair_meta_documento(fpath, cliente[1], "DAUTO", NF_ALVO, None)
                            
                            if meta['pertence_cliente'] or meta['tem_nf']:
                                print(f"      📎 {fname} indexado com sucesso (Tipo: {meta['tipo_detectado']})")
                                cur.execute("""
                                    INSERT OR REPLACE INTO documentos_fiscais 
                                    (cnpj_cliente, num_nf, tipo, email_uid, fpath_local, created_at)
                                    VALUES (?, ?, ?, ?, ?, datetime('now'))
                                """, (cliente[1], NF_ALVO, meta['tipo_detectado'], uid, fpath))
                                encontrados += 1
                                
            conn.commit()
            print(f"   ✅ Fim da varredura. {encontrados} arquivos vinculados ao Dauto.")
            
        finally:
            mail.logout()
        
        conn.close()

if __name__ == "__main__":
    main()

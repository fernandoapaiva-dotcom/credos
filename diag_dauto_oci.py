import os
import re
import email
import sqlite3
import json
from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

def run_diag():
    cnpj_credos = '54804458000122'
    config = carregar_configuracoes_db(cnpj_credos)
    scanner = MailScanner(config)

    # 1. Busca Dauto no Banco
    conn = sqlite3.connect(f'credos_{cnpj_credos}.db')
    c = conn.cursor()
    c.execute("SELECT nome, cnpj FROM clientes WHERE nome LIKE '%DAUTO%'")
    rows = c.fetchall()
    if not rows:
        print("❌ Dauto não encontrado no Banco de Dados.")
        return
    
    target_name, target_cnpj = rows[0]
    print(f"🔍 Alvo: {target_name} ({target_cnpj})")

    # 2. Busca Emails
    mail = scanner.conectar()
    if not mail:
        print("❌ Falha na conexão IMAP.")
        return

    scanner._selecionar_pasta_segura(mail, 'INBOX')
    res, data = mail.search(None, 'BODY', 'DAUTO')
    if not data[0]:
        print("❌ Nenhum e-mail com 'DAUTO' no corpo.")
        # Tenta por CNPJ
        cnpj_limpo = re.sub(r'\D', '', target_cnpj)
        res, data = mail.search(None, 'BODY', cnpj_limpo)
        if not data[0]:
            print(f"❌ Nenhum e-mail com CNPJ {cnpj_limpo} no corpo.")
            return

    uids = data[0].split()
    print(f"📥 Emails encontrados: {len(uids)}. Analisando os 10 mais recentes...")

    for uid in uids[-10:]:
        res, msg_data = mail.fetch(uid, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        subject = msg.get('Subject', 'Sem Assunto')
        print(f"\n📧 Email: {subject}")

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart': continue
            fname = part.get_filename()
            if fname and fname.lower().endswith('.pdf'):
                fpath = os.path.join(scanner.pasta_destino, scanner.limpar_nome_arquivo(fname))
                with open(fpath, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                
                meta = scanner.extrair_meta_documento(fpath, target_cnpj, target_name, None, None)
                print(f"   📄 Arquivo: {fname}")
                print(f"      Pertence? {meta.get('pertence_cliente')} | Conflito: {meta.get('conflito_identidade')}")
                
                if meta.get('pertence_cliente'):
                    print(f"      ✅ MATCH CONFIRMADO para {target_name}")

if __name__ == "__main__":
    run_diag()

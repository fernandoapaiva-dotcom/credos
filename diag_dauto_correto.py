import os
import re
import email
import json
from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

def run_diag():
    cnpj_credos = '54804458000122'
    config = carregar_configuracoes_db(cnpj_credos)
    scanner = MailScanner(config)

    target_name = 'DAUTO COELHO DOS SANTOS'
    target_cnpj = '24934648000284' # CORRETO
    nf_alvo = '382'

    print(f"--- BUSCANDO NF {nf_alvo} PARA {target_name} ({target_cnpj}) ---")
    mail = scanner.conectar()
    scanner._selecionar_pasta_segura(mail, 'INBOX')
    
    # Busca por NF 382
    res, data = mail.search(None, 'BODY', nf_alvo)
    if not data[0]:
        print(f"❌ Nenhuma referencia a {nf_alvo} no corpo dos emails.")
        return

    uids = data[0].split()
    print(f"Emails com '{nf_alvo}': {len(uids)}")

    for uid in uids[-5:]: # Analisa os 5 mais recentes
        res, msg_data = mail.fetch(uid, '(RFC822)')
        msg = email.message_from_bytes(msg_data[0][1])
        print(f"\n📧 Email: {msg.get('Subject')}")

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart': continue
            fname = part.get_filename()
            if fname and fname.lower().endswith('.pdf'):
                fpath = os.path.join(scanner.pasta_destino, scanner.limpar_nome_arquivo(fname))
                with open(fpath, 'wb') as f:
                    f.write(part.get_payload(decode=True))
                
                meta = scanner.extrair_meta_documento(fpath, target_cnpj, target_name, None, nf_alvo)
                print(f"   📄 PDF: {fname}")
                print(f"      Identidade conferida? {meta.get('pertence_cliente')}")
                print(f"      Conflito (CNPJ de outro)? {meta.get('conflito_identidade')}")
                print(f"      Todos CNPJs no PDF: {meta.get('cnpjs_encontrados')}")

if __name__ == "__main__":
    run_diag()

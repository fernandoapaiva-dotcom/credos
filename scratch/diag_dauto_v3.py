import sqlite3
import os
import subprocess

db_path = '/app/data/db_54804458000122.db'
repo_path = '/app/data/repository'
cnpj_dauto = '24934648000284'
cnpj_formatado = '24.934.648/0002-84'

def get_pdf_text(path):
    try:
        # Tenta extrair texto simples via strings (mais rápido que pdftotext para uma busca bruta)
        out = subprocess.check_output(['strings', path], stderr=subprocess.STDOUT, timeout=5)
        return out.decode('utf-8', errors='ignore')
    except:
        return ""

def diag():
    print("=== PESQUISA AVANÇADA DE BUNDLES E DAUTO ===")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. Auditoria de Bundles UID 699/700
    for uid in ['699', '700']:
        print(f"\nAuditando UID {uid}:")
        cur.execute("SELECT tipo, num_nf, cnpj_cliente, fpath_local FROM documentos_fiscais WHERE email_uid = ?", (uid,))
        for r in cur.fetchall():
            print(f" - Tipo: {r[0]} | NF: {r[1]} | CNPJ: {r[2]} | File: {os.path.basename(r[3])}")

    # 2. Busca Bruta por CNPJ do Dauto nos arquivos
    print(f"\nBuscando CNPJ {cnpj_formatado} dentro dos PDFs do repositório...")
    found_count = 0
    for root, dirs, files in os.walk(repo_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                fpath = os.path.join(root, file)
                # Busca rápida no conteúdo binário/texto
                with open(fpath, 'rb') as f:
                    content = f.read(5000) # As primeiras 5kb costumam ter os dados do cabeçalho
                    if cnpj_dauto.encode() in content or cnpj_formatado.encode() in content:
                        print(f"✅ CNPJ ENCONTRADO: {fpath}")
                        found_count += 1
                        if found_count > 10: break
        if found_count > 10: break
    
    if found_count == 0:
        print("❌ CNPJ do Dauto não encontrado em nenhum PDF do repositório.")

    conn.close()

if __name__ == "__main__":
    diag()

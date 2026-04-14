import sqlite3
import os
from src.fiscal_parser import FiscalParser

db_path = '/app/data/db_24934648000102.db'
cnpj_dauto = '24934648000284'

def verify():
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    print("--- DOCUMENTOS NO BANCO PARA DAUTO ---")
    c.execute("SELECT num_nf, valor, emissao, tipo_doc, fpath_local FROM documentos_fiscais WHERE cnpj_cliente = ?", (cnpj_dauto,))
    rows = c.fetchall()
    for r in rows:
        print(f"NF: {r[0]} | Val: {r[1]} | Emi: {r[2]} | Tipo: {r[3]} | Path: {r[4]}")
        
    print("\n--- TESTANDO PARSER NOS ARQUIVOS REAIS ---")
    parser = FiscalParser()
    files = [
        '/app/data/repository/diagnostico_1914_2-382-boletos.pdf',
        '/app/data/repository/diagnostico_1914_002SE003000000382.pdf',
        '/app/data/repository_v2/24934648000284_DAUTO_COELHO_DOS_SANTOS/NF-E/1300/1300.xml'
    ]
    
    parsed_data = {}
    for f in files:
        if os.path.exists(f):
            res = parser.extrair_dados(f)
            print(f"File: {os.path.basename(f)} -> {res}")
            parsed_data[os.path.basename(f)] = res
        else:
            print(f"File NOT FOUND: {f}")

    # SIMULAÇÃO DA REGRA DE OURO
    print("\n--- SIMULANDO REGRA DE OURO ---")
    val_bol = parsed_data.get('diagnostico_1914_2-382-boletos.pdf', {}).get('valor')
    val_nfs = parsed_data.get('diagnostico_1914_002SE003000000382.pdf', {}).get('valor')
    
    if val_bol and val_nfs:
        diff = round(val_bol - val_nfs, 2)
        print(f"Boleto ({val_bol}) - NFS ({val_nfs}) = R$ {diff}")
        
        # Procura no banco
        emissao_nfs = parsed_data.get('diagnostico_1914_002SE003000000382.pdf', {}).get('emissao')
        print(f"Buscando NFe com Emissão={emissao_nfs} e Valor={diff}...")
        
        c.execute("""
            SELECT fpath_local FROM documentos_fiscais 
            WHERE cnpj_cliente = ? AND emissao = ? AND valor = ? AND tipo_doc = 'NF-E'
        """, (cnpj_dauto, emissao_nfs, diff))
        match = c.fetchone()
        if match:
            print(f"✅ SUCESSO! NF-e complementar encontrada: {match[0]}")
        else:
            print("❌ FALHA! Nenhuma NF-e complementar encontrada no banco com esses critérios.")
            
    conn.close()

if __name__ == "__main__":
    verify()

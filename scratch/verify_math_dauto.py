import os
import sys
import pdfplumber
import xml.etree.ElementTree as ET

sys.path.insert(0, '/app')
from src.fiscal_parser import FiscalParser

def verify_dauto_math():
    parser = FiscalParser()
    
    # Arquivos conhecidos do Dauto (Março)
    files = [
        ('/app/data/repository/diagnostico_1914_002SE003000000382.pdf', 'NFS 382'),
        ('/app/data/repository_v2/24934648000284_DAUTO_COELHO_DOS_SANTOS/nf-e/1300/manual_1915_53260354804458000122550010000013001000051556-procNFe.xml', 'NFe 1300 (XML)'),
        ('/app/data/repository/diagnostico_1914_2-382-boletos.pdf', 'Boleto 382')
    ]
    
    print("--- VERIFICAÇÃO MATEMÁTICA DAUTO (MARÇO) ---")
    results = {}
    for fpath, label in files:
        if not os.path.exists(fpath):
            print(f"❌ {label}: Arquivo não encontrado em {fpath}")
            continue
        
        dados = parser.extrair_dados(fpath)
        if dados:
            print(f"✅ {label}: Valor={dados['valor']}, Emissão={dados['emissao']}")
            results[label] = dados['valor']
        else:
            print(f"⚠️ {label}: Falha na extração de dados.")
            
    if 'NFS 382' in results and 'NFe 1300 (XML)' in results and 'Boleto 382' in results:
        v_nfs = results['NFS 382'] or 0.0
        v_nfe = results['NFe 1300 (XML)'] or 0.0
        v_bol = results['Boleto 382'] or 0.0
        soma = v_nfs + v_nfe
        print(f"\nMATEMÁTICA: {v_nfs} (NFS) + {v_nfe} (NFE) = {soma}")
        print(f"VALOR ALVO (Boleto): {v_bol}")
        if abs(soma - v_bol) < 0.05:
            print("🚀 SOMA PERFEITA! A REGRA MATEMÁTICA ESTÁ VALIDADA.")
        else:
            print("❌ SOMA NÃO BATE.")

if __name__ == "__main__":
    verify_dauto_math()

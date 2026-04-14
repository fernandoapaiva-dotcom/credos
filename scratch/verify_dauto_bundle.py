import os
import sqlite3
import re
from src.manager import Manager
from src.database import carregar_configuracoes_db

UNIT_CNPJ = "54804458000122" # Servsolda
DAUTO_CNPJ = "24934648000284"
NF_ALVO = "382"

def verify_bundle():
    print(f"🧐 VALIDANDO PACOTE UNIFICADO PARA DAUTO (NF {NF_ALVO})")
    
    config = carregar_configuracoes_db(UNIT_CNPJ)
    manager = Manager(UNIT_CNPJ)
    
    # Simula a estrutura de itens que o sistema recebe
    itens = [{
        'numero_nf': NF_ALVO,
        'pagador': 'DAUTO COELHO DOS SANTOS',
        'vencimento': '2026-04-30', # Chute para simulação
        'principal': 100.0,
        'total': 100.0,
        'valor': 100.0
    }]
    
    # O método 'buscar_e_zipar_documentos' agora usa a Janela Temporal de 48h
    # Ele deve encontrar a NF 382 (Serviço) E a nota de peças correspondente
    # que o meu resgate exaustivo acabou de indexar.
    
    zip_path, arquivos = manager.buscar_e_zipar_documentos("DAUTO COELHO DOS SANTOS", itens)
    
    if zip_path and os.path.exists(zip_path):
        print(f"\n📦 PACOTE GERADO COM SUCESSO: {zip_path}")
        print(f"📄 ARQUIVOS INCLUÍDOS NO BUNDLE:")
        for f in arquivos:
            print(f"   - {os.path.basename(f)}")
            
        # Verifica se temos tanto Peças (NF-E) quanto Serviço (NF-S)
        tem_servico = any('382' in f for f in arquivos)
        tem_material = any('NFe' in f or '6681' in f for f in arquivos) # 6681 é um exemplo de NF material
        
        if tem_servico:
            print("\n✅ NOTA DE SERVIÇO LOCALIZADA NO PACOTE.")
        if tem_material:
            print("✅ NOTA DE MATERIAL LOCALIZADA NO PACOTE.")
        else:
            # Lista todos os tipos no banco para o Dauto para debug final
            print("\n--- DEBUG: Outros documentos indexados para o Dauto ---")
            conn = sqlite3.connect(f"/app/data/db_{UNIT_CNPJ}.db")
            cur = conn.cursor()
            cur.execute("SELECT num_nf, tipo, fpath_local FROM documentos_fiscais WHERE cnpj_cliente = ?", (DAUTO_CNPJ,))
            for r in cur.fetchall():
                print(f"   NF: {r[0]} | Tipo: {r[1]} | Path: {os.path.basename(r[2])}")
            conn.close()
    else:
        print("❌ Falha ao gerar o pacote unificado.")

if __name__ == "__main__":
    verify_bundle()

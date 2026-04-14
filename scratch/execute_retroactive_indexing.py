import os
import sys

# Garante que o script consiga importar do src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import carregar_todas_unidades_db
from src.proactive_scanner import ProactiveScanner

def executar_varredura_mestre():
    print("🚀 INICIANDO ANÁLISE RETROATIVA DE DOCUMENTOS (180 DIAS) 🚀")
    
    unidades = carregar_todas_unidades_db()
    scanner_worker = ProactiveScanner()
    
    for u in unidades:
        cnpj = u['empresa_cnpj']
        nome = u['empresa_nome']
        
        print(f"\n--- Processando Unidade: {nome} ({cnpj}) ---")
        try:
            # Varre 180 dias (~6 meses)
            sucesso = scanner_worker.indexar_retroativo(cnpj, dias=180)
            if sucesso:
                print(f"✅ Sincronização histórica concluída para {nome}")
            else:
                print(f"⚠️ Nenhuma fatura encontrada no histórico para {nome}")
        except Exception as e:
            print(f"❌ Erro ao sincronizar histórico de {nome}: {e}")

    print("\n✨ FIM DA VARREDURA MESTRE ✨")

if __name__ == "__main__":
    executar_varredura_mestre()

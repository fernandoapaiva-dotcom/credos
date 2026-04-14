import sys
import os

# Adiciona o diretório src ao path para importar o Manager
sys.path.append(os.getcwd())

# Comentado o ambiente DATABASE_DIR= "/app/data" para testar com o db_.db do dir atual
# os.environ["DATABASE_DIR"] = "/app/data"

from src.manager import Manager

def test_whatsapp_flow():
    cnpj_empresa = "11504286000169"
    # CPC CONSTRUCOES E PROCESSOS CI está no banco db_11504286000169.db
    cliente = "CPC CONSTRUCOES E PROCESSOS CI"
    
    print(f"--- Iniciando teste de cobrança WhatsApp para: {cliente} ---")
    print(f"Empresa (CNPJ): {cnpj_empresa}")
    
    try:
        # Inicializa o Manager com o CNPJ da empresa
        man = Manager(cnpj_empresa=cnpj_empresa)
        
        # Tenta disparar a cobrança específica
        # canais_selecionados garante que vai pelo WhatsApp
        res = man.cobrar_cliente_especifico(
            nome_cliente=cliente, 
            canais_selecionados=["whatsapp"]
        )
        print("Resultado do processo:", res)
    except Exception as e:
        import traceback
        print(f"Erro durante o teste: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_whatsapp_flow()

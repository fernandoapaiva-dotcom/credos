import os
import json
import sys

# Garante que o Python encontre a pasta 'src' estando na raiz
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.extractor import extrair_dados_boletos
from src.database import inicializar_banco, salvar_dados_no_banco, get_connection
from src.manager import Manager

def testar_sistema():
    print("🚀 Iniciando Teste de Ciclo Completo - CREDOS")
    inicializar_banco()
    
    # Configurações de teste
    caminho_pdf = "data/BoletosAberto-SERVSOLDA (1).PDF"
    cache_file = "data/cache_extracao.json" # O arquivo que você criou manualmente
    cnpj_servweld = "11504286000169"

    # --- PASSO 1: EXTRAÇÃO COM LÓGICA DE CACHE ---
    print("\n--- PASSO 1: Obtendo dados dos títulos ---")
    
    if os.path.exists(cache_file):
        print(f"📦 Arquivo de cache encontrado! Lendo dados de: {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            dados_extraidos = json.load(f)
        print("✅ Dados carregados do cache com sucesso (API ignorada).")
    else:
        print("🔍 Cache não encontrado. Tentando chamar Gemini API...")
        try:
            dados_extraidos = extrair_dados_boletos(caminho_pdf, cnpj_servweld)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(dados_extraidos, f, indent=4, ensure_ascii=False)
            print("✅ Dados extraídos e salvos em cache.")
        except Exception as e:
            print(f"❌ Erro na API: {e}")
            return

    # --- PASSO 2: PERSISTÊNCIA ---
    print("\n--- PASSO 2: Salvando no Banco de Dados ---")
    conn = get_connection()
    cursor = conn.cursor()
    
    # Cadastramos o WhatsApp de teste para a SWS (que está no seu JSON manual)
    cursor.execute("""
        INSERT OR REPLACE INTO clientes (cnpj_cpf, razao_social, whatsapp) 
        VALUES ('SWS ESQUADRIA DE ALUMINIO COME', 'SWS ESQUADRIA DE ALUMINIO COME', '5561999999999')
    """)
    conn.commit()
    conn.close()
    
    salvar_dados_no_banco(dados_extraidos, cnpj_servweld)

    # --- PASSO 3: COBRANÇA AGRUPADA ---
    print("\n--- PASSO 3: Testando Agrupamento e Mensagem ---")
    mgr = Manager(cnpj_servweld)
    log_cobranca = mgr.executar_cobranca_agrupada()
    
    for log in log_cobranca:
        print(log)

    # --- PASSO 4: CONCILIAÇÃO ---
    print("\n--- PASSO 4: Simulando Título que sumiu (Baixa) ---")
    # Simulamos que a NF 912 sumiu na nova leitura
    dados_simulados = [t for t in dados_extraidos if t['nota_fiscal'] != '912']
    
    alertas = mgr.conciliar_titulos(dados_simulados)
    if alertas:
        for a in alertas:
            print(f"⚠️ Alerta: Título NF {a['nf']} sumiu do relatório. Possível pagamento identificado!")

    print("\n✅ TESTE CONCLUÍDO COM SUCESSO!")

if __name__ == "__main__":
    testar_sistema()
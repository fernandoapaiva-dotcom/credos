import sys
import os

# Adiciona o diretório atual ao path para importar src
sys.path.append('/app')

from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

def test_dauto_aggregation():
    cnpj_servsolda = "54804458000122"
    config = carregar_configuracoes_db(cnpj_servsolda)
    
    scanner = MailScanner(config)
    
    # Dados do Dauto
    cnpj_dauto = "24934648000284"
    nome_dauto = "DAUTO COELHO DOS SANTOS"
    nf_alvo = "382"
    valor_total = 471.91
    
    print(f"🚀 Iniciando teste de agregação para {nome_dauto} | NF {nf_alvo}")
    
    arquivos = scanner.baixar_anexos_por_nf_validado(
        numero_nf=nf_alvo,
        cnpj_cliente=cnpj_dauto,
        nome_cliente=nome_dauto,
        valor=valor_total
    )
    
    print(f"\n✅ Resultados encontrados: {len(arquivos)} arquivo(s)")
    for f in arquivos:
        print(f"   - {os.path.basename(f)}")
        
    if len(arquivos) >= 2:
        print("\n🎉 SUCESSO! Múltiplos arquivos (Venda/Serviço) foram localizados e agregados.")
    elif len(arquivos) == 0:
        print("\n❌ FALHA: Nenhum arquivo encontrado. Verifique se o scanner está conseguindo ler os e-mails.")
    else:
        print("\n⚠️ PARCIAL: Apenas um arquivo foi encontrado.")

if __name__ == "__main__":
    test_dauto_aggregation()

import os
import sys

# Adiciona o diretório atual ao path para importar src
sys.path.append(os.getcwd())

from src.mail_scanner import MailScanner
from src.database import carregar_configuracoes_db

cnpj_empresa = "54804458000122" # Servsolda
config = carregar_configuracoes_db(cnpj_empresa)
scanner = MailScanner(config)

# Dados do Dauto
cliente_nome = "DAUTO COELHO DOS SANTOS"
cnpj_dauto = "24934648000284"
nf_dauto = "382"

print(f"🚀 Iniciando Indexação Manual para {cliente_nome} (NF {nf_dauto})...")
try:
    path = scanner.baixar_anexos_por_nf_validado(
        nf_dauto, 
        cnpj_dauto, 
        cliente_nome,
        vencimento="27/03/2026",
        valor=[471.91]
    )
    if path:
        print(f"✅ Documentos encontrados e indexados:")
        for p in path:
            print(f"   - {p}")
    else:
        print("❌ Nenhum documento encontrado no IMAP para esta NF.")
except Exception as e:
    print(f"🔥 Erro durante a indexação: {e}")

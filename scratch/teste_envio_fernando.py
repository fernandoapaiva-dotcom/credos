import sys
import os

# Adiciona o diretório /app ao path para importar src
sys.path.append('/app')

from src.database import carregar_configuracoes_db
from src.manager import Manager

def testar_envio_fernando():
    cnpj = '54804458000122' # Servsolda
    numero_fernando = '556198334833'
    
    config = carregar_configuracoes_db(cnpj)
    manager = Manager(cnpj)
    
    msg = (
        "*Teste Analu - Unificação de Documentos*\n\n"
        "Olá Fernando! Segue um exemplo de como os documentos (NF-e + NFS-e + Boleto) "
        "estão chegando para o cliente agora que implementamos a lógica de agrupamento."
    )
    
    print(f"🚀 Enviando mensagem para {numero_fernando}...")
    # O Manager já usa a instância baseada no CNPJ (54804458000122)
    res_msg = manager.evo.enviar_mensagem_texto(numero_fernando, msg)
    print(f"   Status Mensagem: {res_msg}")
    
    # Caminho do arquivo dentro do container
    arquivo_path = '/app/data/repository/02133281598198/NF-S/2-1349-boletos.pdf'
    
    if os.path.exists(arquivo_path):
        print(f"📎 Enviando arquivo: {os.path.basename(arquivo_path)}...")
        res_file = manager.evo.enviar_midia(numero_fernando, arquivo_path)
        print(f"   Status Arquivo: {res_file}")
    else:
        print(f"⚠️  Arquivo não encontrado no container: {arquivo_path}")

if __name__ == "__main__":
    testar_envio_fernando()

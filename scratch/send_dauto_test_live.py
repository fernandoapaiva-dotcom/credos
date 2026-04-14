import sys
import os
import json
from datetime import datetime

# Adiciona o diretório atual ao path para importar src
sys.path.append(os.getcwd())

from src.manager import Manager
from src.database import conectar, salvar_configuracoes_db

def send_dauto_test_live():
    # Parâmetros
    target_company_cnpj = "54804458000122" # Centro Oeste
    target_client_name = "DAUTO COELHO DOS SANTOS"
    target_client_cnpj = "24934648000284"
    target_phone = "5561998334833" # Número do usuário
    nf_alvo = "382"

    print(f"--- Iniciando envio de TESTE LIVE para {target_client_name} ---")
    print(f"--- Destinatario: {target_phone} ---")

    # Inicializa Manager
    mgr = Manager(target_company_cnpj)
    
    # Prepara mock do item/título
    # O scanner precisa desses valores para validar identidades se falhar no nome
    itens = [{
        'pagador': target_client_name,
        'numero_nf': nf_alvo,
        'vencimento': '30/03/2026', # Data aproximada do Dauto case
        'valor': 1300.0,            # Valor aproximado do boleto
        'principal': 1100.0,        # Valor aproximado da NFS (exemplo de soma)
        'total': 1300.0,
        'status': 'Aberto'
    }]

    print(f"--- Buscando documentos nos e-mails (IMAP) para NF {nf_alvo}... ---")
    try:
        # Tenta buscar os anexos (isso vai rodar a lógica de soma NFS + NFe)
        # Passamos o CNPJ do cliente manualmente para ajudar o scanner se ele não encontrar no DB
        zip_path, arquivos_temp = mgr.buscar_e_zipar_documentos(target_client_name, itens)
        
        if not zip_path or not os.path.exists(zip_path):
            print("!!! Falha: Documentos nao encontrados nos e-mails para este cliente/NF.")
            return

        print(f"+++ Arquivos encontrados: {[os.path.basename(f) for f in arquivos_temp]}")
        print(f"+++ Pacote gerado: {zip_path}")

        # Mensagem de teste
        msg = (
            f"--- TESTE SISTEMA CREDOS ---\n\n"
            f"Ola, este e um envio de teste para o cliente {target_client_name}.\n"
            f"NF Alvo: {nf_alvo}\n\n"
            f"Este envio demonstra a funcionalidade de unificacao de NFS + NFe "
            f"quando o valor do boleto e composto por ambos.\n\n"
            f"Por favor, confira os arquivos anexados abaixo."
        )

        print("--- Enviando para WhatsApp... ---")
        mgr.evo.enviar_mensagem_texto(target_phone, msg)
        import time
        time.sleep(1) # Pequena pausa
        res = mgr.evo.enviar_midia(target_phone, zip_path)
        
        if res:
            print("--- SUCESSO! Envio concluido. ---")
        else:
            print("!!! Erro ao enviar midia via Evolution API.")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Erro crítico: {e}")

if __name__ == "__main__":
    send_dauto_test_live()

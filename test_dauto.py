import sys
import os
import json
import base64

from dotenv import load_dotenv
load_dotenv('.env')

sys.path.insert(0, '/app')
try:
    from src.manager import Manager
    from src.database import conectar
except ImportError as e:
    print(f"Erro de importacao (certifique-se de estar rodando dentro do credos-backend): {e}")
    sys.exit(1)

cnpj = "54804458000122"
nome = "DAUTO COELHO DOS SANTOS"
numero_teste = "5561998334833"

print("--- INICIANDO TESTE NA NOTA DO DAUTO DEV (SEM MODIFICAR DADOS OFICIAIS) ---")

mgr = Manager(cnpj)

# Força o título para realizar o teste de scan de e-mail e envio
tit_parsed = [{
    'pagador': nome,
    'numero_nf': '382',
    'status': 'Aberto',
    'cnpj': '24934648000284' # CNPJ correto do Dauto
}]

# DEBUG: Mostrar o que está acontecendo no scanner
import src.mail_scanner
src.mail_scanner.DEBUG_SCANNER = True 


print(f"Buscando as notas usando FILTRO FORTE DE CONTAMINAÇÃO para {len(tit_parsed)} titulos em aberto...")

zip_path, arquivos_temp = mgr.buscar_e_zipar_documentos(nome, tit_parsed)

print(f"Zip File: {zip_path}")
print(f"Arquivos Temporarios Aprovados: {arquivos_temp}")

if zip_path and os.path.exists(zip_path):
    print(f"Enviando resultado para {numero_teste} via Whatsapp...")
    msg = f"TESTE CREDOS - Analu Inteligente\nNotas Isoladas do Cliente: {nome}\nConfira se so trouxe a NF verdadeira!"
    
    mgr.evo.enviar_mensagem_texto(numero_teste, msg)
    import time
    time.sleep(2)  # pause small
    res = mgr.evo.enviar_midia(numero_teste, zip_path)
    
    if res:
        print("CONCLUIDO: TESTE ENVIADO NO WHATSAPP")
    else:
        print("FALHA: AO ENVIAR ARQUIVO PARA WHATSAPP. Arquivo pode ser muito grande ou evolucao indisponivel.")
else:
    print("FALHA: Scanner nao aprovou nenhum documento que batesse a identidade rigidamente.")

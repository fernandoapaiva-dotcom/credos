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

conn = conectar(cnpj)
conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
titulos = conn.cursor().execute("SELECT * FROM titulos WHERE pagador LIKE '%DAUTO%' AND status='Aberto'").fetchall()
conn.close()

if not titulos:
    print("Nenhum titulo em aberto do Dauto para testar!")
    sys.exit(1)

tit_parsed = []
for t in titulos:
    tit_parsed.append(t)

print(f"Buscando as notas usando FILTRO FORTE DE CONTAMINAÇÃO para {len(titulos)} titulos em aberto...")

zip_path, arquivos_temp = mgr.buscar_e_zipar_documentos(nome, tit_parsed)

print(f"📦 Zip File: {zip_path}")
print(f"📄 Arquivos Temporários Aprovados: {arquivos_temp}")

if zip_path and os.path.exists(zip_path):
    print(f"🚀 Enviando resultado para {numero_teste} via Whatsapp...")
    msg = f"TESTE CREDOS - Analu Inteligente\nNotas Isoladas do Cliente: {nome}\nConfira se só trouxe a NF verdadeira!"
    
    mgr.evo.enviar_mensagem_texto(numero_teste, msg)
    import time
    time.sleep(2)  # pause small
    res = mgr.evo.enviar_midia(numero_teste, zip_path)
    
    if res:
        print("✅ TESTE ENVIADO CONCLUÍDO NO WHATSAPP")
    else:
        print("❌ FALHA AO ENVIAR ARQUIVO PARA WHATSAPP. Arquivo pode ser muito grande ou evolução indisponível.")
else:
    print("❌ Falha! Scanner não aprovou nenhum documento que batesse a identidade rigidamente.")

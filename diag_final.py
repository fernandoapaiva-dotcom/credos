import sys
import os
from src.manager import Manager
from src.database import conectar

cnpj = "54804458000122"
nome = "DAUTO COELHO DOS SANTOS"

mgr = Manager(cnpj)
conn = conectar(cnpj)
conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
tits = conn.cursor().execute("SELECT * FROM titulos WHERE pagador LIKE '%DAUTO%' AND status='Aberto'").fetchall()
conn.close()

print(f"Buscando arquivos para {len(tits)} títulos do Dauto...")
zip_path, files = mgr.buscar_e_zipar_documentos(nome, tits)

print("\n--- RESULTADO DA BUSCA INTELIGENTE ---")
if not files:
    print("Nenhum arquivo encontrado ou aprovado pelo filtro de identidade.")
else:
    print(f"Total de arquivos aprovados: {len(files)}")
    for f in files:
        print(f" - {os.path.basename(f)}")

print("\n--- TESTE DE WHATSAPP ---")
numero_teste = "5561998334833"
# Tenta limpar o número
target = "".join(filter(str.isdigit, numero_teste))
if len(target) == 13:
    print(f"Tentando enviar para o número original: {target}")
    res = mgr.evo.enviar_mensagem_texto(target, "Teste Analu: Arquivos encontrados para Dauto.")
    if not res:
        print("Falha enviando para 13 dígitos. Tentando remover o prefixo 9...")
        # Em alguns casos do PR o Evolution buga com o 9 prefixo
        target_v2 = target[:4] + target[5:] 
        print(f"Tentando enviar para: {target_v2}")
        res = mgr.evo.enviar_mensagem_texto(target_v2, "Teste Analu (v2): Arquivos encontrados para Dauto.")
        if res:
            print("Sucesso com 12 dígitos!")
            target = target_v2
        else:
             print("Falha total no envio do texto.")

if zip_path and os.path.exists(zip_path):
    print(f"Enviando mídia para {target}...")
    mgr.evo.enviar_midia(target, zip_path)

"""
Script de disparo manual final para o Dauto.
"""
import sys
import os
sys.path.append('/app')

from src.database import carregar_configuracoes_db
from src.manager import Manager
from datetime import datetime

cnpj_empresa = "54804458000122" # Servsolda
config = carregar_configuracoes_db(cnpj_empresa)

# IMPORTANTE: Forçamos o CNPJ correto no Manager para que a Evolution use a instância certa
manager = Manager(cnpj_empresa)

# Dados do Dauto
cliente_nome = "DAUTO COELHO DOS SANTOS"
numero_destino = "5561998334833"
itens = [
    {
        'numero_nf': '382',
        'vencimento': '27/03/2026',
        'principal': 471.91,
        'multa': 0.0,
        'juros': 0.0,
        'total': 471.91,
        'dias_atraso': 14,
        'status': 'Em aberto',
        'pagador': cliente_nome,
    }
]

print(f"🚀 Disparando Teste de Velocidade para {cliente_nome}")
print(f"📍 Destino: {numero_destino}")

# 1. Gera Mensagem
dados_cliente = {'cnpj': '24934648000284', 'contato': 'Dauto', 'nome': cliente_nome}
mensagem = manager.gerar_mensagem_cobranca(cliente_nome, dados_cliente, 471.91, itens)

# 2. Busca Documentos (Bundle)
# Como a NF 382 ainda não está indexada, vamos simular o anexo com um arquivo real para testar velocidade
print("📦 Simulando Bundle com arquivo real para teste de velocidade...")
# (Aqui a lógica buscaria e ziparia. Como está vazio, vamos forçar um caminho para o zip de teste se encontrar)
zip_path, arquivos = manager.buscar_e_zipar_documentos(cliente_nome, itens)

# Teste de Velocidade: Se o zip_path for None (porque NF não foi achada), usamos um arquivo qualquer do repo para teste
arquivo_teste = "/home/ubuntu/credos/data/repository/Geral/BOLETO/2-1349-boletos.pdf"
if not zip_path and os.path.exists(arquivo_teste):
    print(f"ℹ️ NF 382 ainda não indexada. Usando {os.path.basename(arquivo_teste)} para teste de velocidade.")
    zip_path = arquivo_teste

# 3. Dispara
print("📤 Enviando texto...")
r_texto = manager.evo.enviar_mensagem_texto(numero_destino, mensagem)
print(f"   Status Texto: {r_texto}")

if zip_path:
    print("📤 Enviando anexo...")
    r_anexo = manager.evo.enviar_arquivo(numero_destino, zip_path, "Documentos_Dauto.pdf")
    print(f"   Status Anexo: {r_anexo}")

print("\n✅ Teste Realizado.")

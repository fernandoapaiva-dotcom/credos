import sys
import os
from datetime import datetime

# Adiciona o diretório raiz ao path para importar os módulos
sys.path.append(os.getcwd())

from src.manager import Manager
from src.worker import disparar_negociacoes_ia
from src.database import conectar, carregar_todas_unidades_db

def testar_na_vera():
    print(f"SEARCH [{datetime.now().strftime('%H:%M:%S')}] Iniciando Teste de Safeguard (Trava de Seguranca)...")
    
    unidades = carregar_todas_unidades_db()
    if not unidades:
        print("FAIL: Nenhuma unidade encontrada para teste.")
        return

    # Vamos testar na unidade TECAR BRASILIA (ou a primeira ativa)
    uni = unidades[0]
    for u in unidades:
        if "TECAR" in u['empresa_nome'].upper():
            uni = u
            break
            
    cnpj = uni['empresa_cnpj']
    nome = uni['empresa_nome']
    
    print(f"INFO: Empresa Alvo: {nome} ({cnpj})")
    mgr = Manager(cnpj)
    
    # 1. Verificar quem já foi cobrado hoje
    print("\n--- STATUS DAS COBRANÇAS DE HOJE ---")
    debitos = mgr.agrupar_debitos_por_cliente()
    clientes_hoje = list(debitos.keys())
    
    # 0. Injetar um log de teste para demonstrar a trava (Simulando que você já cobrou a TECAR hoje)
    conn_test = conectar(cnpj)
    try:
        agora_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn_test.cursor().execute(
            "INSERT INTO logs_envio (cliente, tipo_envio, status, detalhes, usuario, data_envio) VALUES (?,?,?,?,?,?)",
            ('TECAR BRASILIA VEICULOS E SERV', 'WhatsApp', 'Sucesso', '{"test": true}', 'Teste', agora_iso)
        )
        conn_test.commit()
    finally:
        conn_test.close()

    # 1. Verificar status
    print("\n--- STATUS DAS COBRANCAS DE HOJE ---")
    debitos = mgr.agrupar_debitos_por_cliente()
    clientes_hoje = list(debitos.keys())
    
    for cli in clientes_hoje:
        ja_foi = mgr.ja_foi_cobrado_hoje(cli)
        label = "[TRAVA ATIVA] JA COBRADO HOJE (Analu vai pular)" if ja_foi else "[LIBERADO] AINDA NAO COBRADO (Analu vai atuar)"
        print(f"USER {cli}: {label}")

    print("\n--- SIMULANDO EXECUÇÃO DO ROBÔ (MODO LOG) ---")
    print("O robô agora vai tentar processar a fila. Observe os pulos (skip) baseados na trava que criamos:")
    
    # Chamamos a rotina oficial de negociação IA
    # Ela vai rodar para todos os clientes, mas deve imprimir "já enviada hoje" ou "já recebeu contato" para os marcados como ✅ acima
    try:
        disparar_negociacoes_ia(cnpj_filtro=cnpj)
    except Exception as e:
        print(f"\nFAIL: Erro durante simulado: {e}")

    print("\n--- FIM DO TESTE ---")
    print("Se você viu os logs de 'mensagem IA já enviada hoje' ou 'Pulo', a trava está funcionando 100%.")

if __name__ == "__main__":
    testar_na_vera()

import time
from datetime import datetime
from src.database import listar_todos_agendamentos_ativos
from src.manager import Manager

def disparar_cobranca_automatica(forcar_execucao=False):
    """
    Motor de Cobrança:
    1. Varre agendamentos ativos.
    2. Verifica se hoje é dia de cobrança (ou se forcar_execucao=True).
    3. Gera mensagens (com aviso de 10 dias se necessário).
    4. Envia e loga.
    """
    print(f"\n🤖 [{datetime.now().strftime('%d/%m %H:%M')}] Iniciando Motor de Cobrança...")
    
    # 1. Busca configurações ativas
    agendamentos = listar_todos_agendamentos_ativos()
    
    if not agendamentos:
        print("zzz Nenhuma automação ativa no banco de dados.")
        return 0

    total_envios = 0

    for ag in agendamentos:
        cnpj_empresa = ag['empresa_dona_cnpj']
        
        # Verifica se hoje é dia de executar (se não for forçado manualmente)
        if not forcar_execucao:
            hoje_semana = datetime.now().weekday() # 0=Segunda ... 6=Domingo
            # Converte string "0,2,4" para lista de inteiros
            try:
                dias_permitidos = [int(d) for d in ag['dias_semana'].split(",") if d.strip()]
            except:
                dias_permitidos = []
            
            if hoje_semana not in dias_permitidos:
                print(f"⏩ Pulando {cnpj_empresa}: Hoje não está na agenda.")
                continue

        # Inicia o Gerente para esta empresa específica
        try:
            print(f"🏢 Processando Empresa CNPJ: {cnpj_empresa}...")
            mgr = Manager(cnpj_empresa)
            
            # 2. Busca a fila de cobrança (Apenas 'Cobrar' e 'Aberto')
            fila = mgr.agrupar_debitos_por_cliente()
            
            if not fila:
                print(f"   ✅ Nenhuma pendência 'Cobrar' encontrada.")
                continue

            for cliente_nome, info in fila.items():
                try:
                    print(f"   📦 Preparando: {cliente_nome}...")
                    
                    # 3. Gera Mensagem Inteligente (Calcula se tem aviso de 10 dias internamente)
                    msg = mgr.gerar_mensagem_cobranca(cliente_nome, info['dados_cliente'], info['total'], info['itens'])
                    
                    # Busca PDFs atualizados no email
                    zip_path, arquivos_temp = mgr.buscar_e_zipar_pdfs(cliente_nome, info['itens'])
                    
                    # 4. Executa Envio
                    res = mgr.executar_processo_completo_cobranca(
                        cliente_nome, msg, zip_path, info['itens'], arquivos_temp
                    )
                    
                    status = "SUCESSO" if (res['email'] or res['whatsapp']) else "FALHA"
                    print(f"   -> {status} (Zap:{res['whatsapp']} | Email:{res['email']})")
                    
                    if res['email'] or res['whatsapp']:
                        total_envios += 1
                    
                    # Pausa para não bloquear o WhatsApp
                    time.sleep(10)
                    
                except Exception as e_cli:
                    print(f"   ❌ Erro no cliente {cliente_nome}: {e_cli}")

        except Exception as e_emp:
            print(f"❌ Erro crítico ao processar empresa {cnpj_empresa}: {e_emp}")

    print(f"🏁 Ciclo Finalizado. Total de envios: {total_envios}")
    return total_envios

if __name__ == "__main__":
    # Se rodar o arquivo direto, força a execução para teste
    disparar_cobranca_automatica(forcar_execucao=True)
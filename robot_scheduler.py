import schedule
import time
import datetime
import logging
import os

# Importações do seu projeto
from src.database import carregar_todas_unidades_db
from src.manager import Manager
from src.ai_handler import get_ai_response
from src.mail_scanner import MailScanner
from src.mailer import Mailer

# Configuração de Logs (Cria um arquivo robot.log para você ver o que aconteceu)
logging.basicConfig(
    filename='robot.log', 
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    encoding='utf-8'
)

# Mapeamento: Python datetime.weekday() (0=Segunda) vs Seu Banco
DIAS_MAP = {
    "Segunda": 0, "Terça": 1, "Quarta": 2, "Quinta": 3, 
    "Sexta": 4, "Sábado": 5, "Domingo": 6
}

def executar_rotina_de_cobranca():
    agora = datetime.datetime.now()
    dia_semana_hoje = agora.weekday() # 0 a 6
    hora_atual = agora.strftime("%H:%M")
    
    print(f"⏰ [Check] {hora_atual} - Verificando agendamentos...")
    
    # Carrega todas as empresas do banco
    try:
        unidades = carregar_todas_unidades_db()
    except Exception as e:
        print(f"❌ Erro ao ler banco de dados: {e}")
        return

    for uni in unidades:
        nome_empresa = uni.get('empresa_nome', 'Desconhecida')
        
        try:
            # --- 1. VALIDAÇÃO DE AGENDAMENTO ---
            # Verifica se a empresa tem dias configurados
            dias_configurados = uni.get('agenda_dias', []) # Já vem como lista do DB novo
            hora_configurada = uni.get('agenda_hora', "08:00")
            
            # Converte os nomes dos dias para números
            dias_numeros = [DIAS_MAP[d] for d in dias_configurados if d in DIAS_MAP]
            
            # Se HOJE não for dia de cobrança OU não for a hora exata, pula
            if dia_semana_hoje not in dias_numeros:
                continue
                
            if hora_atual != hora_configurada:
                continue
            
            # --- INÍCIO DA EXECUÇÃO ---
            logging.info(f"🚀 Iniciando rotina para: {nome_empresa}")
            print(f"🚀 Executando rotina: {nome_empresa}")
            
            # Instancia o Manager com as configs dessa empresa específica
            mgr = Manager(uni['empresa_cnpj'])
            
            # --- 2. LEITURA DE E-MAILS (SCANNER) ---
            if uni.get('auto_scan'):
                print(f"   📧 Escaneando e-mails para {nome_empresa}...")
                scanner = MailScanner(uni)
                qtd_baixada = scanner.escaneia_e_baixa_pdfs()
                if qtd_baixada:
                    logging.info(f"{nome_empresa}: {len(qtd_baixada)} novos boletos baixados.")
                    # Opcional: Aqui você poderia chamar o extrator automaticamente
            
            # --- 3. COBRANÇA (WHATSAPP E E-MAIL) ---
            # Verifica débitos
            relatorio = mgr.agrupar_debitos_por_cliente()
            
            if not relatorio:
                logging.info(f"{nome_empresa}: Nenhum débito pendente hoje.")
                continue

            # Prepara o Mailer se estiver ativado
            mailer = Mailer(uni) if uni.get('auto_mail') else None
            
            for cliente, info in relatorio.items():
                total_divida = info['total']
                itens = info['itens'] # Lista de NFs/Boletos
                
                print(f"   -> Cobrando {cliente} (R$ {total_divida:.2f})...")
                
                # Gera texto com IA (Gemini)
                prompt = f"Crie uma mensagem curta e educada de cobrança para o cliente {cliente}. O total devido é R$ {total_divida}. As notas são: {', '.join(itens)}."
                mensagem_ia = get_ai_response(prompt)
                if not mensagem_ia:
                    mensagem_ia = f"Olá {cliente}, identificamos pendências no valor de R$ {total_divida} referente às notas {', '.join(itens)}."

                # A. Enviar WhatsApp
                if uni.get('auto_zap'):
                    sucesso_zap = mgr.enviar_cobranca_multipla(cliente, mensagem_ia, itens)
                    if sucesso_zap:
                        logging.info(f"WhatsApp enviado para {cliente}")
                
                # B. Enviar E-mail
                if uni.get('auto_mail') and mailer:
                    # Busca email do cliente no banco
                    email_destino = mgr.get_email_cliente(cliente)
                    
                    if email_destino:
                        # Busca os caminhos físicos dos PDFs para anexar
                        arquivos_anexos = mgr.buscar_arquivos_das_nfs(itens)
                        
                        sucesso_mail, msg_mail = mailer.enviar_email_cobranca(
                            destinatario=email_destino,
                            cliente_nome=cliente,
                            info_divida=info, # Passa o dicionário completo
                            arquivos_anexos=arquivos_anexos
                        )
                        logging.info(f"E-mail para {cliente}: {msg_mail}")
                    else:
                        logging.warning(f"Sem e-mail cadastrado para {cliente}")
                
                # Pequena pausa para não travar APIs
                time.sleep(5)

            logging.info(f"✅ Rotina finalizada para {nome_empresa}")
            
        except Exception as e:
            error_msg = f"Erro crítico na empresa {nome_empresa}: {str(e)}"
            print(error_msg)
            logging.error(error_msg)

# Agendamento: Roda a função a cada 1 minuto para checar se "bateu" a hora configurada
schedule.every().minute.do(executar_rotina_de_cobranca)

if __name__ == "__main__":
    print("🤖 Robô Credos Ativado.")
    print("Mantenha esta janela aberta para processar os agendamentos.")
    print("Pressione Ctrl+C para parar.")
    
    # DICA: Se quiser testar AGORA sem esperar o horário, descomente a linha abaixo:
    # executar_rotina_de_cobranca()
    
    while True:
        schedule.run_pending()
        time.sleep(30) # Verifica a cada 30 segundos
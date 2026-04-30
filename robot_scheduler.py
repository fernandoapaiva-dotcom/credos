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
from src.backup_manager import perform_backup
from src.worker import (
    verificar_retorno_cartorio, processar_fila_cartorio, 
    disparar_negociacoes_ia, verificar_promessas_d1
)

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
            
            # Se HOJE não for dia de cobrança, pula
            if dia_semana_hoje not in dias_numeros:
                continue
                
            # Verifica se está dentro da janela de 10 minutos do horário configurado
            try:
                # Converte strings de horário para objetos datetime para comparação segura
                ref_dt = datetime.datetime.strptime(hora_configurada, "%H:%M")
                now_dt = datetime.datetime.strptime(hora_atual, "%H:%M")
                diff_min = (now_dt - ref_dt).total_seconds() / 60
                
                # Se ainda não chegou a hora ou se já passaram mais de 10 minutos, pula
                if not (0 <= diff_min <= 10):
                    continue
            except Exception as e:
                print(f"⚠️ Erro ao validar janela de horário para {nome_empresa}: {e}")
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
                # Trava de segurança: já cobrado hoje?
                if mgr.ja_foi_cobrado_hoje(cliente):
                    print(f"   ⏭️ {cliente}: Já recebeu cobrança hoje. Pulando.")
                    continue

                total_divida = info['total']
                itens = info['itens'] # Lista de NFs/Boletos
                
                print(f"   -> Cobrando {cliente} (R$ {total_divida:.2f})...")
                
                # Gera texto com IA (Gemini)
                prompt = f"Crie uma mensagem curta e educada de cobrança para o cliente {cliente}. O total devido é R$ {total_divida}. As notas são: {', '.join(itens)}."
                mensagem_ia = get_ai_response(prompt, api_key=mgr.config.get('gemini_api_key'))
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

def rotina_backup_diario():
    agora = datetime.datetime.now().strftime("%H:%M")
    if agora == "12:00":
        print("💾 [Backup] Iniciando backup diário das 12:00...")
        logging.info("Iniciando backup programado (12:00)")
        success, result = perform_backup()
        if success:
            logging.info(f"Backup concluído com sucesso: {result}")
        else:
            logging.error(f"Falha no backup programado: {result}")

def rotina_analu_ia():
    logging.info("🤖 Verificando ciclo de negociação autônoma (Analu)")
    try:
        # A lógica de horários e dias permitidos agora reside internamente no worker.py
        # 1. Verifica promessas vencidas primeiro
        verificar_promessas_d1()
        # 2. Dispara ciclo de 20 dias
        disparar_negociacoes_ia()
    except Exception as e:
        logging.error(f"❌ Erro na rotina Analu IA: {e}")

# Agendamento: 
# Roda a rotina de cobrança a cada 1 minuto
schedule.every().minute.do(executar_rotina_de_cobranca)
# Roda a checagem de backup a cada 1 minuto
schedule.every().minute.do(rotina_backup_diario)
# Processa fila do cartório a cada 5 minutos
schedule.every(5).minutes.do(processar_fila_cartorio)
# Verifica retorno do cartório todo dia às 10:00
schedule.every().day.at("10:00").do(verificar_retorno_cartorio)
# Rotina Analu (IA) roda a cada minuto (a trava de horário está dentro da função de disparo)
schedule.every().minute.do(rotina_analu_ia)

if __name__ == "__main__":
    print("🤖 Robô Credos Ativado.")
    print("Mantenha esta janela aberta para processar os agendamentos.")
    print("Pressione Ctrl+C para parar.")
    
    # DICA: Se quiser testar AGORA sem esperar o horário, descomente a linha abaixo:
    # executar_rotina_de_cobranca()
    
    while True:
        schedule.run_pending()
        time.sleep(30) # Verifica a cada 30 segundos
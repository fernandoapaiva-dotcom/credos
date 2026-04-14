import sys
import os
import sqlite3
from datetime import datetime

# Adicionar caminho do src
sys.path.append('/app')
from src.manager import Manager

def run_wa_test():
    path_options = [
        '/app/data/db_24934648000102.db',
        '/app/data/24934648000102.db',
        '/app/db_24934648000102.db',
        '/app/db_24934648000102.db'
    ]
    db_path = None
    for opt in path_options:
        if os.path.exists(opt):
            db_path = opt
            break
            
    if not db_path:
        print("ERRO: Banco de dados não encontrado em nenhuma localidade esperada.")
        return

    print(f"Usando banco: {db_path}")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 1. Preparar o banco para o teste
    # Garante que o título 382 do Dauto está ativo para cobrança
    print("--- PREPARANDO BANCO ---")
    c.execute("""
        UPDATE titulos 
        SET status = 'Aberto', acao = 'Cobrar' 
        WHERE pagador LIKE '%DAUTO%' AND numero_nf = '382'
    """)
    
    # Remove logs de hoje para ignorar a trava de 'já cobrado hoje'
    hoje = datetime.now().strftime("%Y-%m-%d")
    c.execute("DELETE FROM logs_envio WHERE cliente LIKE '%DAUTO%' AND data_envio LIKE ?", (f"{hoje}%",))
    
    conn.commit()
    print("Banco preparado (Título 382 setado para 'Cobrar' e logs limpados).")
    conn.close()

    # 2. Executar a cobrança via Manager
    print("\n--- DISPARANDO COBRANÇA (WHATSAPP) ---")
    try:
        man = Manager('24934648000102')
        res = man.cobrar_cliente_especifico("DAUTO COELHO DOS SANTOS", canais_selecionados=["whatsapp"])
        print(f"Resultado final: {res}")
    except Exception as e:
        print(f"ERRO ao disparar cobrança: {e}")

if __name__ == "__main__":
    run_wa_test()

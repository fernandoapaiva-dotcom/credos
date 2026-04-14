import sys
import os
import sqlite3

# Adiciona o diretório atual ao path para importar src
sys.path.append('/app')
# Configura o diretório correto do banco no Docker
os.environ['DATABASE_DIR'] = '/app/data'

from src.manager import Manager
from src.database import conectar

def test_send_dauto():
    # Parâmetros do teste
    target_phone = "556198334833"
    nf_alvo = "382"
    cnpj_servsolda = "54804458000122" # ServSolda
    
    mgr = Manager(cnpj_servsolda)
    
    # Busca a cobrança no banco para ter o ID
    db = conectar(cnpj_servsolda)
    cursor = db.cursor()
    # No banco atualizado, o campo é 'pagador' e a tabela é 'titulos'
    cursor.execute("SELECT id, pagador FROM titulos WHERE numero_nf LIKE ? AND pagador LIKE ?", (f'%{nf_alvo}%', '%DAUTO%'))
    row = cursor.fetchone()
    
    if not row:
        print("❌ Titulo do Dauto NF 382 não encontrado no banco.")
        db.close()
        return
    
    debt_id, client_name = row
    print(f"🚀 Iniciando envio de TESTE para {client_name} (ID: {debt_id})")
    
    # Atualiza o telefone do CLIENTE no cadastro
    cursor.execute("UPDATE clientes SET whatsapp = ? WHERE trim(nome) = ?", (target_phone, client_name.strip()))
    db.commit()
    db.close()
    
    print(f"📱 Telefone de {client_name} atualizado para: {target_phone} (Temporário)")

    try:
        # Chama o método de cobrança de título único que cuida de tudo
        print("⏳ Processando...")
        mgr.cobrar_titulo_unico(debt_id, canais_selecionados=["whatsapp"])
        
        print("\n✅ Processo de Cobrança Finalizado.")
        print("Confira o WhatsApp do destinatário.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Erro no envio: {e}")

if __name__ == "__main__":
    test_send_dauto()

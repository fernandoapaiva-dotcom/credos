import os
import sqlite3
import sys

# Garante que o script consiga importar do src
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import carregar_todas_unidades_db, conectar, upsert_contato_global, _normalizar_cnpj

def migrar_contatos():
    print("Iniciando Sincronizacao Global de Contatos...")
    
    unidades = carregar_todas_unidades_db()
    print(f"Encontradas {len(unidades)} unidades para processar.")
    
    total_processado = 0
    total_contatos = 0
    
    for u in unidades:
        nome_unidade = u.get('empresa_nome')
        cnpj_unidade = u.get('empresa_cnpj')
        
        print(f"--- Processando Unidade: {nome_unidade} ({cnpj_unidade}) ---")
        
        try:
            conn = conectar(cnpj_unidade)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Busca clientes que tenham CNPJ
            clientes = c.execute("SELECT nome, cnpj, whatsapp, email, contato, endereco FROM clientes WHERE cnpj IS NOT NULL AND cnpj != ''").fetchall()
            
            for cli in clientes:
                cnpj_cli = cli['cnpj']
                if not _normalizar_cnpj(cnpj_cli): continue
                
                # Upsert no banco central
                upsert_contato_global(
                    cnpj=cnpj_cli,
                    whatsapp=cli['whatsapp'],
                    email=cli['email'],
                    contato=cli['contato'],
                    endereco=cli['endereco']
                )
                total_contatos += 1
                
            conn.close()
            total_processado += 1
            print(f"   OK: {len(clientes)} contatos sincronizados.")
            
        except Exception as e:
            print(f"   ERRO ao processar unidade {nome_unidade}: {e}")

    print("\n--- RESUMO ---")
    print(f"Unidades processadas: {total_processado}")
    print(f"Contatos totais unificados: {total_contatos}")
    print("Sincronizacao concluida!")

if __name__ == "__main__":
    migrar_contatos()

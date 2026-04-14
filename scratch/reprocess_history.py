import sqlite3
import os
import sys

sys.path.insert(0, '/app')

from src.fiscal_parser import FiscalParser

CNPJ_EMPRESA = "54804458000122"
DB_PATH = f"/app/data/db_{CNPJ_EMPRESA}.db"

def reprocess():
    if not os.path.exists(DB_PATH):
        print("DB not found.")
        return

    parser = FiscalParser()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Busca todos os documentos que não têm valor ou emissão
    c.execute("SELECT id, fpath_local, tipo FROM documentos_fiscais WHERE valor IS NULL OR emissao IS NULL")
    rows = c.fetchall()
    print(f"Encontrados {len(rows)} documentos para reprocessar.")
    
    sucessos = 0
    for doc_id, fpath, tipo in rows:
        if not fpath or not os.path.exists(fpath):
            continue
            
        dados = parser.extrair_dados(fpath)
        if dados and (dados['valor'] is not None or dados['emissao'] is not None):
            print(f"ID {doc_id} | {tipo} | {os.path.basename(fpath)} -> Valor: {dados['valor']}, Emissão: {dados['emissao']}")
            c.execute("""
                UPDATE documentos_fiscais 
                SET valor = ?, emissao = ? 
                WHERE id = ?
            """, (dados['valor'], dados['emissao'], doc_id))
            sucessos += 1
            
        if sucessos % 10 == 0:
             conn.commit()
             
    conn.commit()
    conn.close()
    print(f"🏁 Reprocessamento concluído! {sucessos} documentos atualizados.")

if __name__ == "__main__":
    reprocess()

import sqlite3
import os

def check_data():
    cnpj = "11504286000169"
    db_path = f"db_{cnpj}.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    t = conn.execute("SELECT * FROM titulos WHERE id=55").fetchone()
    print(f"--- Título ---\nID: {t['id']}\nPagador: {t['pagador']}\nValor: {t['valor']}\nVencimento: {t['vencimento']}")
    
    cli = conn.execute("SELECT * FROM clientes WHERE trim(nome)=?", (t['pagador'].strip(),)).fetchone()
    if cli:
        d = dict(cli)
        print(f"\n--- Cliente ---\nNome: {d.get('nome')}\nCNPJ: {d.get('cnpj')}\nCEP: {d.get('cep')}\nEndereco: {d.get('endereco')}\nBairro: {d.get('bairro')}\nCidade: {d.get('cidade')}")
    else:
        print(f"\n❌ Cliente '{t['pagador']}' não encontrado!")
    conn.close()

if __name__ == "__main__":
    check_data()

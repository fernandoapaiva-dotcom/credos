import traceback
import glob

try:
    db_paths = glob.glob("db_*.db")
    if db_paths:
        cnpj = db_paths[0].replace("db_", "").replace(".db", "")
        print(f"Testing with CNPJ: {cnpj}")
        
        from src.manager import Manager
        mgr = Manager(cnpj)
        filtros = {
            "tipo": "Cobrados",
            "cliente": "EMBAIXADA DOS ESTADOS UNIDOS",
            "data_inicio": "2026-03-01",
            "data_fim": "2026-03-31"
        }
        res = mgr.gerar_relatorio_pdf_cobrancas(filtros)
        print("Success:", res)
        # Also let's run the query manually to check rows
        import sqlite3, pandas as pd
        conn = sqlite3.connect(f"db_{cnpj}.db")
        df = pd.read_sql_query("SELECT * FROM titulos", conn)
        print(f"Total rows in titulos DB: {len(df)}")
        df_aberto = pd.read_sql_query("SELECT * FROM titulos WHERE status = 'Aberto'", conn)
        print(f"Total rows Aberto in DB: {len(df_aberto)}")
    else:
        print("No db found")
except Exception as e:
    traceback.print_exc()

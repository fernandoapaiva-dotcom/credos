import os
import shutil
import glob
from datetime import datetime

def perform_backup():
    """
    Realiza o backup dos bancos de dados e logs para a unidade Z: (Google Drive).
    """
    # Configurações
    source_dir = os.getcwd()
    dest_base = r"Z:\Credos\Backup"
    
    # Cria pasta com timestamp para o backup atual
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dest_dir = os.path.join(dest_base, timestamp)
    
    try:
        if not os.path.exists(dest_base):
            print(f"Erro: Destino {dest_base} não encontrado.")
            return False, f"Destino {dest_base} não acessível."

        os.makedirs(dest_dir, exist_ok=True)
        print(f"Iniciando backup em: {dest_dir}")

        # 1. Backup de arquivos .db
        db_files = glob.glob(os.path.join(source_dir, "*.db"))
        for db in db_files:
            shutil.copy2(db, dest_dir)
            print(f"Copiado: {os.path.basename(db)}")

        # 2. Backup de logs
        logs_src = os.path.join(source_dir, "logs")
        if os.path.exists(logs_src):
            logs_dest = os.path.join(dest_dir, "logs")
            shutil.copytree(logs_src, logs_dest)
            print("Diretório de logs copiado.")

        print("Backup finalizado com sucesso.")
        return True, dest_dir

    except Exception as e:
        error_msg = f"Erro durante backup: {str(e)}"
        print(error_msg)
        return False, error_msg

if __name__ == "__main__":
    success, result = perform_backup()
    if success:
        print(f"Backup concluído: {result}")
    else:
        print(f"Falha no backup: {result}")

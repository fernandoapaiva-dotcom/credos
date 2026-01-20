import os

def list_files(startpath):
    print(f"\n🌲 ESTRUTURA DO PROJETO: {os.path.basename(startpath)}")
    print("="*40)
    
    # Adicionamos 'node_modules', 'dist' e 'evolution_db_data' para filtrar o excesso
    exclude = {
        '.git', 'venv', '__pycache__', '.vscode', 
        'node_modules', 'dist', 'evolution_db_data', 
        'evolution_instances', '.docker'
    }
    
    for root, dirs, files in os.walk(startpath):
        # Modifica dirs in-place para que o os.walk não entre nessas pastas
        dirs[:] = [d for d in dirs if d not in exclude]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print(f'{indent}📂 {os.path.basename(root)}/')
        
        subindent = ' ' * 4 * (level + 1)
        for f in files:
            # Opcional: Ignorar arquivos de log gigantes ou bancos de dados locais
            if f.endswith(('.log', '.db', '.lock')):
                continue
            print(f'{subindent}📄 {f}')

if __name__ == "__main__":
    # Garante que o caminho comece da raiz do projeto
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    list_files(root_path)
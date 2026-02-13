import os

def list_files(startpath):
    print(f"\n🌲 ESTRUTURA DO PROJETO: {os.path.basename(os.path.abspath(startpath))}")
    print("="*40)
    
    # Adicionamos as pastas geradas pelo Docker e pela Evolution API
    exclude = {
        '.git', 'venv', '__pycache__', '.vscode', 
        'node_modules', 'dist', 'evolution_db_data', 
        'evolution_instances', 'evolution_store', # Dados da API
        'docker', '.docker', 'logs',              # Infraestrutura
        'temp', 'tmp'                             # Arquivos temporários
    }
    
    for root, dirs, files in os.walk(startpath):
        # Filtra pastas indesejadas
        dirs[:] = [d for d in dirs if d not in exclude and not d.startswith('.')]
        
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        
        # Só imprime a pasta se ela não estiver vazia ou se for a raiz/src
        if level < 3: # Limita a profundidade para não virar uma lista infinita
            print(f'{indent}📂 {os.path.basename(root)}/')
            
            subindent = ' ' * 4 * (level + 1)
            for f in files:
                # Filtra arquivos irrelevantes
                if f.startswith('.') or f.endswith(('.log', '.db', '.lock', '.pyc')):
                    continue
                print(f'{subindent}📄 {f}')

if __name__ == "__main__":
    # Define a raiz como a pasta onde o script está ou a pasta acima
    # Ajustei para pegar a pasta atual se você rodar da raiz
    current_path = os.getcwd()
    list_files(current_path)
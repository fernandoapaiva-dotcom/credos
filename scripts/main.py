import os
import shutil
import json
from src.extractor import extrair_dados_boletos
from src.database import salvar_dados_no_banco

# Caminhos das pastas
DATA_DIR = "data"
PROCESSED_DIR = os.path.join(DATA_DIR, "processados")

def iniciar_processamento():
    # Garante que a pasta de processados existe
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)

    # Lista todos os PDFs na pasta data
    arquivos = [f for f in os.listdir(DATA_DIR) if f.endswith(".pdf")]

    if not arquivos:
        print("☕ Nenhum novo PDF encontrado para processar.")
        return

    for arquivo in arquivos:
        caminho_completo = os.path.join(DATA_DIR, arquivo)
        print(f"🔍 Lendo: {arquivo}...")

        try:
            # 1. Chama a IA para extrair os dados
            json_string = extrair_dados_boletos(caminho_completo)
            
            # Limpa possíveis formatações de markdown que o Gemini possa enviar
            json_clean = json_string.replace("```json", "").replace("```", "").strip()
            dados = json.loads(json_clean)

            # 2. Salva no Banco de Dados
            salvar_dados_no_banco(dados)

            # 3. Move o arquivo para a pasta de processados
            shutil.move(caminho_completo, os.path.join(PROCESSED_DIR, arquivo))
            print(f"✅ Arquivo {arquivo} processado e arquivado com sucesso!")

        except Exception as e:
            print(f"❌ Erro ao processar {arquivo}: {e}")

if __name__ == "__main__":
    iniciar_processamento()
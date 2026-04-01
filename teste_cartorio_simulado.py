import asyncio
import os
from src.cartorio_automation import CartorioAutomation
from src.database import conectar

async def simular_envio():
    import glob
    dry_run = True # Não envia nada, apenas simula até a revisão
    # ------------------------------
    
    # Busca dinamicamente qual empresa/banco de dados tem o título de Cartório que o usuário ativou no CRM
    db_files = glob.glob("db_*.db")
    
    row = None
    cnpj_sistema = None
    
    for db in db_files:
        cnpj = db.replace('db_', '').replace('.db', '')
        conn = conectar(cnpj)
        row = conn.cursor().execute("SELECT id FROM titulos WHERE status = 'Cartório' ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if row:
            cnpj_sistema = cnpj
            break
    
    if not row:
        print("Adicione pelo menos um título (mesmo que fictício) no sistema antes de rodar.")
        return

    titulo_id = row[0]
    bot = CartorioAutomation(cnpj_sistema)
    
    print(f"🤖 Iniciando SIMULAÇÃO CONTROLADA (Modo Dry-Run)...")
    print(f"   -> Empresa: {cnpj_sistema}")
    print(f"   -> Título ID (Gatilho): {titulo_id}")
    print(f"   -> Destino: {bot.base_url}")
    print("\nO robô irá preencher os campos mas NÃO clicará no envio final.\n")

    # dry_run=True garante que não será feito o envio final
    success, msg = await bot.enviar_titulo(titulo_id, dry_run=True)
    
    if success:
        print(f"\n✅ SIMULAÇÃO CONCLUÍDA COM SUCESSO!")
        print(f"Detalhe: {msg}")
    else:
        print(f"\n❌ FALHA NA SIMULAÇÃO: {msg}")

if __name__ == "__main__":
    asyncio.run(simular_envio())

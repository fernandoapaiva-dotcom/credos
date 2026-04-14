from src.manager import Manager
from src.database import conectar
import os

def test_send_dauto():
    cnpj_empresa = "54804458000122" # Servsolda
    phone_test = "556198334833"
    
    # 1. Busca um titulo do Dauto
    conn = conectar(cnpj_empresa)
    c = conn.cursor()
    c.execute("SELECT pagador, numero_nf, valor FROM titulos WHERE pagador LIKE '%DAUTO%' LIMIT 1")
    row = c.fetchone()
    conn.close()
    
    if not row:
        print("❌ Nenhum título encontrado para 'DAUTO'.")
        return

    pagador, nf, valor = row
    print(f"✅ Título encontrado: NF {nf} para {pagador} no valor de R$ {valor}")
    
    # 2. Prepara dados para o Manager
    # buscar_e_zipar_documentos(self, cliente_nome, lista_itens)
    # lista_itens deve ser lista de dicts com 'numero_nf'
    item = {'numero_nf': nf, 'pagador': pagador}
    
    mgr = Manager(cnpj_empresa)
    print("🔍 Buscando documentos no repositório...")
    zip_path, temp_dir = mgr.buscar_e_zipar_documentos(pagador, [item])
    
    if zip_path and os.path.exists(zip_path):
        print(f"📦 Arquivos encontrados e zipados em: {zip_path}")
        
        # 3. Envia WhatsApp
        msg = f"Olá {pagador}, segue o teste da Nota de Débito conforme solicitado.\n\n📄 Número: {nf}\n💰 Valor: R$ {valor}"
        print(f"📤 Enviando para {phone_test}...")
        
        # O Manager possui uma instância de EvolutionAPI em self.evo
        success_text = mgr.evo.enviar_mensagem_texto(phone_test, msg)
        print(f"✅ Texto: {success_text}")
        
        if success_text and zip_path:
            success_media = mgr.evo.enviar_midia(phone_test, zip_path)
            print(f"✅ Mídia: {success_media}")
        
        print(f"🏁 Teste concluído.")
    else:
        print("❌ Nenhum documento encontrado no repositório nem no IMAP.")

if __name__ == "__main__":
    test_send_dauto()

from src.manager import Manager
import os

def test_manager_dauto():
    # CNPJ da Matriz (Centro-Oeste)
    cnpj_co = '24934648000102'
    manager = Manager(cnpj_co)
    
    cliente_nome = "DAUTO COELHO DOS SANTOS"
    # Itens simulados (NF 382)
    itens = [{
        'id': 1000, # Dummy ID
        'numero_nf': '382',
        'pagador': cliente_nome,
        'vencimento': '10/04/2026',
        'valor': 471.91,
        'principal': 471.91,
        'total': 471.91
    }]
    
    print(f"--- TESTANDO MANAGER PARA {cliente_nome} (NF 382) ---")
    zip_path, arquivos = manager.buscar_e_zipar_documentos(cliente_nome, itens)
    
    print(f"\nResultado:")
    print(f"Zip: {zip_path}")
    print(f"Arquivos incluídos no pacote:")
    for a in arquivos:
        print(f"  - {a}")
        
    if any('1300' in a for a in arquivos):
        print("\n✅ SUCESSO! A nota complementar 1300 foi incluída via Regra de Ouro Matemática.")
    else:
        print("\n❌ FALHA! A nota complementar 1300 NÃO foi incluída.")

if __name__ == "__main__":
    test_manager_dauto()

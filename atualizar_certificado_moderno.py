import os
import base64
import sqlite3
from cryptography.hazmat.primitives.serialization import pkcs12, BestAvailableEncryption

def processar_e_salvar_certificado(file_path, password, cnpj):
    """
    Lê o PFX antigo, converte para um formato moderno e salva no banco de dados.
    """
    try:
        # 1. Lê o arquivo original do Z:
        if not os.path.exists(file_path):
            return False, f"Arquivo não encontrado em: {file_path}"
            
        with open(file_path, "rb") as f:
            pfx_data = f.read()
            
        # 2. Carrega o certificado (isso valida a senha tambem)
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
            pfx_data, 
            password.encode()
        )
        
        # 3. Serializa novamente (o cryptography usa algoritmos modernos por padrao)
        modern_pfx = pkcs12.serialize_key_and_certificates(
            b"cartorio_cert",
            private_key,
            certificate,
            additional_certificates,
            BestAvailableEncryption(password.encode())
        )
        
        # 4. Converte para Base64 para salvar no banco
        pfx_b64 = base64.b64encode(modern_pfx).decode('utf-8')
        
        # 5. Salva no banco de dados da empresa
        db_path = f"db_{cnpj}.db"
        if not os.path.exists(db_path):
            return False, f"Banco de dados da empresa {cnpj} não encontrado."
            
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Garante que a coluna existe (fallback se migracao falhou antes)
        cur.execute("UPDATE config SET cartorio_pfx_b64 = ?, cartorio_pfx_pass = ? WHERE id = 1", (pfx_b64, password))
        conn.commit()
        conn.close()
        
        return True, "✅ Certificado modernizado e salvo com sucesso no banco de dados!"

    except Exception as e:
        return False, f"❌ Erro ao converter certificado: {str(e)}"

if __name__ == "__main__":
    pfx_path = r"Z:\SERVWELD ASSISTENCIA TECNICA TRANSPORTE LOCAÇÃO.pfx"
    pfx_pass = "Lua1020*"
    empresa_cnpj = "11504286000169"
    
    print(f"📦 Modernizando certificado para a empresa {empresa_cnpj}...")
    success, msg = processar_e_salvar_certificado(pfx_path, pfx_pass, empresa_cnpj)
    print(msg)

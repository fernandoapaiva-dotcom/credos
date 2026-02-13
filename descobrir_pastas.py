import imaplib

# --- SEUS DADOS AQUI ---
EMAIL = "nfe@servsolda.com.br"  # Seu email de LEITURA
SENHA = "xnok nbad szbs ipvo"  # A senha de app
SERVIDOR = "imap.gmail.com"
# -----------------------

try:
    print(f"🔌 Conectando em {SERVIDOR}...")
    mail = imaplib.IMAP4_SSL(SERVIDOR)
    mail.login(EMAIL, SENHA)
    
    print("\n✅ Conectado! Listando pastas reais do servidor:\n")
    print("-" * 50)
    
    status, folders = mail.list()
    
    for f in folders:
        # Decodifica o nome da pasta
        linha = f.decode()
        print(linha)
        
    print("-" * 50)
    print("\n👉 Procure acima a linha que parece com 'Enviados' ou 'Sent'.")
    print("O nome real é o que está entre aspas no final da linha.")
    print('Exemplo: (\\HasNoChildren) "/" "[Gmail]/Sent Mail" -> O nome é [Gmail]/Sent Mail')

except Exception as e:
    print(f"❌ Erro: {e}")
import imaplib
import email
from email.header import decode_header

# ==============================================================================
# 🔧 ÁREA DE CONFIGURAÇÃO MANUAL (PREENCHA AQUI PARA O TESTE)
# ==============================================================================
EMAIL = "nfe@servsolda.com.br"        # O email onde estão os enviados
SENHA = "xnok nbad szbs ipvo"  # A senha de aplicativo
SERVIDOR = "imap.gmail.com"
NF_TESTE = "1096"                     # Uma nota que VOCÊ SABE que existe lá
# ==============================================================================

def decodificar(texto):
    if not texto: return "Vazio"
    try:
        decoded_list = decode_header(texto)
        parts = []
        for content, encoding in decoded_list:
            if isinstance(content, bytes):
                parts.append(content.decode(encoding or 'utf-8', errors='ignore'))
            else:
                parts.append(str(content))
        return "".join(parts)
    except: return str(texto)

print("\n🚀 INICIANDO RASTREIO DE ROTA IMAP (DIAGNÓSTICO EXTREMO)\n")

# --- PASSO 1: CONEXÃO ---
print(f"1️⃣  Tentando conectar em {SERVIDOR}...")
try:
    mail = imaplib.IMAP4_SSL(SERVIDOR)
    mail.login(EMAIL, SENHA)
    print("   ✅ Login SUCESSO! Credenciais válidas.")
except Exception as e:
    print(f"   ❌ FALHA NO LOGIN: {e}")
    exit()

# --- PASSO 2: MAPEAMENTO DE PASTAS ---
print("\n2️⃣  Mapeando pastas críticas...")
pastas_para_verificar = [
    '"[Gmail]/E-mails enviados"', 
    '"[Gmail]/Sent Mail"', 
    '"[Gmail]/Todos os e-mails"',
    '"INBOX"'
]

pasta_alvo_final = None

for pasta in pastas_para_verificar:
    status, data = mail.select(pasta)
    if status == "OK":
        qtd = data[0].decode()
        print(f"   📂 Pasta encontrada: {pasta} | Total de msgs: {qtd}")
        
        # Se achou uma pasta de enviados com mensagens, define como alvo
        if "enviados" in pasta.lower() or "sent" in pasta.lower():
            if int(qtd) > 0:
                pasta_alvo_final = pasta
    else:
        print(f"   ⚠️ Pasta não existe ou inacessível: {pasta}")

if not pasta_alvo_final:
    print("\n   ❌ ALERTA: Nenhuma pasta de enviados válida encontrada. Usando 'Todos os e-mails' como fallback.")
    pasta_alvo_final = '"[Gmail]/Todos os e-mails"'

print(f"\n   🎯 PASTA ELEITA PARA BUSCA: {pasta_alvo_final}")

# --- PASSO 3: TESTE DE VISÃO (LENDO O ÚLTIMO EMAIL) ---
print(f"\n3️⃣  Teste de Visão: Lendo o e-mail mais recente da pasta {pasta_alvo_final}...")
mail.select(pasta_alvo_final)
status, data = mail.search(None, "ALL")
if status == "OK" and data[0]:
    ultimo_id = data[0].split()[-1]
    _, msg_data = mail.fetch(ultimo_id, '(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])')
    for response_part in msg_data:
        if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])
            assunto = decodificar(msg.get("Subject"))
            data_envio = msg.get("Date")
            print(f"   ✅ VISÃO OK! Eu vejo: ID {ultimo_id.decode()} | Data: {data_envio} | Assunto: '{assunto}'")
else:
    print("   ❌ CEGUEIRA: A pasta parece vazia para o robô, mesmo que tenha mensagens para você.")

# --- PASSO 4: CAÇADA À NOTA ---
print(f"\n4️⃣  Caçando a NF {NF_TESTE} usando 3 métodos diferentes...")

# Método A: Busca Padrão (Subject)
print(f"   ➤ Método A (SUBJECT {NF_TESTE})...", end=" ")
stat, res = mail.search(None, f'(SUBJECT "{NF_TESTE}")')
if stat == "OK": print(f"Encontrou {len(res[0].split()) if res[0] else 0} e-mails.")
else: print("Erro.")

# Método B: Busca Google (X-GM-RAW) Simples
print(f"   ➤ Método B (X-GM-RAW '{NF_TESTE}')...", end=" ")
stat, res = mail.search(None, f'X-GM-RAW "{NF_TESTE}"')
if stat == "OK": 
    ids = res[0].split()
    print(f"Encontrou {len(ids)} e-mails.")
    if ids:
        print(f"      --> IDs encontrados: {ids}")
else: print("Erro.")

# Método C: Busca Google Forçada (from:me)
print(f"   ➤ Método C (X-GM-RAW 'from:me {NF_TESTE}')...", end=" ")
stat, res = mail.search(None, f'X-GM-RAW "from:me {NF_TESTE}"')
if stat == "OK": print(f"Encontrou {len(res[0].split()) if res[0] else 0} e-mails.")
else: print("Erro.")

# --- PASSO 5: VERIFICAÇÃO FINAL ---
print("\n🏁 RESULTADO DO DIAGNÓSTICO:")
if ids:
    print(f"   ✅ O EMAIL ESTÁ LÁ! O ID dele é: {ids[-1].decode()}")
    print("   Se este script achou, o problema estava na configuração salva no 'app.py' (talvez senha ou usuario errado salvo no banco).")
else:
    print("   ❌ O EMAIL NÃO FOI ENCONTRADO VIA IMAP.")
    print("   Possíveis causas:")
    print("   1. O e-mail não está nesta pasta (está na caixa de saída do ERP mas não sincronizou).")
    print("   2. O Assunto/Corpo não contém exatamente o número '1096' (ex: 'NF-1096' ou '001096').")

print("\nEncerrando conexão.")
mail.logout()
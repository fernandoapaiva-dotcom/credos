import imaplib
import email
from email.header import decode_header
import os
import re
import pdfplumber  # Necessário para ler o PDF

class MailScanner:
    def __init__(self, config):
        self.user = config.get('mail_user')
        self.password = config.get('mail_pass')
        self.server = config.get('imap_server')
        
        self.base_temp = "temp_data"
        self.pasta_destino = os.path.join(self.base_temp, "attachments")
        if not os.path.exists(self.pasta_destino): os.makedirs(self.pasta_destino)

    def conectar(self):
        try:
            if not self.user or not self.password or not self.server: return None
            mail = imaplib.IMAP4_SSL(self.server)
            mail.login(self.user, self.password)
            return mail
        except Exception as e:
            print(f"❌ Erro Conexão IMAP: {e}")
            return None

    def limpar_nome_arquivo(self, filename):
        if not filename: return "anexo_desconhecido"
        try:
            decoded_list = decode_header(filename)
            nome_limpo = ""
            for decoded_bytes, charset in decoded_list:
                if isinstance(decoded_bytes, bytes):
                    nome_limpo += decoded_bytes.decode(charset or 'utf-8', errors='ignore')
                else:
                    nome_limpo += str(decoded_bytes)
            return "".join([c for c in nome_limpo if c.isalnum() or c in (' ', '.', '_', '-')]).strip()
        except: return "anexo_erro_decode"

    def _selecionar_pasta_segura(self, mail, nome_pasta):
        try:
            status, _ = mail.select(f'"{nome_pasta}"')
            if status == "OK": return True
        except: pass
        try:
            status, _ = mail.select(nome_pasta)
            if status == "OK": return True
        except: pass
        return False

    def _extrair_texto_arquivo(self, filepath):
        """Lê o conteúdo de texto de PDFs ou XMLs"""
        texto_completo = ""
        try:
            if filepath.lower().endswith('.pdf'):
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages:
                        texto = page.extract_text()
                        if texto: texto_completo += texto
            elif filepath.lower().endswith('.xml'):
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    texto_completo = f.read()
            # Se for outro formato (zip/boleto sem extensão), não conseguimos ler fácil, 
            # então retornamos vazio e confiamos na validação manual se necessário
        except Exception as e:
            print(f"Erro lendo arquivo {filepath}: {e}")
        
        return texto_completo

    def validar_arquivo_pertence_cliente(self, filepath, cnpj_alvo, nome_alvo, vencimento_alvo=None, valor_alvo=None, nf_alvo=None):
        """
        Retorna TRUE se encontrar o CNPJ ou parte do NOME no arquivo.
        Também valida Vencimento, Valor e Número da NF se fornecidos.
        """
        texto = self._extrair_texto_arquivo(filepath)
        
        if not texto:
            print(f"   ⚠️ Arquivo ilegível (imagem ou protegido): {os.path.basename(filepath)}")
            return False 

        # Normaliza textos para comparação
        texto_limpo = re.sub(r'\D', '', texto) # Só números para CNPJ
        texto_upper = texto.upper() # Maiúsculo para Nome
        
        matches = 0
        checks = 0

        # 1. Validação por CNPJ
        if cnpj_alvo:
            checks += 1
            cnpj_limpo = re.sub(r'\D', '', str(cnpj_alvo))
            if cnpj_limpo and len(cnpj_limpo) > 5:
                if cnpj_limpo in texto_limpo:
                    matches += 1
                    print(f"   ✅ CNPJ OK")

        # 2. Validação por Nome
        if nome_alvo:
            checks += 1
            partes_nome = nome_alvo.upper().split()[:2] 
            nome_curto = " ".join(partes_nome)
            if nome_curto in texto_upper:
                matches += 1
                print(f"   ✅ Nome OK")

        # 3. Validação por Vencimento
        if vencimento_alvo:
            checks += 1
            # Tenta vários formatos: DD/MM/YYYY, DD.MM.YYYY, YYYY-MM-DD
            venc_fmt = str(vencimento_alvo).replace('-', '/').replace('.', '/')
            if venc_fmt in texto or vencimento_alvo in texto:
                matches += 1
                print(f"   ✅ Vencimento OK")

        # 4. Validação por Valor
        if valor_alvo:
            checks += 1
            valor_str = f"{valor_alvo:,.2f}".replace('.', '#').replace(',', '.').replace('#', ',') # Padrao PT-BR
            if valor_str in texto or f"{valor_alvo:.2f}" in texto:
                matches += 1
                print(f"   ✅ Valor OK")

        # 5. Validação por Número da NF
        if nf_alvo:
            checks += 1
            if str(nf_alvo) in texto:
                matches += 1
                print(f"   ✅ Número NF OK")

        # Se bateu o CNPJ já é suficiente, ou se bateu pelo menos 2 critérios
        if cnpj_alvo and (re.sub(r'\D', '', str(cnpj_alvo)) in texto_limpo):
            return True
        
        return matches >= 2

    def baixar_anexos_por_nf_validado(self, numero_nf, cnpj_cliente, nome_cliente, vencimento=None, valor=None):
        mail = self.conectar()
        if not mail: return []

        arquivos_baixados = []
        nf_str = str(numero_nf).strip()
        nf_sem_zero = str(int(nf_str)) if nf_str.isdigit() else nf_str
        
        pastas_candidatas = [
            '[Gmail]/E-mails enviados', '[Gmail]/Sent Mail', '[Gmail]/Todos os e-mails', '[Gmail]/All Mail',
            'Enviados', 'Itens Enviados', 'Sent', 'Sent Items', 'INBOX'
        ]

        try:
            _, folders = mail.list()
            pastas_reais = []
            for f in folders:
                decoded = f.decode()
                if '"/"' in decoded: parte_nome = decoded.split('"/"')[-1].strip().replace('"', '')
                else: parte_nome = decoded.split()[-1].strip().replace('"', '')
                pastas_reais.append(parte_nome)
                pastas_reais.append(decoded)
            todas_pastas = list(set(pastas_candidatas + pastas_reais))
            
            print(f"🔍 Procurando NF {nf_str}...") 

            for pasta in todas_pastas:
                if arquivos_baixados: break 
                if any(x in pasta.lower() for x in ['spam', 'trash', 'lixeira', 'drafts']): continue

                if not self._selecionar_pasta_segura(mail, pasta): continue

                ids = []
                typ, data = mail.search(None, f'(SUBJECT "{nf_str}")')
                if data[0]: ids.extend(data[0].split())
                
                if not ids and nf_str != nf_sem_zero:
                    typ, data = mail.search(None, f'(SUBJECT "{nf_sem_zero}")')
                    if data[0]: ids.extend(data[0].split())

                if not ids:
                     typ, data = mail.search(None, f'(BODY "{nf_str}")')
                     if data[0]: ids.extend(data[0].split())

                ids = sorted(list(set(ids)), reverse=True)[:3]
                
                for e_id in ids:
                    _, msg_data = mail.fetch(e_id, "(RFC822)")
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            
                            for part in msg.walk():
                                if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                                
                                fname = part.get_filename()
                                if fname:
                                    fname_lower = fname.lower()
                                    if any(ext in fname_lower for ext in ['.pdf', '.xml', '.boleto', '.zip']):
                                        fname_clean = self.limpar_nome_arquivo(fname)
                                        fpath = os.path.join(self.pasta_destino, f"{nf_str}_{fname_clean}")
                                        
                                        with open(fpath, "wb") as f:
                                            f.write(part.get_payload(decode=True))
                                        
                                        # --- AQUI ENTRA A VALIDAÇÃO ---
                                        if fpath.endswith('.zip'):
                                            arquivos_baixados.append(fpath)
                                        else:
                                            eh_valido = self.validar_arquivo_pertence_cliente(fpath, cnpj_cliente, nome_cliente, vencimento, valor, nf_str)
                                            if eh_valido:
                                                arquivos_baixados.append(fpath)
                                            else:
                                                # Tenta remover se não for válido
                                                try: os.remove(fpath)
                                                except: pass

            mail.close()
            mail.logout()
        except Exception as e:
            print(f"Erro Scanner: {e}")
        
        return list(set(arquivos_baixados))

# --- FUNÇÃO INDIVIDUAL NECESSÁRIA PARA O APP.PY ---
def conectar_email(u, p, s):
    try:
        m = imaplib.IMAP4_SSL(s)
        m.login(u, p)
        m.logout()
        return True, "OK"
    except Exception as e: return False, str(e)
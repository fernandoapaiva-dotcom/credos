import imaplib
import email
from email.header import decode_header
import os
import re
import pdfplumber  # Necessário para ler o PDF

class MailScanner:
    def __init__(self, config):
        self.user = config.get('base_mail_user')
        self.password = config.get('base_mail_pass')
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
        except Exception as e:
            print(f"Erro lendo arquivo {filepath}: {e}")
        
        return texto_completo

    def extrair_dados_fiscais(self, filepath):
        """Dada uma NF, tenta extrair a Data de Emissão e outros dados essenciais cruciais."""
        dados = {'emissao': None}
        try:
            texto = self._extrair_texto_arquivo(filepath)
            
            # 1. Se for XML, a precisão é cirúrgica
            if filepath.lower().endswith('.xml'):
                # Busca por <dhEmi>2026-03-31T10:00:00-03:00</dhEmi>
                match = re.search(r'<dhEmi>([^<]+)</dhEmi>', texto)
                if match:
                    iso_date = match.group(1).split('T')[0] # Pega só a data
                    # Converte para DD/MM/YYYY para seguir o padrão do banco
                    partes = iso_date.split('-')
                    if len(partes) == 3:
                        dados['emissao'] = f"{partes[2]}/{partes[1]}/{partes[0]}"
                        print(f"   XML: Extraída emissão {dados['emissao']}")
            
            # 2. Se for PDF, usamos Regex focada em Danfes brasileiros
            elif filepath.lower().endswith('.pdf'):
                # Busca padrões comuns, ex: DATA DE EMISSÃO 10/10/2025 ou apenas 10/10/2025 próximo a Emissão
                
                # Regex tenta achar DD/MM/YYYY
                dates = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
                # A primeira data no topo da Danfe geralmente é a emissão.
                if dates:
                    dados['emissao'] = dates[0]
                    print(f"   PDF: Extraída possível emissão {dados['emissao']}")
                    
        except Exception as e:
            print(f"Erro ao extrair dados fiscais de {filepath}: {e}")
            
        return dados

    import itertools

    def extrair_meta_documento(self, filepath, cnpj_alvo, nome_alvo, nf_alvo, vencimento_alvo):
        """Extrai todos os metadados matemáticos e de identidade do arquivo."""
        meta = {'pertence_cliente': False, 'tem_nf': False, 'valores': set(), 'tem_vencimento': False}
        texto = self._extrair_texto_arquivo(filepath)
        fname_limpo = os.path.basename(filepath).lower()
        
        texto_limpo = re.sub(r'\D', '', texto) if texto else ""
        texto_upper = texto.upper() if texto else ""
        
        cnpj_limpo = re.sub(r'\D', '', str(cnpj_alvo)) if cnpj_alvo else ""
        if cnpj_limpo and "54804458000122" in cnpj_limpo:
            cnpj_limpo = ""

        nome_curto = " ".join(nome_alvo.upper().split()[:2]) if nome_alvo else ""

        # 1. Identidade
        if cnpj_limpo and len(cnpj_limpo) > 5 and (cnpj_limpo in texto_limpo or cnpj_limpo in fname_limpo):
            meta['pertence_cliente'] = True
        elif nome_curto and len(nome_curto) > 3 and (nome_curto in texto_upper or nome_curto in fname_limpo.upper()):
            meta['pertence_cliente'] = True

        # Para PDFs imagem, confiamos no título para a NF
        if not texto and meta['pertence_cliente']:
            meta['tem_nf'] = True
            
        # 2. Número da NF
        if nf_alvo:
            nf_search = str(nf_alvo)
            if re.search(rf'\b0*{nf_search}\b', texto) or f" {nf_search} " in fname_limpo.replace('-', ' ').replace('_', ' '):
                meta['tem_nf'] = True

        # 3. Extração de Valores e Vencimento
        if texto:
            # Captura valores tipo 1.234,56 ou 1234,56 ou 12,34
            valores_str = re.findall(r'\b\d{1,3}(?:\.\d{3})*,\d{2}\b', texto)
            for v_str in valores_str:
                try:
                    num = float(v_str.replace('.', '').replace(',', '.'))
                    if num > 0: meta['valores'].add(num)
                except: pass
                
            if vencimento_alvo:
                venc_fmt = str(vencimento_alvo).replace('-', '/').replace('.', '/')
                if venc_fmt in texto or vencimento_alvo in texto:
                    meta['tem_vencimento'] = True

        return meta

    def baixar_anexos_por_nf_validado(self, numero_nf, cnpj_cliente, nome_cliente, vencimento=None, valor=None):
        mail = self.conectar()
        if not mail: return []

        arquivos_validados_finais = []
        nf_str = str(numero_nf).strip()
        nf_sem_zero = str(int(nf_str)) if nf_str.isdigit() else nf_str
        
        # Converte alvo para float se existir
        valor_alvo_float = None
        if valor:
            try: valor_alvo_float = float(valor)
            except: pass

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
            
            print(f"🔍 Procurando Lotes na NF {nf_str} (Val Esperado: {valor_alvo_float})...", flush=True) 

            for pasta in todas_pastas:
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

                ids = sorted(list(set(ids)), reverse=True)[:5]
                
                for e_id in ids:
                    _, msg_data = mail.fetch(e_id, "(RFC822)")
                    arquivos_do_email = []
                    
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
                                        fpath = os.path.join(self.pasta_destino, f"{nf_str}_{e_id.decode()}_{fname_clean}")
                                        
                                        with open(fpath, "wb") as f:
                                            f.write(part.get_payload(decode=True))
                                        
                                        if fpath.endswith('.zip'):
                                            arquivos_validados_finais.append(fpath) # Zips ignoram análise profunda
                                        else:
                                            arquivos_do_email.append(fpath)
                                            
                    if not arquivos_do_email: continue
                    
                    print(f"📦 Analisando lote de {len(arquivos_do_email)} arquivos no e-mail {e_id.decode()}...", flush=True)
                    
                    lote_meta = []
                    for fpath in arquivos_do_email:
                        meta = self.extrair_meta_documento(fpath, cnpj_cliente, nome_cliente, nf_str, vencimento)
                        meta['fpath'] = fpath
                        lote_meta.append(meta)
                        
                    # Filtragem Estrita 1: Cliente e NF
                    arquivos_cliente = [m for m in lote_meta if m['pertence_cliente'] and m['tem_nf']]
                    
                    arquivos_aprovados = set()
                    
                    # Estratégia A: Match Exato (Valor Unitário Bate ou Vencimento Bate Perfeitamente)
                    for m in arquivos_cliente:
                        match_valor = False
                        if valor_alvo_float:
                            for v in m['valores']:
                                if abs(v - valor_alvo_float) < 0.05: match_valor = True
                        
                        # Se achou o valor financeiro cravado ou a data de vencimento batendo, ou se nao foi mandado valor alvo
                        if match_valor or (m['tem_vencimento']) or (not valor_alvo_float and not vencimento):
                            arquivos_aprovados.add(m['fpath'])
                            print(f"   ✅ {os.path.basename(m['fpath'])} CUMPRIU TODOS OS REQUISITOS INDIRETOS/DIRETOS.", flush=True)

                    # Estratégia B: Soma Matemática (Produto + Serviço)
                    if not arquivos_aprovados and valor_alvo_float and len(arquivos_cliente) > 1:
                        # Extrai todos os valores e suas origens
                        mapa_valores = []
                        for m in arquivos_cliente:
                            for v in m['valores']:
                                mapa_valores.append({'valor': v, 'fpath': m['fpath']})
                        
                        # Tenta combinações de 2 a N documentos
                        from itertools import combinations
                        achou_combinacao = False
                        for r in range(2, min(5, len(mapa_valores) + 1)):
                            for combo in combinations(mapa_valores, r):
                                soma_combo = sum(c['valor'] for c in combo)
                                if abs(soma_combo - valor_alvo_float) < 0.05:
                                    print(f"   🧩 COMBO ENCONTRADO! Soma exata = {soma_combo}", flush=True)
                                    for c in combo: arquivos_aprovados.add(c['fpath'])
                                    achou_combinacao = True
                                    break
                            if achou_combinacao: break
                            
                    # Limpeza
                    for fpath in arquivos_do_email:
                        if fpath in arquivos_aprovados:
                            arquivos_validados_finais.append(fpath)
                        else:
                            try: os.remove(fpath)
                            except: pass

            try: mail.close()
            except: pass
            mail.logout()
        except Exception as e:
            if "CLOSE" not in str(e): print(f"Erro Scanner: {e}", flush=True)
        
        return list(set(arquivos_validados_finais))

    def buscar_e_extrair_dados_nf(self, numero_nf, cnpj_cliente, nome_cliente):
        """Busca o email, baixa XML/PDF e tenta extrair a 'Data de Emissão'."""
        arquivos = self.baixar_anexos_por_nf_validado(numero_nf, cnpj_cliente, nome_cliente)
        
        # Prioriza a leitura de XML se houver os dois (PDF e XML)
        xmls = [f for f in arquivos if f.lower().endswith('.xml')]
        pdfs = [f for f in arquivos if f.lower().endswith('.pdf')]
        
        ordem_leitura = xmls + pdfs
        
        for fpath in ordem_leitura:
            dados = self.extrair_dados_fiscais(fpath)
            if dados.get('emissao'):
                # Limpa arquivos temporários pois só precisávamos da data
                for tmp_file in arquivos:
                    try: os.remove(tmp_file)
                    except: pass
                return dados
                
        # Limpa tudo se não achou nada util
        for tmp_file in arquivos:
            try: os.remove(tmp_file)
            except: pass
            
        return None

# --- FUNÇÃO INDIVIDUAL NECESSÁRIA PARA O APP.PY ---
def conectar_email(u, p, s):
    try:
        m = imaplib.IMAP4_SSL(s)
        m.login(u, p)
        m.logout()
        return True, "OK"
    except Exception as e: return False, str(e)
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
        
        # LIMPEZA ABRUPTA DO CACHE FÍSICO
        import shutil
        if os.path.exists(self.pasta_destino):
            try: shutil.rmtree(self.pasta_destino)
            except: pass
        os.makedirs(self.pasta_destino, exist_ok=True)

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

    def extrair_meta_documento(self, filepath, cnpj_alvo, nome_alvo, nf_alvo, vencimento_alvo):
        """Extrai todos os metadados matemáticos e de identidade do arquivo."""
        meta = {'pertence_cliente': False, 'tem_nf': False, 'valores': set(), 'tem_vencimento': False, 'eh_imagem': False}
        texto = self._extrair_texto_arquivo(filepath)
        fname_limpo = os.path.basename(filepath).lower()
        
        texto_limpo = re.sub(r'\D', '', texto) if texto else ""
        texto_upper = texto.upper() if texto else ""
        
        if not texto:
            meta['eh_imagem'] = True
            
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
        """Nova Lógica de Pooling: Busch Produto + Serviço e Deduplica arquivos."""
        mail = self.conectar()
        if not mail: return []

        nf_str = str(numero_nf).strip()
        nf_sem_zero = str(int(nf_str)) if nf_str.isdigit() else nf_str
        
        # Converte alvos para lista de floats se existirem
        alvos_validos = []
        if valor:
            if isinstance(valor, (list, tuple)):
                for v in valor:
                    try: alvos_validos.append(float(v))
                    except: pass
            else:
                try: alvos_validos.append(float(valor))
                except: pass

        pastas_candidatas = [
            'INBOX', '[Gmail]/Sent Mail', 'Sent', '[Gmail]/Sent', 'Enviados', 'Itens Enviados', '[Gmail]/Todos os e-mails'
        ]

        pool_metadados = []
        arquivos_temp_lot = []
        seen_filenames = set() # Controle de deduplicação rigorosa

        try:
            _, folders = mail.list()
            pastas_reais = [f.decode().split('"/"')[-1].strip().replace('"', '') for f in folders]
            todas_pastas = list(set(pastas_candidatas + pastas_reais))
            
            print(f"🔍 [Pooling] Iniciando busca para NF {nf_str} (Alvos: {alvos_validos})...", flush=True)

            # --- ETAPA 1: Busca por Número de NF (Corpo e Assunto) ---
            ids_candidatos = []
            for pasta in todas_pastas:
                if any(x in pasta.lower() for x in ['spam', 'trash', 'lixeira', 'drafts']): continue
                if not self._selecionar_pasta_segura(mail, pasta): continue
                
                # Procura NF no assunto ou corpo (geralmente pega o nome do anexo)
                typ, data = mail.search(None, f'(OR SUBJECT "{nf_str}" BODY "{nf_str}")')
                if data[0]: ids_candidatos.extend([(pasta, mid) for mid in data[0].split()])
                
                if not data[0] and nf_str != nf_sem_zero:
                    typ, data = mail.search(None, f'(OR SUBJECT "{nf_sem_zero}" BODY "{nf_sem_zero}")')
                    if data[0]: ids_candidatos.extend([(pasta, mid) for mid in data[0].split()])

            # --- ETAPA 2: Busca por CNPJ e Nome do Cliente (Ampla) ---
            cnpj_limpo = re.sub(r'\D', '', str(cnpj_cliente)) if cnpj_cliente else ""
            nome_curto = " ".join(str(nome_cliente).upper().split()[:2]) if nome_cliente else ""
            
            for pasta in ['INBOX', '[Gmail]/Sent Mail', 'Sent', 'Enviados']:
                if not self._selecionar_pasta_segura(mail, pasta): continue
                
                if cnpj_limpo and len(cnpj_limpo) > 10:
                    typ, data = mail.search(None, f'(OR SUBJECT "{cnpj_limpo}" BODY "{cnpj_limpo}")')
                    if data[0]:
                        for mid in sorted(data[0].split(), reverse=True)[:10]: ids_candidatos.append((pasta, mid))
                
                if nome_curto and len(nome_curto) > 4:
                    # Se não foi, tenta pelo nome curto do cliente no corpo
                    typ, data = mail.search(None, f'(BODY "{nome_curto}")')
                    if data[0]:
                        for mid in sorted(data[0].split(), reverse=True)[:10]: ids_candidatos.append((pasta, mid))

            # Consolida e-mails únicos para processar
            ids_unicos = []
            seen_ids = set()
            for p, mid in ids_candidatos:
                if mid not in seen_ids:
                    ids_unicos.append((p, mid))
                    seen_ids.add(mid)
            
            # Processamento de Anexos do Pool
            for pasta, e_id in ids_unicos[:15]:
                if not self._selecionar_pasta_segura(mail, pasta): continue
                _, msg_data = mail.fetch(e_id, "(RFC822)")
                if not msg_data or not msg_data[0]: continue
                
                msg = email.message_from_bytes(msg_data[0][1])
                
                # PREVENÇÃO DE LOOP DE ANEXOS: Ignora e-mails automáticos do próprio robô
                subj_decode = decode_header(msg.get("Subject", ""))
                txt_subject = ""
                for bytes_str, charset in subj_decode:
                    if isinstance(bytes_str, bytes):
                        txt_subject += bytes_str.decode(charset or 'utf-8', errors='ignore')
                    else:
                        txt_subject += str(bytes_str)
                if "Documentos Fiscais - Credos" in txt_subject: continue
                
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                    
                    fname = part.get_filename()
                    if fname:
                        fname_clean = self.limpar_nome_arquivo(fname)
                        # DEDUPLICAÇÃO REAL POR NOME: Impede o envio de 6 arquivos idênticos
                        if fname_clean.lower() in seen_filenames: continue
                        seen_filenames.add(fname_clean.lower())

                        fpath = os.path.join(self.pasta_destino, f"{nf_str}_{e_id.decode()}_{fname_clean}")
                        with open(fpath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        
                        meta = self.extrair_meta_documento(fpath, cnpj_cliente, nome_cliente, nf_str, vencimento)
                        meta['fpath'] = fpath
                        meta['nome_original'] = fname_clean
                        
                        # Sistema de Scoring para filtrar lixo (Email de outra NF que apenas cita a 1237)
                        score = 0
                        if meta['pertence_cliente']: score += 10
                        if meta['tem_nf']: score += 15
                        if any(abs(v - alvo) < 0.05 for v in meta['valores'] for alvo in alvos_validos): score += 10
                        if meta['tem_vencimento']: score += 5
                        
                        meta['score'] = score
                        if score >= 10: 
                            pool_metadados.append(meta)
                            arquivos_temp_lot.append(fpath)
                        else:
                            try: os.remove(fpath)
                            except: pass

            # --- ETAPA 3: Decisão de Entrega (Pooling Inteligente) ---
            arquivos_aprovados = set()
            
            # 1. Match Ouro (Direto)
            for m in [x for x in pool_metadados if x['score'] >= 30]:
                arquivos_aprovados.add(m['fpath'])
                print(f"   🏆 Lote Ouro Identificado: {os.path.basename(m['fpath'])}", flush=True)

            # 2. Combinação (Produto + Serviço)
            if alvos_validos and not any(m['score'] >= 30 for m in pool_metadados):
                from itertools import combinations
                # Só combina arquivos que pertençam ao cliente
                candidatos = [m for m in pool_metadados if m['pertence_cliente'] and m['fpath'] not in arquivos_aprovados]
                achou_soma = False
                for alvo in alvos_validos:
                    for r in range(1, min(4, len(candidatos) + 1)):
                        for combo in combinations(candidatos, r):
                            soma = sum(max(c['valores']) if c['valores'] else 0 for c in combo)
                            if abs(soma - alvo) < 0.05:
                                print(f"   🧩 Par Perfeito (Produto+Serviço) Encontrado! Soma: {soma}", flush=True)
                                for c in combo: arquivos_aprovados.add(c['fpath'])
                                achou_soma = True; break
                        if achou_soma: break
                    if achou_soma: break

            # 3. Lei da Carona (Boleto/XML do mesmo e-mail de uma NF aprovada)
            ids_aprovados = set()
            for f in arquivos_aprovados:
                base = os.path.basename(f)
                if base.count('_') >= 2: ids_aprovados.add(base.split('_')[1])
            
            for m in pool_metadados:
                base_m = os.path.basename(m['fpath'])
                if base_m.count('_') >= 2:
                    id_m = base_m.split('_')[1]
                    if id_m in ids_aprovados:
                         if m['fpath'].lower().endswith(('.pdf', '.xml', '.boleto')):
                             arquivos_aprovados.add(m['fpath'])

            # Limpeza
            for fpath in arquivos_temp_lot:
                if fpath not in arquivos_aprovados:
                    try: os.remove(fpath)
                    except: pass

            try: mail.close()
            except: pass
            mail.logout()
            
            return list(set(arquivos_aprovados))

        except Exception as e:
            if "CLOSE" not in str(e): print(f"Erro Scanner Pooling: {e}", flush=True)
        
        return []

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
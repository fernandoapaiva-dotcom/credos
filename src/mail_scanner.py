import imaplib
import email
from email.header import decode_header
import os
import re
import pdfplumber  # Necessrio para ler o PDF

DEBUG_SCANNER = False

class MailScanner:
    def __init__(self, config):
        self.user = config.get('base_mail_user')
        self.password = config.get('base_mail_pass')
        self.server = config.get('imap_server')
        
        self.base_temp = "temp_data"
        self.pasta_destino = os.path.join(self.base_temp, "attachments")
        
        # LIMPEZA ABRUPTA DO CACHE FSICO
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
            print(f" Erro Conexo IMAP: {e}")
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
        """L o contedo de texto de PDFs ou XMLs"""
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
        """Dada uma NF, tenta extrair a Data de Emisso e outros dados essenciais cruciais."""
        dados = {'emissao': None}
        try:
            texto = self._extrair_texto_arquivo(filepath)
            
            # 1. Se for XML, a preciso  cirrgica
            if filepath.lower().endswith('.xml'):
                # Busca por <dhEmi>2026-03-31T10:00:00-03:00</dhEmi>
                match = re.search(r'<dhEmi>([^<]+)</dhEmi>', texto)
                if match:
                    iso_date = match.group(1).split('T')[0] # Pega s a data
                    # Converte para DD/MM/YYYY para seguir o padro do banco
                    partes = iso_date.split('-')
                    if len(partes) == 3:
                        dados['emissao'] = f"{partes[2]}/{partes[1]}/{partes[0]}"
                        print(f"   XML: Extrada emisso {dados['emissao']}")
            
            # 2. Se for PDF, usamos Regex focada em Danfes brasileiros
            elif filepath.lower().endswith('.pdf'):
                # Busca padres comuns, ex: DATA DE EMISSO 10/10/2025 ou apenas 10/10/2025 prximo a Emisso
                
                # Regex tenta achar DD/MM/YYYY
                dates = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
                # A primeira data no topo da Danfe geralmente  a emisso.
                if dates:
                    dados['emissao'] = dates[0]
                    print(f"   PDF: Extrada possvel emisso {dados['emissao']}")
                    
        except Exception as e:
            print(f"Erro ao extrair dados fiscais de {filepath}: {e}")
            
        return dados

    def extrair_meta_documento(self, filepath, cnpj_alvo, nome_alvo, nf_alvo, vencimento_alvo):
        """Extrai todos os metadados matemticos e de identidade do arquivo."""
        meta = {'pertence_cliente': False, 'tem_nf': False, 'valores': set(), 'tem_vencimento': False, 'eh_imagem': False, 'conflito_identidade': False}
        texto = self._extrair_texto_arquivo(filepath)
        fname_limpo = os.path.basename(filepath).lower()
        
        texto_limpo = re.sub(r'\D', '', texto) if texto else ""
        texto_upper = texto.upper() if texto else ""
        
        if not texto:
            meta['eh_imagem'] = True
            
        cnpj_alvo_limpo = re.sub(r'\D', '', str(cnpj_alvo)) if cnpj_alvo else ""
        
        # 0. Identificao de CNPJs (Extrator de Preciso)
        # Busca CNPJs formatados (XX.XXX.XXX/XXXX-XX) ou sequncias de 14 dgitos
        cnpjs_encontrados = re.findall(r'\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b', texto or "")
        # cnpjs_limpos conter apenas CNPJs que parecem reais (formato XX.XXX.XXX/XXXX-XX)
        cnpjs_limpos = {re.sub(r'\D', '', c) for c in cnpjs_encontrados}
        
        # Só usamos a busca de 14 dígitos brutos em PDFs (onde o OCR pode falhar na pontuação)
        # e verificamos se não são apenas sequências de zeros ou números muito simples.
        if filepath.lower().endswith('.pdf'):
            puj_14 = re.findall(r'\b\d{14}\b', texto_limpo)
            for c in puj_14:
                if c != '0' * 14 and not c.startswith('000000'):
                    cnpjs_limpos.add(c)

        if DEBUG_SCANNER:
            print(f"      [DEBUG] CNPJs Encontrados: {cnpjs_limpos}")
            print(f"      [DEBUG] Texto (primeiros 100): {texto[:100] if texto else 'VAZIO'}")

        # CNPJ do Emitter (Credos/Servsolda) - Sempre ignoramos como alvo
        cnpj_proprio = "54804458000122"
        
        # Se existe um CNPJ que nao o nosso e NAO o do cliente, temos um CONFLITO
        # Mas s marcamos conflito SE no encontrarmos o CNPJ do cliente no mesmo arquivo
        encontrou_alvo = (cnpj_alvo_limpo and cnpj_alvo_limpo in cnpjs_limpos)
        
        for c in cnpjs_limpos:
            if c != cnpj_proprio:
                if cnpj_alvo_limpo and c != cnpj_alvo_limpo and not encontrou_alvo:
                    meta['conflito_identidade'] = True
                elif not cnpj_alvo_limpo:
                    # Se no temos o CNPJ do cliente no banco, qualquer CNPJ estranho e um risco
                    pass

        nome_curto = " ".join(nome_alvo.upper().split()[:2]) if nome_alvo else ""
        primeiro_nome = nome_alvo.upper().split()[0] if nome_alvo else ""

        # 1. Identidade Positiva Forte (CNPJ)
        if encontrou_alvo:
            meta['pertence_cliente'] = True
        
        # Identidade Flexivel (Nome) - Apenas se o CNPJ não foi conclusivo
        if not meta['pertence_cliente']:
            def normalizar(t): return re.sub(r'[^A-Z0-9]', '', str(t).upper())
            
            texto_norm = normalizar(texto_upper)
            fname_norm = normalizar(fname_limpo)
            nome_norm = normalizar(nome_alvo)
            nome_curto_norm = normalizar(nome_curto)
            p_nome_norm = normalizar(primeiro_nome)

            if (nome_curto_norm and len(nome_curto_norm) > 4 and (nome_curto_norm in texto_norm or nome_curto_norm in fname_norm)):
                meta['pertence_cliente'] = True
            elif (p_nome_norm and len(p_nome_norm) >= 4 and (p_nome_norm in texto_norm or p_nome_norm in fname_norm)):
                meta['pertence_cliente'] = True
            elif (nome_norm and nome_norm in texto_norm):
                meta['pertence_cliente'] = True

        # 2. Nmero da NF (Sniper de Preciso)
        if nf_alvo:
            nf_search = str(nf_alvo).lstrip('0')
            
            # Tenta achar Chaves de Acesso (44 dgitos) no texto ou nome
            chaves = re.findall(r'\d{44}', texto_limpo + " " + fname_limpo)
            nfs_reais_na_chave = []
            for c in chaves:
                n_extraido = c[25:34].lstrip('0')
                if n_extraido: nfs_reais_na_chave.append(n_extraido)
            
            if nfs_reais_na_chave:
                if any(n == nf_search for n in nfs_reais_na_chave):
                    meta['tem_nf'] = True
                else:
                    meta['outra_nf_detectada'] = nfs_reais_na_chave[0]
            
            # Busca de nmero solto (Apenas se no tem chave conflitante)
            if not meta['tem_nf'] and not meta.get('outra_nf_detectada'):
                # 1. Tenta com limites de não-dígitos (precisão)
                if re.search(rf'(?<!\d){nf_search}(?!\d)', (texto or "") + " " + fname_limpo):
                    meta['tem_nf'] = True
                # 2. Fallback: Busca o número solto em qualquer lugar (permissivo)
                elif nf_search in (texto or "") or nf_search in fname_limpo:
                    meta['tem_nf'] = True

        # 2.5 Reforo para Boletos
        boleto_words = ['boleto', 'duplicata', 'titulo', 'fatura', 'pagamento']
        if any(w in fname_limpo for w in boleto_words):
            meta['provavel_boleto'] = True

        # 3. Extrao de Valores e Vencimento
        if texto:
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

        if DEBUG_SCANNER:
            print(f"      [DEBUG] META FINAL: pertence_cliente={meta['pertence_cliente']}, tem_nf={meta['tem_nf']}, conflito={meta['conflito_identidade']}")

        return meta

    def baixar_anexos_por_nf_validado(self, numero_nf, cnpj_cliente, nome_cliente, vencimento=None, valor=None):
        """Nova Lgica de Pooling: Busch Produto + Servio e Deduplica arquivos."""
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
        seen_nomes_originais = set()  # Controle de deduplicao pelo nome real do arquivo (evita duplicatas entre emails)

        
        # ISOLAMENTO: Cada busca usa sua prpria subpasta nica para evitar
        # que a limpeza de uma NF apague os arquivos de outra NF.
        import uuid
        pasta_destino_isolada = os.path.join(self.pasta_destino, f"nf_{nf_str}_{uuid.uuid4().hex[:8]}")
        os.makedirs(pasta_destino_isolada, exist_ok=True)

        try:
            _, folders = mail.list()
            pastas_reais = [f.decode().split('"/"')[-1].strip().replace('"', '') for f in folders]
            todas_pastas = list(set(pastas_candidatas + pastas_reais))
            
            print(f"--- [Pooling] Iniciando busca para NF {nf_str} (Alvos: {alvos_validos})...", flush=True)

            # --- ETAPA 1: Busca por Nmero de NF (Corpo e Assunto) ---
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
                    # Se no foi, tenta pelo nome curto do cliente no corpo
                    typ, data = mail.search(None, f'(BODY "{nome_curto}")')
                    if data[0]:
                        for mid in sorted(data[0].split(), reverse=True)[:10]: ids_candidatos.append((pasta, mid))

            # Consolida e-mails nicos para processar
            ids_unicos = []
            seen_ids = set()
            for p, mid in ids_candidatos:
                if mid not in seen_ids:
                    ids_unicos.append((p, mid))
                    seen_ids.add(mid)
            
            # Processamento de Anexos do Pool (aumentado para 25 e-mails)
            for pasta, e_id in ids_unicos[:25]:
                if not self._selecionar_pasta_segura(mail, pasta): continue
                _, msg_data = mail.fetch(e_id, "(RFC822)")
                if not msg_data or not msg_data[0]: continue
                
                msg = email.message_from_bytes(msg_data[0][1])
                
                # PREVENO DE LOOP DE ANEXOS: Ignora e-mails automticos do prprio rob
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
                        
                        # DEDUPLICAO REAL: Pelo nome do arquivo limpo. Se j baixamos o "boleto.pdf", no baixamos de novo
                        if fname_clean.lower() in seen_nomes_originais: continue
                        seen_nomes_originais.add(fname_clean.lower())

                        fpath = os.path.join(pasta_destino_isolada, f"{nf_str}_{e_id.decode()}_{fname_clean}")
                        with open(fpath, "wb") as f:

                            f.write(part.get_payload(decode=True))
                        
                        meta = self.extrair_meta_documento(fpath, cnpj_cliente, nome_cliente, nf_str, vencimento)
                        meta['fpath'] = fpath
                        meta['nome_original'] = fname_clean
                        
                        meta['email_id'] = str(e_id.decode())
                        
                        # NOVIDADE: No deletamos mais nada antecipadamente. 
                        # Mantemos todos os candidatos para a filtragem "Sniper" final.
                        pool_metadados.append(meta)
                        arquivos_temp_lot.append(fpath)

            # --- ETAPA 3: FILTRO SNIPER (REGRA INTELIGENTE) ---
            # Um arquivo  aprovado se:
            # 1. O nmero da NF estiver no nome (ou na chave de acesso no nome)
            # 2. OU se a pontuao de contedo for alta (Data + Valor batendo exatamente)
            # 3. NOVIDADE: Se estiver no MESMO E-MAIL de um arquivo que j foi aprovado por NF!
            arquivos_aprovados = set()
            emails_com_nf_confirmada = set()
            nf_num = nf_str.lstrip('0')

            # Passada 1: Identifica e-mails que DEFINITIVAMENTE contm a NF alvo
            for m in pool_metadados:
                bname = os.path.basename(m['fpath'])
                eh_nf_confirmada = False

                nome_orig = m.get('nome_original', bname)
                # Regra 1: Identificao por NF + Cliente (Foguete)
                if (nf_num in nome_orig or m.get('tem_nf')) and m.get('pertence_cliente'):
                    eh_nf_confirmada = True
                    identidade_ok = True # Identidade confirmada pelo match duplo
                elif nf_num in nome_orig or m.get('tem_nf'):
                     # Candidato por nmero, mas precisa validar identidade
                    eh_nf_confirmada = True
                    identidade_ok = False
                else:
                    # Tenta via Chave SEFAZ
                    chaves_no_nome = re.findall(r'\d{42,44}', nome_orig)
                    if chaves_no_nome:
                        for chave in chaves_no_nome:
                            try:
                                if str(int(chave[25:34])) == nf_num:
                                    eh_nf_confirmada = True
                                    identidade_ok = m.get('pertence_cliente', False)
                            except: pass
                    if chaves_no_nome:
                        for chave in chaves_no_nome:
                            # Tenta extrair a NF da posição padrão (25:34) ou aproximada
                            try:
                                nf_na_chave = str(int(chave[25:34]))
                                if nf_na_chave == nf_num:
                                    eh_nf_confirmada = True
                            except: pass


                # CROSS-CONTAMINATION FILTER (REFORADO)
                if eh_nf_confirmada:
                    identidade_ok = False
                    # Regra 1: CNPJ ou Nome batendo e aprovao instantnea
                    if m.get('pertence_cliente', False): 
                        identidade_ok = True
                    
                    # Regra 2: Se o nome confirmou (pertence_cliente), ignoramos conflitos de CNPJ menores (ex: banco/transporte)
                    # Apenas marcamos falha se pertense_cliente for FALSO e houver conflito
                    if not identidade_ok:
                        if not m.get('conflito_identidade', False):
                            if m.get('tem_vencimento', False): identidade_ok = True
                            if alvos_validos and m.get('valores') and any((abs(v - a) < 0.1) for v in m.get('valores') for a in alvos_validos):
                                identidade_ok = True
                    
                    if not identidade_ok:
                        eh_nf_confirmada = False
                        msg_falha = "Conflito de CNPJ" if m.get('conflito_identidade') else "Nome/Dados no conferem"
                        print(f"    REJEITADO: {msg_falha} | {bname[:50]}")

                if eh_nf_confirmada:
                    arquivos_aprovados.add(m['fpath'])
                    emails_com_nf_confirmada.add(m['email_id'])
                    print(f"    NF CONFIRMADA E VALIDADA: {bname[:60]} (Email: {m['email_id']})")

            # Passada 2: Aprova outros arquivos (Boletos/XMLs) que esto nos mesmos e-mails aprovados
            for m in pool_metadados:
                if m['fpath'] in arquivos_aprovados: continue
                
                if m['email_id'] in emails_com_nf_confirmada:
                    # Se est no mesmo email de uma NF aprovada, e  um arquivo til, a gente deixa passar!
                    bname = os.path.basename(m['fpath'])
                    arquivos_aprovados.add(m['fpath'])
                    print(f"    APROVADO POR ASSOCIAO (Mesmo e-mail da NF): {bname[:60]}")

            print(f"   Total aprovado: {len(arquivos_aprovados)} arquivo(s) para NF {nf_str}")
            
            # Limpeza: remove apenas arquivos NO aprovados desta pasta isolada
            if os.path.exists(pasta_destino_isolada):
                for f in os.listdir(pasta_destino_isolada):
                    fp = os.path.join(pasta_destino_isolada, f)
                    if fp not in arquivos_aprovados and os.path.isfile(fp):
                        try: os.remove(fp)
                        except: pass
                # Remove a subpasta se ficou vazia
                try:
                    if not os.listdir(pasta_destino_isolada):
                        os.rmdir(pasta_destino_isolada)
                except: pass

            try: mail.close()
            except: pass
            mail.logout()

            return list(arquivos_aprovados)

        except Exception as e:
            if "CLOSE" not in str(e): print(f"Erro Scanner Pooling: {e}", flush=True)
        
        return []

    def buscar_e_extrair_dados_nf(self, numero_nf, cnpj_cliente, nome_cliente):
        """Busca o email, baixa XML/PDF e tenta extrair a 'Data de Emisso'."""
        arquivos = self.baixar_anexos_por_nf_validado(numero_nf, cnpj_cliente, nome_cliente)
        
        # Prioriza a leitura de XML se houver os dois (PDF e XML)
        xmls = [f for f in arquivos if f.lower().endswith('.xml')]
        pdfs = [f for f in arquivos if f.lower().endswith('.pdf')]
        
        ordem_leitura = xmls + pdfs
        
        for fpath in ordem_leitura:
            dados = self.extrair_dados_fiscais(fpath)
            if dados.get('emissao'):
                # Limpa arquivos temporrios pois s precisvamos da data
                for tmp_file in arquivos:
                    try: os.remove(tmp_file)
                    except: pass
                return dados
                
        # Limpa tudo se no achou nada util
        for tmp_file in arquivos:
            try: os.remove(tmp_file)
            except: pass
            
        return None

# --- FUNO INDIVIDUAL NECESSRIA PARA O APP.PY ---
def conectar_email(u, p, s):
    try:
        m = imaplib.IMAP4_SSL(s)
        m.login(u, p)
        m.logout()
        return True, "OK"
    except Exception as e: return False, str(e)
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
        self.enviados_detectada = None
        
        # Garante que a pasta existe, MAS NÃO DELETA O CONTEÚDO
        # Isso previne que requisições concorrentes apaguem os arquivos umas das outras
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

    def descobrir_pasta_enviados(self, mail):
        """Tenta descobrir qual a pasta de itens ENVIADOS no IMAP."""
        if self.enviados_detectada:
            return self._selecionar_pasta_segura(mail, self.enviados_detectada)

        try:
            status, list_data = mail.list()
            if status != "OK": return False
            
            # Mapas comuns de nomes de pastas de enviados
            noms_pasto = ['SENT', 'ENVIADOS', 'ENVIADAS', 'ENVIEI', 'OUTBOX', 'ITEMS ENVIADOS', 'ENVIADOS - YAHOO']
            
            # 1. Procura por atributos (flags) do IMAP (RFC 6154)
            for line in list_data:
                line_decode = line.decode('utf-8', errors='ignore')
                if '\\Sent' in line_decode:
                    parts = line_decode.split(' "/" ')
                    if len(parts) > 1:
                        target = parts[-1].strip().strip('"')
                        if self._selecionar_pasta_segura(mail, target):
                            self.enviados_detectada = target
                            return True

            # 2. Heurstica por nomes comuns
            for p in noms_pasto:
                for line in list_data:
                    line_decode = line.decode('utf-8', errors='ignore').upper()
                    if f'"{p}"' in line_decode or f'/{p}' in line_decode or line_decode.endswith(p):
                        # Pega o nome real da pasta entre aspas no final da linha
                        parts = line_decode.split(' "/" ')
                        if len(parts) > 1:
                            target = parts[-1].strip().strip('"')
                            if self._selecionar_pasta_segura(mail, target):
                                self.enviados_detectada = target
                                return True
            
            # 3. Fallback: Tenta os nomes diretos
            for p in noms_pasto:
                if self._selecionar_pasta_segura(mail, p):
                    self.enviados_detectada = p
                    return True
                    
        except Exception as e:
            print(f"Erro ao descobrir pasta de enviados: {e}")
            
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

    def _extrair_identidade_tomador(self, texto_upper):
        """
        Extrai Nome e CNPJ do TOMADOR/DESTINATÁRIO dos 3 tipos de documento fiscal.
        Padrões robustos baseados nos layouts reais: NFe (DANFE), NFS-e e Fatura de Locação.
        Retorna (nome, cnpj) ou (None, None) se não encontrar campos rotulados.
        """
        def _limpa_cnpj(s): return re.sub(r'\D', '', s)
        
        nome_ret = None
        cnpj_ret = None

        # ── 1. Fatura de Locação (Padrão SERV WELD / ALVORADA) ──────────────────
        if "FATURA" in texto_upper:
            m_nome = re.search(r'NOME\s+DO\s+CLIENTE\s*[:\-]?\s*([A-Z0-9\s.\-&]{5,})', texto_upper)
            m_cnpj = re.search(r'CNPJ\s*[:\-]?\s*(\d{14}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', texto_upper)
            if m_nome and m_cnpj:
                nome_ret = m_nome.group(1).split('\n')[0].strip()
                cnpj_ret = _limpa_cnpj(m_cnpj.group(1))
                # Limpeza extra para nomes que capturam etiquetas da mesma linha
                nome_ret = re.split(r'\s{2,}|ENDERE[CÇ]O|CNPJ|INSCRI[CÇ][AÃ]O', nome_ret)[0].strip()
                if len(cnpj_ret) in (11, 14):
                    return nome_ret, cnpj_ret

        # ── 2. NFS-e (Padrão Distrito Federal / Outros) ────────────────────────
        if "TOMADOR" in texto_upper:
            # Busca bloco do tomador para evitar pegar dados do prestador
            bloco_t = re.search(r'(?:TOMADOR|DADOS DO TOMADOR)(.*?)(?:DADOS DO INTERMEDIÁRIO|DESCRIÇÃO DOS SERVIÇOS|DETALHAMENTO DOS TRIBUTOS|ENDEREÇO|$)', texto_upper, re.DOTALL)
            txt_busca = bloco_t.group(1) if bloco_t else texto_upper
            
            m_cnpj = re.search(r'CNPJ[/\s]*CPF\s*[:\-]?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{11,14})', txt_busca)
            m_nome = re.search(r'RAZ[AÃ]O\s+SOCIAL\s*[:\-]?\s*([A-Z0-9\s.\-&]{5,})', txt_busca)
            
            if m_cnpj and m_nome:
                nome_ret = m_nome.group(1).split('\n')[0].strip()
                cnpj_ret = _limpa_cnpj(m_cnpj.group(1))
                nome_ret = re.split(r'\s{2,}|ENDERE[CÇ]O|CNPJ', nome_ret)[0].strip()
                if len(cnpj_ret) in (11, 14):
                    return nome_ret, cnpj_ret

        # ── 3. NFe (DANFE) ──────────────────────────────────────────────────────
        if "DESTINAT" in texto_upper:
            # Padrão NFe: Nome e CNPJ estão no bloco DESTINATÁRIO / REMETENTE
            # Usamos . para aceitar Á em DESTINATÁRIO
            bloco_d = re.search(r'DESTINAT.RIO\s*/\s*REMETENTE(.*?)(?:FATURA|DUPLICATAS|C[AÁ]LCULO DO IMPOSTO|ENDERE[CÇ]O|$)', texto_upper, re.DOTALL)
            if bloco_d:
                txt_d = bloco_d.group(1)
                
                # Busca CNPJ formatado (XX.XXX.XXX/XXXX-XX) ou 14 dígitos
                m_cnpj = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{11,14})', txt_d)

                if m_cnpj:
                    cnpj_ret = _limpa_cnpj(m_cnpj.group(0)) # group(0) matches the whole match
                    
                    # O nome costuma estar ANTES do CNPJ no layout DANFE
                    txt_pre = txt_d[:m_cnpj.start()]
                    # Remove labels comuns (usamos . para evitar problemas de encoding com Ã/Á)
                    txt_pre = re.sub(r'NOME\s*/\s*RAZ.O\s+SOCIAL|CNPJ\s*/\s*CPF|DATA\s+DA\s+EMISS.O', ' ', txt_pre)
                    
                    # Busca sequências de palavras em maiúsculas que pareçam um nome
                    nomes = re.findall(r'([A-Z][A-Z0-9\s&.\-]{5,})', txt_pre)
                    if nomes:
                        # O último nome encontrado antes do CNPJ costuma ser o do Tomador
                        nome_ret = nomes[-1].strip()
                        if len(nome_ret) > 3:
                            return nome_ret, cnpj_ret

        
        return None, None


    def extrair_meta_documento(self, filepath, cnpj_alvo, nome_alvo, nf_alvo, vencimento_alvo, extra_context=None):
        """Extrai todos os metadados matemáticos e de identidade do arquivo."""
        meta = {
            'pertence_cliente': False, 
            'tem_nf': False, 
            'valores': set(), 
            'tem_vencimento': False, 
            'eh_imagem': False, 
            'conflito_identidade': False,
            'emissao': None,
            'tipo_detectado': 'BOLETO',
            'cnpj_detectado': None,
            'nf_detectada': None
        }
        texto = self._extrair_texto_arquivo(filepath)
        fname_limpo = os.path.basename(filepath).lower()
        
        meta['texto_extraido'] = texto # Armazena para uso proativo
        
        # Consolida tudo o que temos para pesquisar: texto do arquivo + assunto do e-mail (contexto)
        todo_texto = (texto or "") + " " + (extra_context or "")
        texto_limpo = re.sub(r'\D', '', todo_texto) if todo_texto else ""
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

        # ─── CNPJs PRÓPRIOS DO SISTEMA (EMITENTES) ──────────
        # Todos os CNPJs cadastrados no Credos são emitentes — nunca destinatários.
        # Buscamos do banco para ser dinâmico (suporta novas empresas cadastradas).
        cnpjs_proprios = {"54804458000122", "11504286000169"}  # fallback estático
        try:
            from src.database import carregar_todas_unidades_db
            for u in (carregar_todas_unidades_db() or []):
                cnpj_u = re.sub(r'\D', '', str(u.get('empresa_cnpj', '')))
                if cnpj_u:
                    cnpjs_proprios.add(cnpj_u)
        except Exception:
            pass  # fallback estático já está definido

        # ─── NOMES DE CAMPOS DE BOLETO (FALSOS POSITIVOS) ──────────
        # Esses termos aparecem logo após "PAGADOR" em boletos e NÃO são nomes de clientes.
        NOMES_FALSO_POSITIVO = {
            'NOSSO NÚMERO', 'NOSSO NUMERO', 'BANCO', 'AGÊNCIA', 'AGENCIA',
            'CONTA', 'VENCIMENTO', 'VALOR', 'CEDENTE', 'SACADO',
            'COMPENSAÇÃO', 'COMPENSACAO', 'LOCAL DE PAGAMENTO', 'DATA',
        }

        # ─── EXTRAÇÃO DE IDENTIDADE REFORÇADA (ANTI-VAZAMENTO) ──────────
        cnpj_destinatario = None
        nome_destinatario = None

        if texto_upper:
            # 1. Busca CNPJ do Destinatário no bloco do SACADO/PAGADOR
            #    Usamos janela pequena (300 chars) para evitar capturar o CNPJ do emitente
            padroes_cnpj_sacado = [
                r'SACADO[:\s]+([A-Z0-9 .]+?)\s+CNPJ[/CPF:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
                r'PAGADOR[:\s]+([A-Z0-9 .]+?)\s+CNPJ[/CPF:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
                r'DESTINAT[A-Z]*/REMETENTE[:\s]+([A-Z0-9 .]+?)\s+CNPJ[/CPF:\s]*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})',
            ]
            for pat in padroes_cnpj_sacado:
                m_c = re.search(pat, texto_upper)
                if m_c:
                    nome_cand = m_c.group(1).strip()
                    cnpj_cand = re.sub(r'\D', '', m_c.group(2))
                    # Só aceita se o CNPJ candidato NÃO for um dos nossos emitentes
                    if cnpj_cand not in cnpjs_proprios:
                        cnpj_destinatario = cnpj_cand
                        # Só aceita o nome se não for um campo de boleto falso-positivo
                        if nome_cand.upper() not in NOMES_FALSO_POSITIVO:
                            nome_destinatario = nome_cand
                    break

            # 2. Fallback: busca nome do sacado sem CNPJ confirmado
            if not nome_destinatario:
                match_nome = re.search(
                    r'(?:SACADO|PAGADOR|DESTINAT[A-Z]*/REMETENTE)[:\s]+([A-Z][A-Z0-9 .&-]{4,60})',
                    texto_upper
                )
                if match_nome:
                    cand = match_nome.group(1).strip().rstrip()
                    if cand.upper() not in NOMES_FALSO_POSITIVO and len(cand) > 4:
                        nome_destinatario = cand

        # ─── VERIFICAÇÃO DE CONFLITO LGPD (CRITÉRIO RIGOROSO) ──────────
        encontrou_alvo_cnpj = (cnpj_alvo_limpo and (cnpj_alvo_limpo in cnpjs_limpos or cnpj_alvo_limpo == cnpj_destinatario))

        # Só bloqueia por CNPJ se o CNPJ detectado for claramente de um TERCEIRO
        # (não nosso, e diferente do alvo). CNPJs de emitentes são ignorados.
        if cnpj_destinatario and cnpj_alvo_limpo:
            if cnpj_destinatario in cnpjs_proprios:
                print(f"      [LGPD] CNPJ detectado ({cnpj_destinatario}) é emitente próprio — ignorando.")
            elif cnpj_destinatario != cnpj_alvo_limpo:
                meta['conflito_identidade'] = True
                print(f"      [LGPD] BLOQUEIO: Destinatário CNPJ ({cnpj_destinatario}) != Alvo ({cnpj_alvo_limpo})")

        # Bloqueia por nome apenas se temos um nome de destinatário VÁLIDO (não campo de boleto)
        if nome_destinatario and nome_alvo and nome_destinatario.upper() not in NOMES_FALSO_POSITIVO:
            n_alvo_clean = re.sub(r'[^A-Z]', '', str(nome_alvo).upper())
            n_dest_clean = re.sub(r'[^A-Z]', '', str(nome_destinatario).upper())
            if len(n_dest_clean) > 5 and n_alvo_clean not in n_dest_clean and n_dest_clean not in n_alvo_clean:
                # Se o CNPJ JÁ BATEU, não bloqueamos por nome (pode ser variação tipo TECAR vs TECAR BRASILIA)
                if not encontrou_alvo_cnpj:
                    meta['conflito_identidade'] = True
                    print(f"      [LGPD] BLOQUEIO: Destinatário Nome ({nome_destinatario}) != Alvo ({nome_alvo})")
                else:
                    print(f"      [LGPD] Nome difere ({nome_destinatario} vs {nome_alvo}), mas CNPJ confirmou identidade. Ignorando conflito de nome.")

        # ─── PERTENCIMENTO POSITIVO ──────────
        # Se o CNPJ ou o Nome baterem perfeitamente, marcamos como pertencente
        if encontrou_alvo_cnpj:
            meta['pertence_cliente'] = True
        
        if not meta['pertence_cliente'] and nome_alvo:
            # Busca o nome curto ou o nome completo no texto todo
            def normalizar(t): return re.sub(r'[^A-Z0-9]', '', str(t).upper())
            texto_norm = normalizar(texto_upper)
            nome_norm = normalizar(nome_alvo)
            if nome_norm and len(nome_norm) > 4 and nome_norm in texto_norm:
                meta['pertence_cliente'] = True
            else:
                # Tenta pelo nome curto (primeiras 2 palavras)
                n_curto = normalizar(" ".join(nome_alvo.upper().split()[:2]))
                if n_curto and len(n_curto) > 4 and n_curto in texto_norm:
                    meta['pertence_cliente'] = True

        for c in cnpjs_limpos:
            if c not in cnpjs_proprios:
                if cnpj_alvo_limpo:
                    if c == cnpj_alvo_limpo:
                        meta['cnpj_detectado'] = c
                else:
                    if cnpj_destinatario: meta['cnpj_detectado'] = cnpj_destinatario
                    elif not meta['cnpj_detectado']: meta['cnpj_detectado'] = c

        nome_curto = " ".join(nome_alvo.upper().split()[:2]) if nome_alvo else ""
        primeiro_nome = nome_alvo.upper().split()[0] if nome_alvo else ""

        # 1. Identidade Positiva Forte (CNPJ)
        if encontrou_alvo_cnpj:
            meta['pertence_cliente'] = True
        
        # Identidade Flexivel (Nome) - Apenas se o CNPJ não foi conclusivo
        if not meta['pertence_cliente']:
            def normalizar(t): return re.sub(r'[^A-Z0-9]', '', str(t).upper())
            
            texto_norm = normalizar(texto_upper)
            fname_norm = normalizar(fname_limpo)
            nome_norm = normalizar(nome_alvo)
            # Exige pelo menos 2 palavras para o nome curto e pelo menos 6 caracteres
            partes_nome = nome_alvo.upper().split()
            nome_curto_norm = normalizar(" ".join(partes_nome[:2])) if len(partes_nome) >= 2 else ""
            
            # Match por nome completo
            if nome_norm and len(nome_norm) > 5 and (nome_norm in texto_norm or nome_norm in fname_norm):
                meta['pertence_cliente'] = True
            # Match por nome curto (2 primeiras palavras) - mais seguro que primeiro nome apenas
            elif nome_curto_norm and len(nome_curto_norm) >= 6 and (nome_curto_norm in texto_norm or nome_curto_norm in fname_norm):
                meta['pertence_cliente'] = True

        # ── VERIFICAÇÃO FORTE: Campos rotulados NFe / NFS-e / Fatura ────────────
        # Extrai nome+CNPJ dos campos EXATOS do documento e cruza com o cadastro.
        # Esta camada tem prioridade: confirma ou bloqueia com alta precisão.
        if texto_upper and (nome_alvo or cnpj_alvo_limpo):
            nome_tomador, cnpj_tomador = self._extrair_identidade_tomador(texto_upper)
            if nome_tomador or cnpj_tomador:
                def _norm(t): return re.sub(r'[^A-Z0-9]', '', str(t).upper())
                cnpj_match = bool(cnpj_tomador and cnpj_alvo_limpo and cnpj_tomador == cnpj_alvo_limpo)
                nome_match = False
                if nome_tomador and nome_alvo:
                    n_doc  = _norm(nome_tomador)
                    n_alvo = _norm(nome_alvo)
                    n_alvo_curto = _norm(' '.join(nome_alvo.upper().split()[:2]))
                    nome_match = (
                        (n_alvo and n_alvo in n_doc) or
                        (n_doc  and n_doc  in n_alvo) or
                        (n_alvo_curto and len(n_alvo_curto) > 4 and n_alvo_curto in n_doc)
                    )

                if cnpj_match or nome_match:
                    # Confirmação positiva forte — campo rotulado bateu com o cadastro
                    meta['pertence_cliente'] = True
                    meta['conflito_identidade'] = False
                    print(f"      [ID ✅] Tomador confirmado via campo rotulado: '{nome_tomador}' / {cnpj_tomador}")
                elif cnpj_tomador and cnpj_alvo_limpo and cnpj_tomador not in cnpjs_proprios:
                    # CNPJ de terceiro no campo rotulado — bloqueio definitivo
                    meta['conflito_identidade'] = True
                    meta['pertence_cliente'] = False
                    print(f"      [LGPD 🚫] Tomador '{nome_tomador}' / {cnpj_tomador} != alvo '{nome_alvo}' / {cnpj_alvo_limpo}")
                elif nome_tomador and nome_alvo:
                    # Só tem nome (sem CNPJ confirmado) — nome diferente = bloqueia
                    n_doc  = _norm(nome_tomador)
                    n_alvo = _norm(nome_alvo)
                    partes_alvo = str(nome_alvo).upper().split()
                    n_curto = _norm(' '.join(partes_alvo[:2])) if len(partes_alvo) >= 2 else ""

                    
                    # Se o nome extraído do campo "Tomador" é longo e não contém o alvo, bloqueia
                    if len(n_doc) > 6 and n_alvo not in n_doc and n_doc not in n_alvo and (not n_curto or n_curto not in n_doc):
                        meta['conflito_identidade'] = True
                        meta['pertence_cliente'] = False
                        print(f"      [LGPD 🚫] Conflito de Nome Tomador: '{nome_tomador}' != '{nome_alvo}'")


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
                meta['nf_detectada'] = nfs_reais_na_chave[0]
                if nf_alvo and any(n == nf_search for n in nfs_reais_na_chave):
                    meta['tem_nf'] = True
                elif nf_alvo:
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
        # ─── FASE 0: VERIFICAÇÃO EM REPOSITÓRIO LOCAL (DB) ──────────
        # Se o ProactiveScanner já indexou, não precisamos gastar tempo/processamento no IMAP
        try:
            from src.database import conectar as conectar_local
            cnpj_empresa = self.user.split('@')[0] if self.user else "" # Heurística simples ou busca global
            # Na verdade, o MailScanner já tem as credenciais. Vamos tentar conectar ao banco da empresa dona.
            # O ideal é que o MailScanner receba o CNPJ da empresa dona no __init__
            # Mas como fallback, vamos tentar achar qual banco tem esse email_user
            conn_c = conectar_local()
            res_c = conn_c.cursor().execute("SELECT empresa_cnpj FROM unidades").fetchall()
            conn_c.close()
            
            for r in res_c:
                emp_cnpj = r[0]
                conn_emp = conectar_local(emp_cnpj)
                c_emp = conn_emp.cursor()
                # Busca por NF e CNPJ do Cliente (Se tiver)
                nf_search = str(numero_nf).lstrip('0')
                query = "SELECT fpath_local FROM documentos_fiscais WHERE num_nf = ?"
                params = [nf_search]
                
                # Se o CNPJ do cliente foi passado, refinamos
                if cnpj_cliente:
                    cnpj_clean = re.sub(r'\D', '', str(cnpj_cliente))
                    query += " AND cnpj_cliente = ?"
                    params.append(cnpj_clean)
                
                rows = c_emp.execute(query, params).fetchall()
                conn_emp.close()
                
                arquivos_locais = []
                for row in rows:
                    p = row[0]
                    if p and os.path.exists(p):
                        arquivos_locais.append(p)
                
                if arquivos_locais:
                    print(f"   ✅ [Cache DB] Encontrado(s) {len(arquivos_locais)} arquivo(s) localmente para NF {numero_nf}")
                    return arquivos_locais
        except Exception as e_db:
            print(f"   ⚠️ Erro ao consultar cache de documentos: {e_db}")

        # ─── FASE 1: BUSCA IMAP (FALLBACK) ──────────────────────────
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
            'INBOX', '[Gmail]/Sent Mail', 'Sent', '[Gmail]/Sent', 'Enviados', 'Itens Enviados'
        ]

        pool_metadados = []
        arquivos_temp_lot = []
        seen_nomes_originais = set()  # Controle de deduplicao pelo nome real do arquivo (evita duplicatas entre emails)

        
        # ISOLAMENTO: Cada busca usa sua prpria subpasta nica para evitar
        # que a limpeza de uma NF apague os arquivos de outra NF.
        import uuid
        from datetime import datetime, timedelta
        pasta_destino_isolada = os.path.join(self.pasta_destino, f"nf_{nf_str}_{uuid.uuid4().hex[:8]}")
        os.makedirs(pasta_destino_isolada, exist_ok=True)

        try:
            _, folders = mail.list()
            pastas_reais = [f.decode().split('"/"')[-1].strip().replace('"', '') for f in folders]
            todas_pastas = list(set(pastas_candidatas + pastas_reais))
            
            # Remove pastas que contêm todos os emails (muito grandes para busca de BODY)
            todas_pastas = [p for p in todas_pastas if 'todos os e-mails' not in p.lower() and 'all mail' not in p.lower()]
            
            print(f"--- [Pooling] Iniciando busca para NF {nf_str} (Alvos: {alvos_validos})...", flush=True)

            # Filtro de data: últimos 180 dias para evitar travamento em buscas de BODY
            data_limite = (datetime.now() - timedelta(days=180)).strftime("%d-%b-%Y")
            search_prefix = f'SINCE "{data_limite}"'

            # --- ETAPA 1: Busca por Número de NF (Corpo e Assunto) ---
            ids_candidatos = []
            for pasta in todas_pastas:
                if any(x in pasta.lower() for x in ['spam', 'trash', 'lixeira', 'drafts']): continue
                if not self._selecionar_pasta_segura(mail, pasta): continue
                
                # Busca 1: NF no Assunto
                typ, data = mail.search(None, f'{search_prefix} SUBJECT "{nf_str}"')
                if data[0]: ids_candidatos.extend([(pasta, mid) for mid in data[0].split()])
                
                # Busca 2: NF no Corpo
                typ, data = mail.search(None, f'{search_prefix} BODY "{nf_str}"')
                if data[0]: ids_candidatos.extend([(pasta, mid) for mid in data[0].split()])
                
                if nf_str != nf_sem_zero:
                    typ, data = mail.search(None, f'{search_prefix} SUBJECT "{nf_sem_zero}"')
                    if data[0]: ids_candidatos.extend([(pasta, mid) for mid in data[0].split()])
                    typ, data = mail.search(None, f'{search_prefix} BODY "{nf_sem_zero}"')
                    if data[0]: ids_candidatos.extend([(pasta, mid) for mid in data[0].split()])

            if not ids_candidatos:
                print(f"   ⚠️ Nenhuma mensagem encontrada com NF {nf_str}. Tentando por Nome/CNPJ...")

            # --- ETAPA 2: Busca por CNPJ e Nome do Cliente (Ampla) ---
            cnpj_limpo = re.sub(r'\D', '', str(cnpj_cliente)) if cnpj_cliente else ""
            nome_parts = str(nome_cliente).upper().split()
            nome_curto = " ".join(nome_parts[:2]) if len(nome_parts) >= 2 else (nome_parts[0] if nome_parts else "")
            nome_busca_3 = " ".join(nome_parts[:3]) if len(nome_parts) >= 3 else nome_curto
            
            print(f"   [Debug] Termos: CNPJ={cnpj_limpo} | NomeCurto={nome_curto} | Nome3={nome_busca_3}")
            
            pastas_busca_ampla = ['INBOX', '[Gmail]/Sent Mail', 'Sent', 'Enviados', 'Itens Enviados', 'Sent Items']
            for pasta in pastas_busca_ampla:
                if not self._selecionar_pasta_segura(mail, pasta): continue
                
                # Busca por CNPJ
                if cnpj_limpo and len(cnpj_limpo) > 10:
                    typ, data = mail.search(None, f'{search_prefix} (OR SUBJECT "{cnpj_limpo}" BODY "{cnpj_limpo}")')
                    if data[0]:
                        found = data[0].split()
                        print(f"      [Debug] Pasta {pasta}: {len(found)} emails por CNPJ")
                        for mid in sorted(found, reverse=True)[:10]: ids_candidatos.append((pasta, mid))
                
                # Busca por Nome (3 palavras ou 2)
                termos_nome = [nome_busca_3, nome_curto]
                for termo in termos_nome:
                    if not termo or len(termo) < 4: continue
                    typ, data = mail.search(None, f'{search_prefix} SUBJECT "{termo}"')
                    if data[0]:
                        found = data[0].split()
                        print(f"      [Debug] Pasta {pasta}: {len(found)} emails por Nome Assunto ({termo})")
                        for mid in sorted(found, reverse=True)[:10]: ids_candidatos.append((pasta, mid))
                    
                    typ, data = mail.search(None, f'{search_prefix} BODY "{termo}"')
                    if data[0]:
                        found = data[0].split()
                        print(f"      [Debug] Pasta {pasta}: {len(found)} emails por Nome Corpo ({termo})")
                        for mid in sorted(found, reverse=True)[:10]: ids_candidatos.append((pasta, mid))

            # --- ETAPA 3: LAST RESORT (SCAN RECENTES) ---
            if not ids_candidatos:
                print("   ⚠️ Sem resultados. Ativando Busca de Último Recurso (Últimos 50 emails)...")
                for pasta in ['INBOX', '[Gmail]/Sent Mail', 'Sent', 'Enviados']:
                    if not self._selecionar_pasta_segura(mail, pasta): continue
                    typ, data = mail.search(None, 'ALL')
                    if data[0]:
                        recentes = data[0].split()[-50:]
                        for mid in recentes: ids_candidatos.append((pasta, mid))

            # Consolida e-mails únicos para processar
            ids_unicos = []
            seen_ids = set()
            for p, mid in ids_candidatos:
                if (p, mid) not in seen_ids:
                    ids_unicos.append((p, mid))
                    seen_ids.add((p, mid))
            
            print(f"   🔎 Total de {len(ids_unicos)} mensagens em análise profunda.")

            # Processamento de Anexos do Pool
            for pasta, e_id in ids_unicos[:50]:
                if not self._selecionar_pasta_segura(mail, pasta): continue
                try:
                    _, msg_data = mail.fetch(e_id, "(RFC822)")
                except: continue
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
                        if fname_clean.lower() in seen_nomes_originais: continue
                        seen_nomes_originais.add(fname_clean.lower())

                        # REMOVIDO PREFIXO nf_str: Evita o bug de "match circular"
                        fpath = os.path.join(pasta_destino_isolada, fname_clean)
                        with open(fpath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        
                        meta = self.extrair_meta_documento(fpath, cnpj_cliente, nome_cliente, nf_str, vencimento)
                        meta['fpath'] = fpath
                        meta['nome_original'] = fname_clean
                        meta['email_id'] = str(e_id.decode())
                        
                        print(f"      [Pool] Arquivo: {fname_clean} | NF detectada: {meta.get('nf_detectada')} | Pertence: {meta.get('pertence_cliente')} | Conflito: {meta.get('conflito_identidade')}")
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

                # Regra de Ouro: Match de Número de NF
                # CUIDADO: O nf_num pode aparecer no cNF (últimos 9 dígitos da chave de acesso).
                # Ex: chave ...000001286 1 000051237 → o '1237' está no cNF, NÃO é a NF 1237.
                # Solução: para arquivos com chave de acesso no nome (44 dígitos), só aceita
                # match se o nf_num estiver nos dígitos 25-34 da chave (posição do nNF).
                chave_no_nome = re.search(r'(\d{44})', nome_orig)
                if chave_no_nome:
                    nf_da_chave = chave_no_nome.group(1)[25:34].lstrip('0')
                    nf_match_nome = (nf_da_chave == nf_num)  # Só aceita se for o nNF exato
                else:
                    # Arquivo sem chave de acesso no nome (boletos, faturas, etc.)
                    # Aceita se o número aparecer delimitado (não dentro de outro número)
                    nf_match_nome = bool(re.search(rf'(?<!\d){re.escape(nf_num)}(?!\d)', nome_orig))

                nf_match = nf_match_nome or m.get('tem_nf', False)
                
                # BINGO: Se o Número da NF bate E a Identidade bate → APROVADO
                # Regra de Segurança Máxima [LGPD]: Para arquivos fiscais (PDF/XML), o match de Valor/Vencimento NÃO é suficiente.
                # EXIGIMOS que o Nome ou CNPJ no documento coincida com o cadastro.
                
                if nf_match:
                    # Bloqueio de Segurança: Se detectou outra identidade (conflito), para tudo.
                    if m.get('conflito_identidade', False):
                        print(f"    [LGPD 🚫] BLOQUEIO CRÍTICO: NF {nf_num} pertence a OUTRO cliente. Descartando {bname}")
                        continue

                    # Critério de Aprovação:
                    # 1. Se for PDF/XML (Documento Fiscal), EXIGE identidade confirmada.
                    # 2. Se for outro tipo (Boleto genérico), aceita Valor ou Vencimento como prova.
                    ext = os.path.splitext(m['fpath'])[1].lower()
                    if ext in ['.pdf', '.xml']:
                        if identidade_match:
                            arquivos_aprovados.add(m['fpath'])
                            emails_com_nf_confirmada.add(m['email_id'])
                            print(f"    ✅ BINGO IDENTIDADE: NF {nf_num} confirmada para {cliente_nome}")
                        else:
                            print(f"    [LGPD ⚠️] NF {nf_num} encontrada ({bname}), mas identidade não confirmada no documento. Ignorando.")
                    else:
                        # Boletos/Faturas de texto simples: aceita evidências matemáticas se não houver conflito
                        if identidade_match or valor_match or venc_match:
                            arquivos_aprovados.add(m['fpath'])
                            emails_com_nf_confirmada.add(m['email_id'])
                            print(f"    ✅ BINGO APOIO: Arquivo {bname} aprovado por valor/venc/id")



            # Passada 2: Aprova outros arquivos (Boletos/XMLs) que esto nos mesmos e-mails aprovados
            for m in pool_metadados:
                if m['fpath'] in arquivos_aprovados: continue
                
                if m['email_id'] in emails_com_nf_confirmada:
                    # Aprovação por associação: arquivo no mesmo e-mail que uma NF confirmada.
                    # EXIGE identidade confirmada (pertence_cliente=True) E sem conflito.
                    if m.get('conflito_identidade', False):
                        f_name = os.path.basename(m['fpath'])
                        print(f"    [LGPD] Bloqueio Associação: {f_name} tem conflito de identidade.")
                        continue

                    if not m.get('pertence_cliente', False):
                        f_name = os.path.basename(m['fpath'])
                        print(f"    [LGPD] Bloqueio Associação: {f_name} sem identidade confirmada.")
                        continue

                    arquivos_aprovados.add(m['fpath'])
                    print(f"    📎 APROVADO POR ASSOCIAÇÃO: {os.path.basename(m['fpath'])}")

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
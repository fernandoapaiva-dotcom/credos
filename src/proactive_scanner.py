import threading
import email
import time
import os
from datetime import datetime, timedelta
from src.database import conectar, carregar_todas_unidades_db, carregar_configuracoes_db, listar_titulos_por_cliente
from src.mail_scanner import MailScanner
from src.evolution_controller import EvolutionController
from src.manager import Manager

def _garantir_colunas_documentos(conn):
    """Garante que documentos_fiscais tenha as colunas do repositório V2."""
    c = conn.cursor()
    c.execute("PRAGMA table_info(documentos_fiscais)")
    cols = [col[1] for col in c.fetchall()]
    if 'pasta_repo' not in cols:
        c.execute("ALTER TABLE documentos_fiscais ADD COLUMN pasta_repo TEXT")
    if 'nome_cliente' not in cols:
        c.execute("ALTER TABLE documentos_fiscais ADD COLUMN nfs_vinculada TEXT")
    conn.commit()

class ProactiveScanner:
    def __init__(self):
        self.intervalo = 300  # 5 minutos entre varreduras
        self.running = False
    
    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("🚀 ProactiveScanner iniciado em background.")

    def _run_loop(self):
        while self.running:
            try:
                print(f"🕒 [{datetime.now().strftime('%H:%M:%S')}] Iniciando ciclo proativo...")
                unidades = carregar_todas_unidades_db()
                for u in unidades:
                    self.processar_unidade(u['empresa_cnpj'])
                
                print(f"✅ Ciclo finalizado. Próximo em {self.intervalo}s.")
                time.sleep(self.intervalo)
            except Exception as e:
                print(f"❌ Erro no loop do ProactiveScanner: {e}")
                time.sleep(60)

    def processar_unidade(self, cnpj):
        config = carregar_configuracoes_db(cnpj)
        if not config.get('base_mail_user'): return

        scanner = MailScanner(config)
        mail = scanner.conectar()
        if not mail: return

        try:
            # Seleciona pasta de ENVIADOS (O SoftSystem manda, nós capturamos na saída)
            scanner.descobrir_pasta_enviados(mail)
            
            # 1. Indexação de novos e-mails (Proativa na Saída)
            self.indexar_novos_emails(cnpj, scanner, mail)
            
            # 2. Lembretes Pré-Vencimento (Proativo)
            self.verificar_prevencimento(cnpj, config)
            
        finally:
            mail.logout()

    def indexar_novos_emails(self, cnpj, scanner, mail, since_date=None):
        """Busca os e-mails e indexa anexos no banco. Default: Hoje."""
        if since_date is None:
            since_date = datetime.now().strftime("%d-%b-%Y")
        
        # 1. Busca Notas Fiscais e Boletos por padrões de assunto comuns
        status, data = mail.search(None, f'SINCE "{since_date}"')
        if status != "OK" or not data[0]: return

        ids = data[0].split()
        # Detecta em qual ambiente está e usa o caminho correto
        if os.name == 'nt':  # Windows (dev local)
            repo_base = os.path.join(os.getcwd(), "data", "repository_v2")
        else:  # Linux (Docker/produção)
            repo_base = "/app/data/repository_v2"
        os.makedirs(repo_base, exist_ok=True)

        conn = conectar(cnpj)
        _garantir_colunas_documentos(conn)  # Garante migração
        c = conn.cursor()

        for e_id in ids:
            try:
                # Evita re-indexar o mesmo e-mail (UID)
                uid = e_id.decode()
                c.execute("SELECT id FROM documentos_fiscais WHERE email_uid = ?", (uid,))
                if c.fetchone(): continue

                _, msg_data = mail.fetch(e_id, '(RFC822)')
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                
                # Contexto para o Sniper/Parsing
                assunto = scanner.limpar_nome_arquivo(msg.get('Subject', ''))
                print(f"   🔍 Indexando e-mail: {assunto}")

                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                    
                    fname = scanner.limpar_nome_arquivo(part.get_filename())
                    if not fname.lower().endswith(('.pdf', '.xml')): continue

                    # Salva temporariamente para processar
                    tmp_path = os.path.join("temp_data", fname)
                    with open(tmp_path, "wb") as f:
                        f.write(part.get_payload(decode=True))

                    # Extrai Metadados Proativos
                    # No modo proativo, não sabemos o CNPJ alvo ainda, então passamos None para o Scanner tentar achar
                    meta = scanner.extrair_meta_documento(tmp_path, None, None, None, None, extra_context=assunto)
                    texto_extraido = meta.get('texto_extraido') or ""
                    texto_upper = texto_extraido.upper()
                    
                    if meta.get('cnpj_detectado') or meta.get('pertence_cliente') or meta.get('tem_nf') or meta.get('valores'):
                        # Identificamos um documento fiscal!
                        cnpj_extraido = meta.get('cnpj_detectado') 
                        nf_num = meta.get('nf_detectada') or ""
                        tipo = meta.get('tipo_detectado', 'BOLETO')

                        # Move para o repositório oficial estruturado
                        from src.fiscal_repository import FiscalRepository
                        if os.name == 'nt':
                            repo = FiscalRepository(
                                db_dir=os.path.join(os.getcwd()),
                                repo_dir=os.path.join(os.getcwd(), "data", "repository_v2")
                            )
                        else:
                            repo = FiscalRepository()

                        repo_path = repo.organizar_arquivo(
                            cnpj,
                            cnpj_extraido or "Geral",
                            "Desconhecido",
                            tipo,
                            nf_num,
                            tmp_path,
                            atualizar_db=False
                        )

                        if repo_path:
                            # Salva no Banco de Documentos
                            agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            c.execute("""
                                INSERT INTO documentos_fiscais
                                (cnpj_cliente, num_nf, tipo, emissao, valor, fpath_local, email_uid, created_at, pasta_repo)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (cnpj_extraido, nf_num, tipo, meta.get('emissao'), list(meta.get('valores'))[0] if meta.get('valores') else 0,
                                repo_path, uid, agora, repo_path))

                            # ─── AUTO-LANÇAMENTO NO CRM (TÍTULOS) ──────────
                            # Se identificamos o cliente e o valor, lançamos a dívida automaticamente
                            if cnpj_extraido and meta.get('valores'):
                                valor_nf = list(meta.get('valores'))[0]
                                emissao_nf = meta.get('emissao')
                                
                                # 1. Busca nome do cliente no banco (ou usa o detectado)
                                c.execute("SELECT nome FROM clientes WHERE cnpj = ?", (cnpj_extraido,))
                                res_cli = c.fetchone()
                                nome_final = res_cli[0] if res_cli else meta.get('nome_detectado', "Cliente Novo (Scanner)")
                                
                                if not res_cli:
                                    # Cria o cliente se for novo, sinalizando como scanner_pendente para preenchimento de contato no CRM
                                    c.execute(
                                        "INSERT INTO clientes (nome, cnpj, scanner_pendente) VALUES (?, ?, 1)", 
                                        (nome_final, cnpj_extraido)
                                    )
                                
                                # 2. Verifica se o título já existe
                                c.execute("SELECT id FROM titulos WHERE numero_nf = ? AND pagador = ?", (nf_num, nome_final))
                                if not c.fetchone():
                                    # Calcula vencimento aproximado se não detectado (ex: emissão + 30 dias)
                                    venc = meta.get('vencimento')
                                    if not venc and emissao_nf:
                                        try:
                                            dt_emi = datetime.strptime(emissao_nf, "%d/%m/%Y")
                                            venc = (dt_emi + timedelta(days=30)).strftime("%d/%m/%Y")
                                        except: pass
                                    
                                    if not venc: venc = (datetime.now() + timedelta(days=15)).strftime("%d/%m/%Y")

                                    # Se o cliente acabou de ser criado (scanner_pendente = 1), o título entra como Pausado para não estourar erro de falta de contato.
                                    acao_inicial = 'Pausar' if not res_cli else 'Cobrar'

                                    c.execute("""
                                        INSERT INTO titulos (pagador, numero_nf, vencimento, emissao, valor, status, acao)
                                        VALUES (?, ?, ?, ?, ?, 'Aberto', ?)
                                    """, (nome_final, nf_num, venc, emissao_nf, valor_nf, acao_inicial))
                                    print(f"      🚀 AUTO-LANÇAMENTO: NF {nf_num} para {nome_final} (R$ {valor_nf:.2f}) [{acao_inicial}]")

                            print(f"      Indexado (Repo V2): {tipo} {nf_num} para CNPJ {cnpj_extraido}")
                    else:
                        if os.path.exists(tmp_path): os.remove(tmp_path)

                conn.commit()
            except Exception as ex:
                print(f"      ⚠️ Erro ao indexar e-mail {e_id}: {ex}")

        conn.close()

    def indexar_retroativo(self, cnpj, dias=180):
        """Varre o passado (Caixa de Saída) e indexa tudo o que encontrar."""
        config = carregar_configuracoes_db(cnpj)
        scanner = MailScanner(config)
        mail = scanner.conectar()
        if not mail: return False

        try:
            scanner.descobrir_pasta_enviados(mail)
            # Calcula data de início (Fernando pediu Out/2025. Hoje é Abr/2026 ~ 180 dias)
            inicio = (datetime.now() - timedelta(days=dias)).strftime("%d-%b-%Y")
            print(f"🔎 Iniciando indexação retroativa desde {inicio} para CNPJ {cnpj}...")
            
            status, data = mail.search(None, f'SINCE "{inicio}"')
            if status == "OK" and data[0]:
                self.indexar_novos_emails(cnpj, scanner, mail, since_date=inicio)
                return True
            return False
        finally:
            mail.logout()

    def verificar_prevencimento(self, cnpj, config):
        """Verifica títulos que vencem em 2 dias e notifica (apenas status Aberto + acao Cobrar)."""
        from src.database import is_global_halt_active
        if is_global_halt_active():
            print(f"🛑 [EMERGÊNCIA] Lembrete proativo pausado pelo pânico global ({cnpj}).")
            return

        conn = conectar(cnpj)
        c = conn.cursor()
        
        # Alvo: Títulos em Aberto com acao Cobrar que vencem daqui a 2 dias
        alvo = (datetime.now() + timedelta(days=2)).strftime("%d/%m/%Y")
        
        try:
            # Seleciona todos os títulos em Aberto (Cobrar ou Pausar) para a data alvo
            c.execute("""
                SELECT id, pagador, numero_nf, valor, acao
                FROM titulos
                WHERE vencimento = ? AND status = 'Aberto'
            """, (alvo,))
            titulos = c.fetchall()
            
            if not titulos: return

            evo = EvolutionController(config)
            mgr = Manager(cnpj) # Manager já carrega as instâncias
            
            for tid, pagador, nf, valor, acao in titulos:
                # Evita enviar o mesmo lembrete duas vezes (Log de auditoria)
                c.execute("SELECT count(*) FROM logs_envio WHERE cliente = ? AND tipo_envio = 'Lembrete' AND detalhes LIKE ?", 
                          (pagador, f"%NF {nf}%"))
                if c.fetchone()[0] > 0: continue

                # Busca contato do cliente
                c.execute("SELECT whatsapp, email, scanner_pendente FROM clientes WHERE trim(nome) = ?", (pagador.strip(),))
                contato = c.fetchone()
                
                tem_contato = False
                if contato:
                    whatsapp, email, scanner_pendente = contato
                    # Considera que tem contato se WhatsApp/Email existir E a flag de pendência (1) já tiver sido removida (0)
                    if (whatsapp or email) and not scanner_pendente:
                        tem_contato = True

                # ROTINA EXTRA DE AUTO-ATIVAÇÃO SOLICITADA PELO USUÁRIO
                if acao == 'Pausar' and tem_contato:
                    c.execute("UPDATE titulos SET acao = 'Cobrar' WHERE id = ?", (tid,))
                    conn.commit()
                    print(f"🔄 Auto-Ativação do Título {nf} para {pagador}: o contato foi preenchido.")
                    acao = 'Cobrar'

                if acao == 'Pausar':
                    # Se continua pausado (sem contato), não tenta enviar para o cliente
                    if not tem_contato:
                        operador = config.get('operador_whatsapp')
                        if operador:
                            aviso = f"Oi Fernando! Tudo bem?\n\nIdentifiquei que o cliente *{pagador}* tem a NF {nf} vencendo daqui a 2 dias, mas como não tenho o WhatsApp ou Email dele aqui no banco do Credos, não consegui enviar o lembrete proativo. 😕\n\n*Pode me enviar por favor o telefone/whatsapp dele para eu adicionar e já deixar tudo em ordem?*"
                            # Verifica se já avisou o Fernando hoje
                            c.execute("SELECT count(*) FROM logs_envio WHERE cliente = 'SISTEMA' AND tipo_envio = 'Aviso Operador' AND detalhes LIKE ?", (f"%{pagador}%",))
                            if c.fetchone()[0] == 0:
                                evo.enviar_mensagem_texto(operador, aviso)
                                mgr.salvar_log_envio("SISTEMA", "Aviso Operador", "Sucesso", f"Solicitado contato de {pagador} ao Fernando", "Analu Proativa")
                    continue

                # Se acao é Cobrar e tem contato, envia o lembrete
                if tem_contato:
                    # Analu envia lembrete gentil
                    msg = f"Olá! Aqui é a Analu do financeiro. 🤖\n\nPassando para lembrar que a sua NF {nf} no valor de R$ {valor:.2f} vence daqui a 2 dias ({alvo}).\n\nGostaria de confirmar se deu tudo certo com o recebimento do boleto ou se precisa de alguma ajuda? 😊"
                    num = whatsapp if whatsapp else None
                    if num:
                        res = evo.enviar_mensagem_texto(num, msg)
                        if res:
                            mgr.salvar_log_envio(pagador, "Lembrete", "Sucesso", f"Lembrete de vencimento NF {nf} enviado para {num}", "Analu Proativa")

        except Exception as e:
            print(f"Erro em verificar_prevencimento ({cnpj}): {e}")
        finally:
            conn.close()

# Singleton do Scanner
proactive_worker = ProactiveScanner()

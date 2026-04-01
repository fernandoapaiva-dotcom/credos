import os
import asyncio
import base64
from datetime import datetime
from playwright.async_api import async_playwright
from src.database import conectar, carregar_configuracoes_db

class CartorioAutomation:
    def __init__(self, cnpj_empresa):
        self.cnpj_empresa = cnpj_empresa
        self.config = carregar_configuracoes_db(cnpj_empresa)
        self.pfx_b64 = self.config.get("cartorio_pfx_b64")
        self.pfx_pass = self.config.get("cartorio_pfx_pass")
        self.base_url = "https://www.pesquisaprotesto.com.br"

    async def _get_browser_context(self, playwright):
        """
        Conecta a uma instância do Chrome já aberta com depuração remota (Porta 9222).
        Isso permite herdar o login, Web PKI e certificados do usuário.
        """
        print("🔌 Tentando conectar ao Chrome aberto (Porta 9222)...")
        try:
            # Conecta à instância que o usuário abriu via ABRIR_CHROME_ROBO.bat
            # Usamos 127.0.0.1 para evitar problemas com IPv6 (::1) no Windows
            browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            # Usa o primeiro contexto disponível (que terá a sessão do usuário)
            context = browser.contexts[0]
            return context
        except Exception as e:
            raise Exception("Navegador não detectado. Certifique-se de que você abriu o Edge usando o arquivo 'ABRIR_EDGE_ROBO.bat'.")

    async def enviar_titulo(self, titulo_id, dry_run=True):
        """
        Executa o fluxo de envio de um título para o cartório pegando carona na sessão do usuário.
        """
        conn = conectar(self.cnpj_empresa)
        conn.row_factory = self.dict_factory
        t = conn.cursor().execute("SELECT * FROM titulos WHERE id=?", (titulo_id,)).fetchone()
        cli = conn.cursor().execute("SELECT * FROM clientes WHERE nome=?", (t['pagador'],)).fetchone()
        conn.close()

        if not t or not cli:
            return False, "Título ou Cliente não encontrado no banco."

        async with async_playwright() as p:
            context = None
            try:
                context = await self._get_browser_context(p)
                pages = context.pages
                page = pages[0] if pages else await context.new_page()
                
                print(f"📍 URL Atual: {page.url}")
                
                if "/PedidoProtesto" not in page.url:
                    print("🚀 Navegando para Pedido de Protesto...")
                    await page.goto(f"{self.base_url}/PedidoProtesto")
                    await page.wait_for_load_state("networkidle")

                # --- PASSO 1: DADOS DA DÍVIDA ---
                print("📝 Preenchendo Passo 1: Dados da Dívida...")
                
                # 1. Espécie (Vue Select — selecionar DM com precisão)
                try:
                    # Limpa qualquer seleção anterior e abre o dropdown
                    await page.locator("#vs1__combobox").click()
                    await page.wait_for_timeout(800)
                    
                    # Digita "DM" no campo de busca do Vue Select
                    await page.keyboard.type("DM")
                    await page.wait_for_timeout(1000)
                    
                    # Busca a opção cujo texto COMEÇA com "DM" (ex: "DM - Duplicata Mercantil")
                    # Usa evaluate para verificar o texto exato de cada <li>
                    selecionado = await page.evaluate("""
                        () => {
                            const ops = document.querySelectorAll('li.vs__dropdown-option');
                            for (const op of ops) {
                                const txt = op.textContent.trim();
                                if (txt === 'DM' || txt.startsWith('DM')) {
                                    op.click();
                                    return txt;
                                }
                            }
                            return null;
                        }
                    """)
                    
                    if selecionado:
                        print(f"✅ Espécie selecionada: {selecionado}")
                    else:
                        # Último recurso: pressiona Enter para selecionar o item destacado
                        await page.keyboard.press("Enter")
                        print("⚠️ Espécie: item DM não encontrado na lista, Enter pressionado.")
                except Exception as e:
                    print(f"⚠️ Erro na Espécie: {e}")

                # 2. Número
                await page.fill("#dados_divida_numero", str(t['numero_nf']))

                # 3. Datas 
                # Usa a Data de Emissão extraída do Email (salva no DB) sempre que possível
                vencimento_dt = datetime.strptime(str(t['vencimento']), "%d/%m/%Y")
                
                if t.get('emissao'):
                    print(f"✅ Utilizando Data de Emissão Extraída via Email: {t['emissao']}")
                    try:
                        emissao_dt = datetime.strptime(str(t['emissao']).strip(), "%d/%m/%Y")
                    except:
                        emissao_dt = datetime.strptime(str(t['emissao']).strip().split()[0], "%Y-%m-%d") if '-' in t['emissao'] else (vencimento_dt).replace(day=max(1, vencimento_dt.day-3))
                else:
                    # Fallback emergencial (não deve ocorrer pois o orquestrador trava antes)
                    print(f"⚠️ Usando Emissão retroativa padrão.")
                    emissao_dt = (vencimento_dt).replace(day=max(1, vencimento_dt.day-3))
                
                emissao_iso = emissao_dt.strftime("%Y-%m-%d")
                vencimento_iso = vencimento_dt.strftime("%Y-%m-%d")
                
                await page.fill("#dados_divida_dt_emissao", emissao_iso)
                await page.fill("#dados_divida_dt_vencimento", vencimento_iso)
                
                # 4. Valores
                valor_str = f"{float(t['valor']):.2f}".replace('.', ',')
                await page.fill("#dados_divida_valor_titulo", valor_str)
                await page.fill("#dados_divida_valor_protestado", valor_str)
                
                await page.screenshot(path="passo1_completo.png")
                await self._clicar_prosseguir(page)

                # Passo 2: Credor (Confirmar)
                print("🏢 Passo 2: Dados do Credor...")
                await page.wait_for_selector("#documento_cedente", state="visible", timeout=10000)
                await page.screenshot(path="passo2_credor.png")
                await self._clicar_prosseguir(page)

                # Passo 3: Devedor
                print("👤 Passo 3: Dados do Devedor...")
                await page.wait_for_selector("#documento_devedor", state="visible", timeout=10000)
                
                # Preenchimento por IDs capturados
                cnpj = str(cli.get('cnpj', '')).replace('.', '').replace('/', '').replace('-', '').strip()
                if cnpj:
                    await page.locator("#documento_devedor").click()
                    await page.keyboard.type(cnpj) # type é mais seguro para campos com máscara
                else: print("⚠️ Alerta: CNPJ do devedor está VAZIO no banco.")

                await page.fill("#nome_devedor", str(cli['nome']))
                
                if cli.get('email'):
                    await page.fill("#email_devedor", str(cli['email']))
                if cli.get('telefone'):
                    await page.fill("#celular_devedor", str(cli['telefone']))
                
                cep = str(cli.get('cep', '')).replace('-', '').replace('.', '').strip()
                if cep:
                    await page.locator("#devedor_cep").click()
                    await page.keyboard.type(cep)
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(3000) # Espera AJAX endereço
                else: print("⚠️ Alerta: CEP do devedor está VAZIO no banco.")
                
                await page.fill("#endereco_devedor_numero", str(cli.get('numero') or 'SN'))
                
                # Campos de Logradouro/Bairro/Cidade podem vir do Banco se o CEP falhou
                if not await page.locator("#endereco_devedor_logradouro").input_value() and cli.get('endereco'):
                    await page.fill("#endereco_devedor_logradouro", str(cli['endereco']))
                if not await page.locator("#devedor_bairro").input_value() and cli.get('bairro'):
                    await page.fill("#devedor_bairro", str(cli['bairro']))
                if not await page.locator("#devedor_cidade").input_value() and cli.get('cidade'):
                    await page.fill("#devedor_cidade", str(cli['cidade']))

                # UF (Vue Select vs5__combobox)
                if not await page.locator("#vs5__combobox").inner_text() or "Loading" in await page.locator("#vs5__combobox").inner_text():
                     await page.locator("#vs5__combobox").click()
                     await page.keyboard.type("DF")
                     await page.wait_for_timeout(500)
                     await page.keyboard.press("Enter")

                print("✅ Dados do devedor preenchidos.")
                await page.screenshot(path="passo3_devedor_fim.png")
                await self._clicar_prosseguir(page)

                # Passo 4: Revisão
                print("📋 Passo 4: Revisão final...")
                await page.wait_for_load_state("networkidle")
                await page.screenshot(path="passo4_revisao.png")
                
                if dry_run:
                    print("🔐 Modo Dry-Run: parado antes do Passo 5 (Solicitar Protesto).")
                    return True, "Simulação concluída com sucesso até a revisão."

                # Passo 5: Envio Real — Clicar em "Solicitar o Protesto"
                print("🚀 Passo 5: Solicitando Protesto...")
                await page.screenshot(path="passo5_pre_envio.png")
                
                # Tenta os seletores mais comuns do botão de submit final
                btn_submit_selectors = [
                    "button:has-text('Solicitar o Protesto')",
                    "button:has-text('Confirmar')",
                    "button:has-text('Enviar')",
                    "button[type='submit']",
                ]
                clicou_submit = False
                for sel in btn_submit_selectors:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=3000):
                        await btn.click()
                        clicou_submit = True
                        print(f"✅ Botão Submit clicado: {sel}")
                        break
                
                if not clicou_submit:
                    return False, "Botão 'Solicitar o Protesto' não encontrado na página."
                
                # Aguarda confirmação de sucesso da página (redirecionamento ou toast)
                await page.wait_for_timeout(5000)
                await page.screenshot(path="passo5_final.png")
                
                # Atualiza o job como Sucesso no banco
                self._atualizar_job_status(t['id'], "Sucesso")
                
                print("✅ Passo 5 concluído! Título enviado ao cartório com sucesso.")
                return True, "Título protestado com sucesso."

            except Exception as e:
                return False, f"Erro na automação: {str(e)}"
            finally:
                if context:
                    await context.close()

    async def _clicar_prosseguir(self, page):
        """Helper para clicar no botão de avanço do wizard"""
        btn_selectors = [
            "button:has-text('Prosseguir')", 
            "button:has-text('Próximo')",
            "button:has-text('Confirmar')"
        ]
        for sel in btn_selectors:
            btn = page.locator(sel).first
            if await btn.is_visible():
                await btn.click()
                await page.wait_for_load_state("networkidle")
                return True
        return False

    def _atualizar_job_status(self, titulo_id, status, erro=None):
        conn = conectar(self.cnpj_empresa)
        c = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            UPDATE cartorio_jobs 
            SET status_automacao = ?, log_erro = ?, data_execucao = ?
            WHERE titulo_id = ? AND status_automacao = 'Processando'
        """, (status, erro, agora, titulo_id))
        
        if status == "Sucesso":
            # Atualiza o status do título e registra a data de envio para acompanhamento
            c.execute(
                "UPDATE titulos SET status = 'Cartório', data_envio_cartorio = ?, status_retorno_cartorio = 'Aguardando' WHERE id = ?",
                (agora, titulo_id)
            )
            
        conn.commit()
        conn.close()

    def dict_factory(self, cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

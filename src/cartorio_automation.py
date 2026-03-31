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
        Inicia o browser com o certificado A1 configurado.
        """
        browser = await playwright.chromium.launch(headless=True)
        
        if not self.pfx_b64:
            raise Exception("Certificado A1 (.pfx) não configurado no sistema.")

        # Decodifica o certificado para um buffer temporário
        pfx_buffer = base64.b64decode(self.pfx_b64)
        
        # Configura o contexto com o certificado de cliente (Playwright 1.41+)
        context = await browser.new_context(
            client_certificates=[{
                "origin": self.base_url,
                "pfx": pfx_buffer,
                "passphrase": self.pfx_pass
            }],
            viewport={'width': 1280, 'height': 720}
        )
        return browser, context

    async def enviar_titulo(self, titulo_id):
        """
        Executa o fluxo de envio de um título para o cartório.
        """
        conn = conectar(self.cnpj_empresa)
        conn.row_factory = self.dict_factory
        t = conn.cursor().execute("SELECT * FROM titulos WHERE id=?", (titulo_id,)).fetchone()
        
        # Busca dados extras do cliente para o cartório (Razão Social, Endereço, etc)
        cli = conn.cursor().execute("SELECT * FROM clientes WHERE nome=?", (t['pagador'],)).fetchone()
        conn.close()

        if not t or not cli:
            return False, "Título ou Cliente não encontrado no banco."

        status_msg = ""
        async with async_playwright() as p:
            browser = None
            try:
                browser, context = await self._get_browser_context(p)
                page = await context.new_page()
                
                # 1. Login/Acesso ao Portal
                await page.goto(f"{self.base_url}/login") # URL hipotética baseada na busca
                
                # O Playwright cuida do handshake SSL/TLS com o certificado automaticamente
                # Pode haver um botão "Entrar com Certificado Digital"
                cert_button = page.get_by_text("Certificado Digital", exact=False)
                if await cert_button.is_visible():
                    await cert_button.click()
                
                await page.wait_for_load_state("networkidle")

                # 2. Navegação para Envio de Títulos
                # Aqui o robô navegadora pelos menus até o formulário
                # Nota: Os seletores abaixo são baseados em padrões de sistemas de cartório
                await page.get_by_text("Enviar Títulos", exact=False).click()
                
                # 3. Preenchimento do Formulário
                # Identificamos a nota e inserimos os campos
                await page.get_by_label("CNPJ/CPF").fill(cli['cnpj'])
                await page.get_by_label("Razão Social").fill(cli['nome'])
                await page.get_by_label("Endereço").fill(cli.get('endereco', 'Não informado'))
                
                await page.get_by_label("Número do Título").fill(str(t['numero_nf']))
                await page.get_by_label("Valor").fill(str(t['valor']))
                await page.get_by_label("Data Emissão").fill(t.get('emissao', '')) # Precisaremos garantir que temos este campo
                await page.get_by_label("Data Vencimento").fill(t['vencimento'])
                
                # 4. Confirmação
                await page.get_by_role("button", name="Confirmar").click()
                
                # Verifica sucesso
                await page.wait_for_timeout(3000)
                if "sucesso" in (await page.content()).lower():
                    status_msg = "Enviado com Sucesso"
                    self._atualizar_job_status(titulo_id, "Sucesso")
                    return True, status_msg
                else:
                    status_msg = "Falha ao confirmar no portal."
                    self._atualizar_job_status(titulo_id, "Falha", status_msg)
                    return False, status_msg

            except Exception as e:
                status_msg = f"Erro na automação: {str(e)}"
                self._atualizar_job_status(titulo_id, "Erro", status_msg)
                return False, status_msg
            finally:
                if browser:
                    await browser.close()

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
            # Atualiza também o status do título
            c.execute("UPDATE titulos SET status = 'Cartório' WHERE id = ?", (titulo_id,))
            
        conn.commit()
        conn.close()

    def dict_factory(self, cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

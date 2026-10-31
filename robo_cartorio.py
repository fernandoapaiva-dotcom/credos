import asyncio
import base64
import requests
import time
from playwright.async_api import async_playwright

API_BASE_URL = "http://167.234.252.109:8001/api/cartorio"
CNPJ_EMPRESA = "54804458000122" # CNPJ da sua empresa Credos
CARTORIO_BASE_URL = "https://www.pesquisaprotesto.com.br"

def print_log(msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def get_browser_context(playwright):
    """Conecta ao Chrome/Edge aberto na porta 9222 (pelo ABRIR_EDGE_ROBO.bat)"""
    print_log("🔌 Conectando ao navegador aberto na porta 9222...")
    try:
        browser = await playwright.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=10000)
        context = browser.contexts[0]
        return context
    except Exception as e:
        raise Exception(f"Navegador não detectado. Você rodou o 'ABRIR_EDGE_ROBO.bat'? Detalhe: {e}")

async def processar_titulo(job_id, titulo, cliente):
    async with async_playwright() as p:
        context = None
        try:
            context = await get_browser_context(p)
            pages = context.pages
            page = pages[0] if pages else await context.new_page()
            
            print_log("🚀 (Re)carregando a página de Pedido de Protesto no portal CENPROT...")
            await page.goto(f"{CARTORIO_BASE_URL}/PedidoProtesto")
            await page.wait_for_load_state("networkidle")
            print_log(f"📍 URL Atual: {page.url}")

            # --- PASSO 1: DADOS DA DÍVIDA ---
            print_log("📝 Preenchendo Passo 1: Dados da Dívida...")
            try:
                await page.locator("#vs1__combobox").click()
                await page.wait_for_timeout(800)
                await page.keyboard.type("DM")
                await page.wait_for_timeout(1000)
                
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
                    print_log(f"✅ Espécie selecionada: {selecionado}")
                else:
                    await page.keyboard.press("Enter")
            except Exception as e:
                print_log(f"⚠️ Erro na Espécie: {e}")

            # 2. Número
            await page.fill("#dados_divida_numero", str(titulo['numero_nf']))

            # 3. Datas 
            emissao_raw = str(titulo.get('emissao', '')).split(' ')[0]
            vencimento_raw = str(titulo.get('vencimento', emissao_raw)).split(' ')[0]
            
            # Converte para YYYY-MM-DD
            def formata_data(data_str):
                if '/' in data_str:
                    parts = data_str.split('/')
                    if len(parts) == 3:
                        return f"{parts[2]}-{parts[1]}-{parts[0]}"
                return data_str
                
            emissao = formata_data(emissao_raw)
            vencimento = formata_data(vencimento_raw)
            
            # Proteção contra erros de digitação no sistema: a Emissão não pode ser DEPOIS do Vencimento.
            if emissao > vencimento:
                return False, f"Erro: Data de emissão ({emissao}) é maior que vencimento ({vencimento}). Por favor, edite os dados do título no painel web e clique em Reprocessar."
            
            if not emissao or emissao.strip() == "" or emissao == "None":
                return False, "Erro: Data de emissão ausente. Por favor, edite os dados do título no painel web e adicione a data de emissão."

            await page.fill("#dados_divida_dt_emissao", emissao)
            await page.fill("#dados_divida_dt_vencimento", vencimento) 
            
            # 4. Valor
            valor_str = f"{float(titulo['valor']):.2f}".replace('.', ',')
            await page.fill("#dados_divida_valor_titulo", valor_str)
            await page.fill("#dados_divida_valor_protestado", valor_str)
            
            print_log("   👉 Avançando para o Passo 2...")
            clicou = await clicar_prosseguir(page)
            if not clicou:
                return False, "Não foi possível avançar para o Passo 2."

            # --- PASSO 2: CREDOR ---
            print_log("📝 Passo 2: Dados do Credor (Apenas Confirmar)...")
            await page.wait_for_selector("#documento_cedente", state="visible", timeout=10000)
            print_log("   👉 Avançando para o Passo 3...")
            clicou = await clicar_prosseguir(page)
            if not clicou:
                return False, "Não foi possível avançar para o Passo 3."

            # --- PASSO 3: DEVEDOR ---
            print_log("📝 Preenchendo Passo 3: Dados do Devedor...")
            await page.wait_for_selector("#documento_devedor", state="visible", timeout=10000)
            
            # CNPJ do devedor
            if cliente.get('cnpj'):
                cnpj = str(cliente['cnpj']).replace('.', '').replace('/', '').replace('-', '').strip()
                await page.locator("#documento_devedor").click()
                await page.keyboard.type(cnpj)
            
            await page.fill("#nome_devedor", str(titulo['pagador'])[:100])
            
            if cliente.get('email'):
                await page.fill("#email_devedor", str(cliente['email']))
                
            telefone = cliente.get('telefone') or cliente.get('whatsapp')
            if telefone:
                await page.fill("#celular_devedor", str(telefone))
                
            endereco = str(cliente.get('endereco', ''))
            cep = ""
            import re
            match = re.search(r'\b\d{5}-?\d{3}\b', endereco)
            if match:
                cep = match.group()
            
            if cep:
                cep = cep.replace('-', '').replace('.', '').strip()
                await page.locator("#devedor_cep").click()
                await page.keyboard.type(cep)
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(3000)
                
            print_log("   👉 Avançando para o Passo 4 (Resumo)...")
            clicou = await clicar_prosseguir(page)
            if not clicou:
                return False, "Não foi possível avançar para o Passo 4."

            # --- PASSO 4: RESUMO E ANEXOS ---
            print_log("📊 Passo 4: Conferindo o Resumo e Anexos...")
            await page.wait_for_timeout(2000)
            
            if titulo.get('pdf_base64'):
                print_log("📎 PDF da NF encontrado pela IA. Iniciando anexo...")
                import tempfile
                import os
                import base64
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(base64.b64decode(titulo['pdf_base64']))
                    tmp_path = tmp.name
                
                try:
                    # Tenta clicar em "Sim" ou similar para abrir o campo de upload, se houver
                    for lbl_text in ["Sim", "Enviar", "Anexar"]:
                        lbl = page.locator(f"label:has-text('{lbl_text}')").first
                        if await lbl.is_visible():
                            await lbl.click()
                            await page.wait_for_timeout(500)
                            break
                            
                    input_file = page.locator("input[type='file']").first
                    if await input_file.is_visible(timeout=5000) or await input_file.is_attached():
                        await input_file.set_input_files(tmp_path)
                        print_log("✅ PDF da NF anexado com sucesso!")
                    else:
                        print_log("⚠️ Campo de anexo não encontrado na tela.")
                except Exception as e:
                    print_log(f"⚠️ Aviso: Falha ao anexar PDF automaticamente: {e}")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except: pass
            else:
                print_log("⚠️ Nenhum PDF da nota fiscal encontrado no banco para este título.")
            
            print_log("✅ Simulação Concluída. O envio real está desativado no código para testes.")
            return True, "Título simulado com sucesso (sem envio real)."
            
            # Passo 5: Envio Real — Clicar em "Solicitar o Protesto" (DESATIVADO)
            # print_log("🚀 Passo 5: Solicitando Protesto Oficial...")

        except Exception as e:
            err_msg = f"Erro na automação do Chrome: {str(e)}"
            print_log(f"❌ {err_msg}")
            return False, err_msg
        finally:
            if context:
                try:
                    await context.close()
                except:
                    pass

async def clicar_prosseguir(page):
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

def informar_resultado(job_id, status, log_erro=""):
    print_log(f"📡 Informando nuvem: Job {job_id} -> {status}")
    try:
        url = f"{API_BASE_URL}/job/{CNPJ_EMPRESA}/{job_id}/status"
        res = requests.post(url, json={"status": status, "log_erro": log_erro})
        if res.status_code == 200:
            print_log("✅ Nuvem atualizada com sucesso.")
        else:
            print_log(f"⚠️ Erro ao atualizar nuvem: {res.text}")
    except Exception as e:
        print_log(f"⚠️ Erro de rede ao contatar a nuvem: {e}")

async def main_loop():
    print_log("=========================================")
    print_log("🤖 Robô Local de Cartório Iniciado")
    print_log("Certifique-se de que o navegador está aberto via ABRIR_CHROME_ROBO.bat")
    print_log("=========================================\n")
    
    while True:
        try:
            url = f"{API_BASE_URL}/next-job/{CNPJ_EMPRESA}"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                job = data.get("job")
                
                if job:
                    print_log(f"🎯 NOVO TÍTULO ENCONTRADO: NF {job['numero_nf']} - R$ {job['valor']}")
                    print_log(f"   Cliente: {job['cliente_nome']}")
                    
                    ok, msg = await processar_titulo(
                        job_id=job['job_id'], 
                        titulo=job, 
                        cliente=job
                    )
                    
                    if ok:
                        informar_resultado(job['job_id'], "Sucesso", msg)
                    else:
                        informar_resultado(job['job_id'], "Erro", msg)
                else:
                    # Nenhum job pendente
                    print_log("💤 Fila vazia. Aguardando novos títulos da nuvem...")
            else:
                print_log(f"⚠️ Erro na API: HTTP {res.status_code}")
                
        except requests.exceptions.RequestException as e:
            print_log(f"⚠️ Sem conexão com a nuvem (Verificando novamente em breve).")
        except Exception as e:
            print_log(f"❌ Erro fatal no loop: {e}")
            
        time.sleep(15) # Verifica a cada 15 segundos

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print_log("🛑 Robô Local encerrado pelo usuário.")

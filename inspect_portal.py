import asyncio
import os
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        try:
            print("🔌 Conectando ao Chrome/Edge (Porta 9222)...")
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0]
            page = context.pages[0]
            print(f"📍 URL Atual: {page.url}")

            print("\n🔍 PROCURANDO INPUTS E SEUS IDs NO PASSO ATUAL...")
            elements = await page.query_selector_all("input, select, textarea, label, div[role='combobox']")
            for el in elements:
                tag = await el.evaluate("el => el.tagName")
                text = await el.evaluate("el => el.innerText || el.placeholder || ''")
                id_attr = await el.evaluate("el => el.id")
                name_attr = await el.evaluate("el => el.name")
                is_visible = await el.is_visible()
                if is_visible or id_attr:
                    print(f"[{tag}] ID: {id_attr} | Name: {name_attr} | Visible: {is_visible} | Text: {text.strip()[:40]}")

            await browser.close()
        except Exception as e:
            print(f"❌ Erro: {e}")

if __name__ == "__main__":
    asyncio.run(inspect())

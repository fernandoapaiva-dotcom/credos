import pdfplumber
import pandas as pd
import re
import os
import json

def _buscar_chave_gemini(cnpj=None):
    if cnpj:
        try:
            from src.database import carregar_configuracoes_db
            cfg = carregar_configuracoes_db(cnpj)
            if cfg and cfg.get('gemini_api_key'):
                return cfg.get('gemini_api_key')
        except Exception:
            pass

    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key

    # Busca em qualquer empresa cadastrada no banco de dados
    try:
        from src.database import DATABASE_DIR, DB_PREFIX
        import sqlite3
        if os.path.exists(DATABASE_DIR):
            for fname in os.listdir(DATABASE_DIR):
                if fname.endswith('.db') and (fname.startswith(DB_PREFIX) or fname.replace('.db', '').isdigit()):
                    try:
                        c_path = os.path.join(DATABASE_DIR, fname)
                        with sqlite3.connect(c_path) as c_db:
                            cur = c_db.cursor()
                            cur.execute("SELECT gemini_api_key FROM config WHERE gemini_api_key IS NOT NULL AND gemini_api_key != '' LIMIT 1")
                            row = cur.fetchone()
                            if row and row[0]:
                                return row[0]
                    except Exception:
                        continue
    except Exception:
        pass

    return None

def _extrair_tabela_gemini(caminho_pdf, api_key):
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        with open(caminho_pdf, "rb") as f:
            pdf_bytes = f.read()

        prompt = """
Você é um extrator de dados financeiros especializado em relatórios bancários em PDF.
Extraia a tabela completa com todas as linhas de boletos/títulos deste documento.
Preserve os nomes exatos das colunas da tabela conforme aparecem no cabeçalho (ex: Vencimento, Carteira, Nosso Número, Seu Número, Valor(R$), Pagador, etc).
Retorne estritamente um JSON no formato:
{
  "colunas": ["Vencimento", "Carteira", "Nosso Número", "Seu Número", "Valor(R$)", "Pagador", "Boleto em DDA", "Situação"],
  "linhas": [
    ["15/05/2026", "109", "000213567", "1371", "1.127,05", "HIPER METALURGICA LTDA", "SIM", "VENCIDO"],
    ...
  ]
}
Não inclua nenhum texto, explicação ou markdown fora do JSON.
"""
        models = ['gemini-2.5-flash', 'gemini-2.0-flash-lite', 'gemini-flash-latest']
        for model in models:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        prompt
                    ]
                )
                txt = resp.text.strip()
                if txt.startswith("```"):
                    txt = txt.split("```")[1]
                    if txt.startswith("json"):
                        txt = txt[4:].strip()
                data = json.loads(txt)
                if isinstance(data, dict) and "colunas" in data and "linhas" in data:
                    if len(data["linhas"]) > 0:
                        df = pd.DataFrame(data["linhas"], columns=data["colunas"])
                        return df
            except Exception as ex_m:
                print(f"[Gemini Extractor] Falha no modelo {model}: {ex_m}")
                continue
    except Exception as e:
        print(f"[Gemini Extractor] Erro ao processar via IA: {e}")

    return None

def ler_pdf_bruto(caminho_pdf, cnpj=None, gemini_api_key=None):
    """
    Lê o PDF e tenta transformar todas as tabelas encontradas em um único DataFrame Pandas.
    Tenta primeiro via pdfplumber (rápido e local).
    Se o PDF não contiver texto embutido (ex: fontes convertidas em curvas vetoriais ou imagem/scanner),
    utiliza fallback com a IA Gemini (Vision/Multimodal) para extração estruturada de alta precisão.
    """
    dados_totais = []
    
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for page in pdf.pages:
                tabelas = page.extract_tables()
                for tabela in tabelas:
                    for linha in tabela:
                        linha_limpa = [str(celula).replace('\n', ' ').strip() if celula else '' for celula in linha]
                        if any(linha_limpa):
                            dados_totais.append(linha_limpa)
    except Exception as e:
        print(f"[Extractor] Aviso ao ler tabelas com pdfplumber: {e}")

    if dados_totais:
        df = pd.DataFrame(dados_totais)
        new_header = df.iloc[0] 
        df = df[1:] 
        df.columns = new_header
        if len(df) > 0 and len(df.columns) > 1:
            return df

    # Se pdfplumber não encontrou dados com texto, tenta o fallback com Gemini
    print("[Extractor] PDF sem texto editável via pdfplumber. Acionando fallback Gemini Multimodal...")
    chave = gemini_api_key or _buscar_chave_gemini(cnpj)
    if chave:
        df_ia = _extrair_tabela_gemini(caminho_pdf, chave)
        if df_ia is not None and len(df_ia) > 0:
            return df_ia

    return None

def _normalizar_texto(txt):
    if not txt:
        return ""
    txt = str(txt).lower().strip()
    substituicoes = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ü': 'u',
        'ç': 'c',
        '$': '', '(': '', ')': '', '-': '', '_': '', ' ': '', '/': '', '.': ''
    }
    for k, v in substituicoes.items():
        txt = txt.replace(k, v)
    return txt

def _obter_valor_celula(row, nome_coluna_alvo):
    if not nome_coluna_alvo:
        return ""
    if nome_coluna_alvo in row:
        return row[nome_coluna_alvo]
    
    alvo_lower = str(nome_coluna_alvo).strip().lower()
    for col in row.index:
        if str(col).strip().lower() == alvo_lower:
            return row[col]
            
    alvo_norm = _normalizar_texto(nome_coluna_alvo)
    for col in row.index:
        if _normalizar_texto(col) == alvo_norm:
            return row[col]
            
    for col in row.index:
        col_norm = _normalizar_texto(col)
        if alvo_norm in col_norm or col_norm in alvo_norm:
            return row[col]
            
    return ""

def processar_dataframe_mapeado(df, mapa_colunas):
    """
    Recebe o DataFrame bruto e o dicionário de mapeamento:
    mapa_colunas = {
        'vencimento': 'Nome da Coluna A',
        'numero': 'Nome da Coluna B',
        'valor': 'Nome da Coluna C',
        'pagador': 'Nome da Coluna D'
    }
    """
    resultados = []
    
    col_venc = mapa_colunas.get('vencimento')
    col_num = mapa_colunas.get('numero')
    col_val = mapa_colunas.get('valor')
    col_pag = mapa_colunas.get('pagador')

    for index, row in df.iterrows():
        try:
            val_venc = _obter_valor_celula(row, col_venc)
            val_num = _obter_valor_celula(row, col_num)
            val_val = _obter_valor_celula(row, col_val)
            val_pag = _obter_valor_celula(row, col_pag)

            raw_venc = str(val_venc).strip()
            raw_num = str(val_num).strip()
            raw_val = str(val_val).strip()
            raw_pag = str(val_pag).strip()

            # Pula linhas que parecem cabeçalho repetido
            if "vencimento" in raw_venc.lower() or "valor" in raw_val.lower() or "pagador" in raw_pag.lower():
                continue

            if not raw_pag or not raw_val:
                continue

            # Tratamento de Valor (R$ 1.000,00 -> 1000.00 ou 1000.00 direto)
            if isinstance(val_val, (int, float)):
                valor_float = float(val_val)
            else:
                limpo = raw_val.replace('R$', '').replace(' ', '').strip()
                if ',' in limpo:
                    limpo = limpo.replace('.', '').replace(',', '.')
                try:
                    valor_float = float(limpo)
                except:
                    continue

            # Normalização de número da NF / Boleto (ex: se vier float '1371.0' -> '1371')
            if raw_num.endswith('.0') and raw_num[:-2].isdigit():
                raw_num = raw_num[:-2]

            resultados.append({
                'vencimento': raw_venc,
                'numero': raw_num,
                'valor': valor_float,
                'pagador': raw_pag.upper(), # Nome em maiúsculo
                'arquivo_origem': 'Upload Manual'
            })
            
        except Exception as e:
            continue
            
    return resultados
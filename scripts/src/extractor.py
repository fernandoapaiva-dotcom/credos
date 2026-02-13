import pdfplumber
import pandas as pd
import re

def ler_pdf_bruto(caminho_pdf):
    """
    Lê o PDF e tenta transformar todas as tabelas encontradas em um único DataFrame Pandas.
    Retorna o DataFrame para que o usuário faça o mapeamento das colunas.
    """
    dados_totais = []
    
    with pdfplumber.open(caminho_pdf) as pdf:
        for page in pdf.pages:
            # Tenta extrair tabelas da página
            tabelas = page.extract_tables()
            
            for tabela in tabelas:
                # Remove linhas vazias ou cabeçalhos repetidos no meio
                for linha in tabela:
                    # Limpeza básica: remove None e quebras de linha
                    linha_limpa = [str(celula).replace('\n', ' ').strip() if celula else '' for celula in linha]
                    
                    # Ignora linhas totalmente vazias
                    if any(linha_limpa):
                        dados_totais.append(linha_limpa)
    
    if not dados_totais:
        return None

    # Cria DataFrame genérico (Coluna 0, Coluna 1, etc...)
    # Assumimos que a primeira linha com dados relevantes pode ser o cabeçalho,
    # mas retornamos tudo para o usuário decidir.
    df = pd.DataFrame(dados_totais)
    
    # Tenta promover a primeira linha a cabeçalho se parecer texto
    new_header = df.iloc[0] 
    df = df[1:] 
    df.columns = new_header 
    
    return df

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
    
    for index, row in df.iterrows():
        try:
            # Extrai os dados baseado no nome da coluna escolhida pelo usuário
            col_venc = mapa_colunas.get('vencimento')
            col_num = mapa_colunas.get('numero')
            col_val = mapa_colunas.get('valor')
            col_pag = mapa_colunas.get('pagador')

            raw_venc = str(row[col_venc])
            raw_num = str(row[col_num])
            raw_val = str(row[col_val])
            raw_pag = str(row[col_pag])

            # Pula linhas que parecem cabeçalho repetido
            if "Vencimento" in raw_venc or "Valor" in raw_val:
                continue

            # Tratamento de Valor (R$ 1.000,00 -> 1000.00)
            valor_limpo = raw_val.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
            try:
                valor_float = float(valor_limpo)
            except:
                continue # Se não conseguiu converter valor, ignora a linha (lixo)

            resultados.append({
                'vencimento': raw_venc,
                'numero': raw_num,
                'valor': valor_float,
                'pagador': raw_pag.upper(), # Nome em maiúsculo
                'arquivo_origem': 'Upload Manual'
            })
            
        except Exception as e:
            # Ignora erros de linha a linha para não travar tudo
            continue
            
    return resultados
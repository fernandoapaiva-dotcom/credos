import re
import os
import pdfplumber
import xml.etree.ElementTree as ET

class FiscalParser:
    def __init__(self):
        pass

    def extrair_dados(self, fpath):
        if not os.path.exists(fpath): return None
        ext = fpath.lower().split('.')[-1]
        if ext == 'xml': return self._parse_xml(fpath)
        elif ext == 'pdf': return self._parse_pdf(fpath)
        return None

    def _parse_xml(self, fpath):
        try:
            tree = ET.parse(fpath)
            root = tree.getroot()
            # Valor Total (vNF)
            v_nf = None
            v_nf_elem = root.find('.//{*}vNF')
            if v_nf_elem is not None: v_nf = float(v_nf_elem.text)
            
            # Data de Emissão
            emissao = None
            dh_emi = root.find('.//{*}dhEmi')
            if dh_emi is not None:
                emissao = dh_emi.text.split('T')[0]
            else:
                d_emi = root.find('.//{*}dEmi')
                if d_emi is not None: emissao = d_emi.text
            
            if emissao and '-' in emissao:
                p = emissao.split('-')
                emissao = f"{p[2]}/{p[1]}/{p[0]}"
            return {'valor': v_nf, 'emissao': emissao, 'tipo': 'NF-E'}
        except Exception as e:
            return None

    def _parse_pdf(self, fpath):
        try:
            with pdfplumber.open(fpath) as pdf:
                texto_total = ""
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: texto_total += t + "\n"
                
                texto_upper = texto_total.upper()
                
                if any(x in texto_upper for x in ["VALOR TOTAL DA NOTA", "NFS-E", "PREFEITURA", "TOMADOR DE SERVIÇO", "NOTA FISCAL DE SERVIÇOS"]):
                    return self._parse_nfs_pdf(texto_total)
                elif any(x in texto_upper for x in ["LINHA DIGITÁVEL", "PAGÁVEL EM", "RECIBO DO PAGADOR", "BOLETO"]):
                    return self._parse_boleto_pdf(texto_total)
                elif "DANFE" in texto_upper:
                    return self._parse_nfe_pdf(texto_total)
                else:
                    # Tenta extrair qualquer valor monetário como fallback
                    return self._parse_generic_pdf(texto_total)
        except Exception as e:
            pass
        return None

    def _parse_nfs_pdf(self, texto):
        dados = {'valor': None, 'emissao': None, 'tipo': 'NF-S'}
        datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
        if datas: dados['emissao'] = datas[0]
            
        # Regex aprimorada para valores
        patterns = [
            r'VALOR TOTAL DA NOTA.*?R\$\s*([\d\.,]+)',
            r'VALOR TOTAL DOS SERVIÇOS.*?([\d\.,]+)',
            r'VALOR LÍQUIDO.*?([\d\.,]+)',
            r'TOTAL DA NOTA.*?([\d\.,]+)',
            r'VALOR DO SERVIÇO.*?([\d\.,]+)',
            r'Vl\. Líquido.*?R\$\s*([\d\.,]+)',
            r'Líquido a Receber.*?([\d\.,]+)'
        ]
        for p in patterns:
            match = re.search(p, texto, re.IGNORECASE | re.DOTALL)
            if match:
                val_str = match.group(1).rstrip('.').replace('.', '').replace(',', '.')
                try:
                    v = float(val_str)
                    if v < 1000000: # Sanity check
                        dados['valor'] = v
                        break
                except: continue
        return dados

    def _parse_nfe_pdf(self, texto):
        dados = {'valor': None, 'emissao': None, 'tipo': 'NF-E'}
        datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
        if datas: dados['emissao'] = datas[0]
        match = re.search(r'VALOR TOTAL DA NOTA\s+([\d\.,]+)', texto)
        if match:
            val_str = match.group(1).rstrip('.').replace('.', '').replace(',', '.')
            try: dados['valor'] = float(val_str)
            except: pass
        return dados

    def _parse_boleto_pdf(self, texto):
        dados = {'valor': None, 'emissao': None, 'tipo': 'BOLETO'}
        match = re.search(r'VALOR DO DOCUMENTO\s+([\d\.,]+)', texto, re.IGNORECASE)
        if not match: match = re.search(r'R\$\s*([\d\.,]+)', texto)
        if match:
            val_str = match.group(1).rstrip('.').replace('.', '').replace(',', '.')
            try:
                v = float(val_str)
                if v < 1000000: dados['valor'] = v
            except: pass
        match_dt = re.search(r'DATA (?:DO )?PROCESSAMENTO\s+(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
        if match_dt: dados['emissao'] = match_dt.group(1)
        else:
            datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
            if len(datas) >= 1: dados['emissao'] = datas[0]
        return dados

    def _parse_generic_pdf(self, texto):
        # Fallback para PDFs não identificados
        datas = re.findall(r'(\d{2}/\d{2}/\d{4})', texto)
        emissao = datas[0] if datas else None
        # Busca por algo que pareça um valor monetário no final ou perto de "TOTAL"
        match = re.search(r'(?:TOTAL|VALOR).*?([\d\.,]+)', texto, re.IGNORECASE | re.DOTALL)
        valor = None
        if match:
            try:
                val_str = match.group(1).rstrip('.').replace('.', '').replace(',', '.')
                valor = float(val_str)
            except: pass
        return {'valor': valor, 'emissao': emissao, 'tipo': 'OUTROS'}

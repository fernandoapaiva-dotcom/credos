#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/app')
from src.manager import Manager

try:
    m = Manager('11504286000169')
    filtros = {
        'tipo': 'Cobrados',
        'data_inicio': '2026-04-01',
        'data_fim': '2026-04-09',
        'cliente': None
    }
    r = m.gerar_relatorio_pdf_cobrancas(filtros)
    print('OK:', r)
except Exception as e:
    import traceback
    print('ERRO:', str(e))
    traceback.print_exc()

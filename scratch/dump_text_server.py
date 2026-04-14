import pdfplumber
import os

files = [
    '/app/data/repository/diagnostico_1914_2-382-boletos.pdf',
    '/app/data/repository/diagnostico_1914_002SE003000000382.pdf'
]

with open('/app/dump_text_dauto.txt', 'w', encoding='utf-8') as out:
    for f in files:
        out.write(f"\n--- FILE: {f} ---\n")
        if os.path.exists(f):
            with pdfplumber.open(f) as pdf:
                for page in pdf.pages:
                    out.write(page.extract_text() or "[NO TEXT]")
        else:
            out.write("[NOT FOUND]")

with open(r'c:\Antigravity\credos\src\manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The new function ends with:
# "        return filepath\n"
# followed immediately by "\n\n" then the old dead code
# We want to keep everything up to and including the LAST occurrence of
# "        return filepath\n" that belongs to gerar_relatorio_pdf_cobrancas.
# The new function's return filepath is followed by a blank line then
# "        \n        conn = conectar" (old dead code)

import re

# Find position of the dead code marker
dead_marker = "        \n        conn = conectar(self.cnpj_empresa)\n        params = []"
idx = content.find(dead_marker)

if idx != -1:
    # Trim from just before the dead_marker to end of file
    trimmed = content[:idx].rstrip() + '\n'
    with open(r'c:\Antigravity\credos\src\manager.py', 'w', encoding='utf-8') as f:
        f.write(trimmed)
    lines = trimmed.count('\n')
    print(f"SUCCESS: Trimmed to {lines} lines")
    print("Last 10 lines:")
    for l in trimmed.split('\n')[-10:]:
        print(repr(l))
else:
    print("Marker not found, trying alternate...")
    # Try different newline
    dead_marker2 = "        conn = conectar(self.cnpj_empresa)\r\n        params = []"
    idx2 = content.find(dead_marker2)
    print(f"Alternate idx: {idx2}")
    # Show context around likely location
    # Look for second 'return filepath'
    positions = [m.start() for m in re.finditer(r'        return filepath', content)]
    print(f"'return filepath' positions: {positions}")
    if len(positions) >= 2:
        cut_at = positions[1] + len('        return filepath') + 2  # +2 for \r\n
        trimmed = content[:cut_at]
        with open(r'c:\Antigravity\credos\src\manager.py', 'w', encoding='utf-8') as f:
            f.write(trimmed)
        print(f"Cut after second return filepath at position {cut_at}")

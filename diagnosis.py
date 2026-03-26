# diagnostico.py — cole na raiz do repositório e execute
import sys
sys.path.insert(0, '.')
import pdfplumber
from pipeline.parser import extract_text, clean_text, tokenize

pdf = "corpus/pdf-lei8429.pdf"

# --- Diagnóstico 1: linhas limpas após o Art. 9º ---
raw = extract_text(pdf)
lines = clean_text(raw)
print(f"Total de linhas limpas: {len(lines)}\n")

# Encontra o índice do Art. 9º e mostra as 30 linhas seguintes
for i, line in enumerate(lines):
    if "Art. 9" in line:
        print(f"Art. 9º encontrado na posição [{i}]")
        print("--- 30 linhas seguintes ---")
        for j, l in enumerate(lines[i:i+30], start=i):
            print(f"[{j:03d}] {l[:100]}")
        break

print()

# --- Diagnóstico 2: tokens gerados ---
tokens = tokenize(lines)
print(f"\nTotal de tokens: {len(tokens)}")
print("--- Últimos 10 tokens ---")
for t in tokens[-10:]:
    print(f"  {t.tipo:<18} | {t.rotulo!r:<20} | {t.texto[:60]!r}")
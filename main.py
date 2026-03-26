"""
main.py — CLI unificada do pipeline SPUK-LEGIS

Uso:
    python main.py parse   <pdf>        --output <json>
    python main.py analyze <cards_json> --questoes <dataset_json> --output <fingerprint_json>
    python main.py generate <cards_json> --fingerprint <fingerprint_json> --output <full_json>
    python main.py export  <full_json>  --corpus <sigla> --output <migration.sql>
"""

import argparse
import json
import sys
from pathlib import Path


def cmd_parse(args):
    from pipeline.parser import parse

    resultado = parse(args.pdf)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    total = len(resultado["cards"])
    print(f"✓ {total} cards gerados → {args.output}")


def cmd_analyze(args):
    # Implementado na Etapa 3
    print("[analyze] Ainda não implementado. Execute após a revisão humana do JSON de cards.")
    sys.exit(1)


def cmd_generate(args):
    # Implementado na Etapa 4
    print("[generate] Ainda não implementado. Execute após o analyzer.")
    sys.exit(1)


def cmd_export(args):
    # Implementado na Etapa 6
    print("[export] Ainda não implementado. Execute após a aprovação no dashboard.")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Pipeline SPUK-LEGIS — geração de cards de legislação",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- parse ---
    p_parse = subparsers.add_parser("parse", help="Etapa 1: PDF da lei → JSON de cards")
    p_parse.add_argument("pdf", help="Caminho para o PDF (ex: corpus/lei_8429.pdf)")
    p_parse.add_argument("--output", "-o", required=True, help="JSON de saída")

    # --- analyze ---
    p_analyze = subparsers.add_parser("analyze", help="Etapa 3: questões → fingerprint de armadilhas")
    p_analyze.add_argument("cards_json", help="JSON de cards (saída do parse)")
    p_analyze.add_argument("--questoes", required=True, help="Dataset JSON de questões CEBRASPE")
    p_analyze.add_argument("--output", "-o", required=True, help="JSON de fingerprint de saída")

    # --- generate ---
    p_generate = subparsers.add_parser("generate", help="Etapa 4: gera variantes com armadilhas")
    p_generate.add_argument("cards_json", help="JSON de cards revisado")
    p_generate.add_argument("--fingerprint", required=True, help="JSON de fingerprint")
    p_generate.add_argument("--output", "-o", required=True, help="JSON completo de saída")

    # --- export ---
    p_export = subparsers.add_parser("export", help="Etapa 6: JSON aprovado → SQL Flyway")
    p_export.add_argument("full_json", help="JSON completo revisado e aprovado")
    p_export.add_argument("--corpus", required=True, help="Sigla do corpus (ex: LEI8429)")
    p_export.add_argument("--output", "-o", required=True, help="Arquivo SQL de saída")

    args = parser.parse_args()

    dispatch = {
        "parse":    cmd_parse,
        "analyze":  cmd_analyze,
        "generate": cmd_generate,
        "export":   cmd_export,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
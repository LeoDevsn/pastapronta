from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import History, Monitor, export_csv, human_size, scan


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog="pastapronta", description="Organize arquivos locais com prévia e histórico reversível.")
    cli.add_argument("--state-dir", type=Path, help="Pasta alternativa para o histórico")
    sub = cli.add_subparsers(dest="command")
    sub.add_parser("gui", help="Abre a interface gráfica (padrão)")
    for command, help_text in (("scan", "Mostra a prévia, sem mover arquivos"),
                               ("organize", "Analisa e organiza arquivos"),
                               ("watch", "Monitora enquanto este processo estiver aberto")):
        cmd = sub.add_parser(command, help=help_text)
        cmd.add_argument("folder", type=Path)
        cmd.add_argument("--recursive", action="store_true", help="Inclui subpastas")
        cmd.add_argument("--by-month", action="store_true", help="Separa por ano/mês de modificação")
        if command in {"scan", "organize"}:
            cmd.add_argument("--csv", type=Path, help="Exporta a prévia para um CSV novo")
        if command == "organize":
            cmd.add_argument("--apply", action="store_true", help="Confirma a movimentação; sem isso é só prévia")
        if command == "watch":
            cmd.add_argument("--apply", action="store_true", required=True,
                             help="Autoriza a organização contínua")
            cmd.add_argument("--interval", type=float, default=5)
            cmd.add_argument("--settle", type=float, default=10,
                             help="Idade mínima em segundos; também exige duas verificações estáveis")
    sub.add_parser("history", help="Lista operações locais em JSON")
    undo = sub.add_parser("undo", help="Desfaz uma operação sem sobrescrever arquivos")
    undo.add_argument("batch_id")
    undo.add_argument("--apply", action="store_true", required=True)
    sub.add_parser("demo", help="Cria arquivos fictícios e abre a interface")
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command in {None, "gui", "demo"}:
            from .gui import launch
            from .demo import create_demo
            launch(args.state_dir, create_demo() if args.command == "demo" else None)
            return 0
        history = History(args.state_dir)
        if args.command == "history":
            print(json.dumps(history.batches(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "undo":
            result = history.undo(args.batch_id)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["errors"] else 0
        if args.command == "watch":
            # Valida pasta e opções antes de entrar no loop.
            scan(args.folder, args.recursive, args.by_month)
            monitor = Monitor(args.folder, history, args.interval, args.settle,
                              args.recursive, args.by_month, notify=print)
            print(f"Monitorando {args.folder.resolve()}. Ctrl+C para parar. Nenhum arquivo será excluído.", flush=True)
            try:
                monitor.run()
            except KeyboardInterrupt:
                monitor.stop()
                print("\nMonitor encerrado.")
            return 0
        plan = scan(args.folder, args.recursive, args.by_month)
        print(f"{len(plan.items)} arquivo(s) · {human_size(plan.total_bytes)} · {plan.duplicates} cópia(s) duplicada(s)")
        for item in plan.items:
            duplicate = f" [duplicado de {item.duplicate_of}]" if item.duplicate_of else ""
            print(f"  {item.source.relative_to(plan.root)} -> {item.destination.relative_to(plan.root)}{duplicate}")
        for warning in plan.warnings:
            print(f"AVISO: {warning}", file=sys.stderr)
        print(f"Ignorados: {plan.skipped}. Duplicados são mantidos.")
        if args.csv:
            export_csv(plan, args.csv)
            print(f"Relatório salvo: {args.csv}")
        if args.command == "organize" and args.apply:
            result = history.execute(plan)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["errors"] or plan.warnings else 0
        print("Somente prévia. Para mover: organize PASTA --apply")
        return 1 if plan.warnings else 0
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

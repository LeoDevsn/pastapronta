"""Preferências locais. Não inicia monitoramento automaticamente."""

import json
from pathlib import Path


def load(directory: Path) -> dict:
    try:
        value = json.loads((directory / "preferencias.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save(directory: Path, folder: str, recursive: bool, by_month: bool) -> None:
    target = directory / "preferencias.json"
    temporary = directory / "preferencias.tmp"
    temporary.write_text(json.dumps({"folder": folder, "recursive": recursive,
                                     "by_month": by_month}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(target)

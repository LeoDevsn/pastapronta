"""Gera um ZIP de código-fonte sem histórico, caches ou arquivos de teste gerados."""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pasta_pronta import __version__


def main():
    target = ROOT / "dist" / f"PastaPronta-{__version__}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in ("README.md", "LICENSE", "pyproject.toml", "iniciar.pyw", ".gitignore")]
    for folder in ("pasta_pronta", "tests", "scripts"):
        files.extend(path for path in (ROOT / folder).rglob("*.py") if "__pycache__" not in path.parts)
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, Path("PastaPronta") / path.relative_to(ROOT))
    print(target)


if __name__ == "__main__":
    main()

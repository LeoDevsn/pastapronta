"""Motor independente da interface. Usa apenas a biblioteca padrão do Python."""

from __future__ import annotations

import csv
import hashlib
import os
import shutil
import sqlite3
import stat
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

OUTPUT = "Organizados"
CATEGORIES = {
    "Documentos": ".pdf .doc .docx .odt .txt .rtf .md .epub",
    "Planilhas": ".xls .xlsx .csv .tsv .ods",
    "Imagens": ".jpg .jpeg .png .gif .webp .svg .heic .bmp .tiff .ico",
    "Vídeos": ".mp4 .mov .mkv .avi .webm .m4v",
    "Áudios": ".mp3 .wav .flac .aac .ogg .m4a",
    "Apresentações": ".ppt .pptx .odp .key",
    "Compactados": ".zip .rar .7z .tar .gz .bz2 .xz",
    "Instaladores": ".exe .msi .msix .dmg .deb .rpm .apk",
    "Código": ".py .js .ts .tsx .jsx .html .css .json .yaml .yml .xml .sql .sh .ps1",
}
EXTENSIONS = {ext: name for name, extensions in CATEGORIES.items() for ext in extensions.split()}
TEMP_EXTENSIONS = {".part", ".crdownload", ".download", ".tmp", ".partial"}
_thread_lock = threading.Lock()


def state_directory() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "PastaPronta"


def fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
        value /= 1024
    return ""


def _key(path: Path) -> str:
    return os.path.normcase(str(path))


def _regular(path: Path) -> bool:
    # Junctions e links nunca devem ser atravessados.
    return not path.is_symlink() and not path.is_junction() and stat.S_ISREG(path.lstat().st_mode)


def _safe_parent(path: Path, root: Path) -> None:
    if not path.is_relative_to(root):
        raise ValueError("Caminho fora da pasta selecionada.")
    for parent in [path.parent, *path.parent.parents]:
        if parent.is_symlink() or parent.is_junction():
            raise ValueError(f"Link ou junção ignorado: {parent}")
        if parent == root:
            break


@dataclass(frozen=True)
class Item:
    source: Path
    destination: Path
    category: str
    size: int
    mtime_ns: int
    sha256: str
    duplicate_of: str = ""


@dataclass
class Plan:
    root: Path
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: int = 0

    @property
    def duplicates(self) -> int:
        return sum(bool(item.duplicate_of) for item in self.items)

    @property
    def total_bytes(self) -> int:
        return sum(item.size for item in self.items)

    @property
    def categories(self) -> dict[str, int]:
        return dict(Counter(item.category for item in self.items))


def scan(root: Path | str, recursive: bool = False, by_month: bool = False,
         min_age: float = 0, progress: Callable[[str], None] | None = None) -> Plan:
    """Somente leitura. Duplicados são identificados dentro desta análise."""
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Selecione uma pasta existente.")
    if root == Path(root.anchor):
        raise ValueError("Escolha uma pasta específica, não a raiz do disco.")
    plan = Plan(root)
    files: list[Path] = []
    def walk_error(error: OSError) -> None:
        plan.warnings.append(str(error))
    for folder, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        directory = Path(folder)
        dirs[:] = sorted(d for d in dirs if d != OUTPUT and not d.startswith(".")
                         and not (directory / d).is_symlink() and not (directory / d).is_junction())
        files.extend(directory / name for name in sorted(names))
        if not recursive:
            break
    reserved: set[str] = set()
    hashes: dict[str, str] = {}
    for source in files:
        try:
            if source.name.startswith((".", "~$")) or source.suffix.lower() in TEMP_EXTENSIONS:
                plan.skipped += 1
                continue
            if not _regular(source):
                plan.skipped += 1
                continue
            before = source.stat()
            if min_age > 0 and time.time() - before.st_mtime < min_age:
                plan.skipped += 1
                continue
            if progress:
                progress(source.name)
            digest = fingerprint(source)
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                plan.warnings.append(f"Arquivo em alteração: {source.name}")
                continue
            category = EXTENSIONS.get(source.suffix.lower(), "Outros")
            target_folder = root / OUTPUT / category
            if by_month:
                target_folder /= datetime.fromtimestamp(before.st_mtime).strftime("%Y/%m")
            destination = target_folder / source.name
            number = 2
            while destination.exists() or destination.is_symlink() or _key(destination) in reserved:
                destination = target_folder / f"{source.stem} ({number}){source.suffix}"
                number += 1
            _safe_parent(destination, root)
            reserved.add(_key(destination))
            duplicate_of = hashes.get(digest, "")
            hashes.setdefault(digest, str(source.relative_to(root)))
            plan.items.append(Item(source, destination, category, before.st_size,
                                   before.st_mtime_ns, digest, duplicate_of))
        except (OSError, ValueError) as error:
            plan.warnings.append(f"{source.name}: {error}")
    return plan


def _move_without_overwrite(source: Path, destination: Path, digest: str) -> None:
    """Criação exclusiva + verificação. Nunca usa rename/replace sobre o destino."""
    if not _regular(source):
        raise ValueError("Origem não é um arquivo regular.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 'xb' falha se qualquer objeto já ocupar o destino. Funciona entre discos.
    created = False
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            created = True
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        shutil.copystat(source, destination, follow_symlinks=False)
        if fingerprint(destination) != digest or fingerprint(source) != digest:
            raise ValueError("Arquivo mudou durante a operação; original preservado.")
        source.unlink()
    except BaseException:
        if created and source.exists():
            destination.unlink(missing_ok=True)
        raise


class History:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else state_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db_path = self.directory / "historico.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, created TEXT NOT NULL, root TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL,
                    source TEXT NOT NULL, destination TEXT NOT NULL,
                    sha256 TEXT NOT NULL, size INTEGER NOT NULL,
                    status TEXT NOT NULL, error TEXT NOT NULL DEFAULT ''
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lock(self):
        """Serializa interface, CLI e monitor, inclusive entre processos."""
        with _thread_lock, (self.directory / "operacao.lock").open("a+b") as stream:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                if stream.read(1) == b"":
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise RuntimeError("Outra instância está organizando arquivos.") from error
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                if os.name == "nt":
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def batches(self, limit: int = 30) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("""
                SELECT b.*, COUNT(a.id) AS total,
                  SUM(CASE WHEN a.status = 'done' THEN 1 ELSE 0 END) AS moved,
                  SUM(CASE WHEN a.status = 'undone' THEN 1 ELSE 0 END) AS undone,
                  SUM(CASE WHEN a.error != '' OR a.status IN ('error', 'pending') THEN 1 ELSE 0 END) AS errors
                FROM batches b LEFT JOIN actions a ON a.batch_id = b.id
                GROUP BY b.id ORDER BY b.created DESC LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]

    def actions(self, batch_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM actions WHERE batch_id = ? ORDER BY id", (batch_id,))]

    def _status(self, action_id: int, status: str, error: str = "") -> None:
        with self.connect() as db:
            db.execute("UPDATE actions SET status = ?, error = ? WHERE id = ?",
                       (status, error, action_id))

    def execute(self, plan: Plan, progress: Callable[[str], None] | None = None) -> dict:
        if not plan.items:
            return {"id": "", "moved": 0, "errors": []}
        batch_id = uuid.uuid4().hex[:12]
        result = {"id": batch_id, "moved": 0, "errors": []}
        with self.lock():
            with self.connect() as db:
                db.execute("INSERT INTO batches VALUES (?, ?, ?)", (
                    batch_id, datetime.now(timezone.utc).isoformat(), str(plan.root)))
            for item in plan.items:
                with self.connect() as db:
                    action_id = db.execute("""INSERT INTO actions
                        (batch_id, source, destination, sha256, size, status)
                        VALUES (?, ?, ?, ?, ?, 'pending')""", (
                            batch_id, str(item.source), str(item.destination), item.sha256, item.size)).lastrowid
                try:
                    if item.source.is_relative_to(self.directory.resolve()):
                        raise ValueError("Arquivos internos do histórico não podem ser organizados.")
                    _safe_parent(item.source, plan.root)
                    _safe_parent(item.destination, plan.root)
                    info = item.source.stat()
                    if (info.st_size, info.st_mtime_ns) != (item.size, item.mtime_ns):
                        raise ValueError("Arquivo mudou desde a análise. Analise novamente.")
                    if fingerprint(item.source) != item.sha256:
                        raise ValueError("Conteúdo mudou desde a análise.")
                    if progress:
                        progress(item.source.name)
                    _move_without_overwrite(item.source, item.destination, item.sha256)
                    self._status(action_id, "done")
                    result["moved"] += 1
                except (OSError, ValueError) as error:
                    self._status(action_id, "error", str(error))
                    result["errors"].append(f"{item.source.name}: {error}")
        return result

    def undo(self, batch_id: str) -> dict:
        result = {"restored": 0, "errors": []}
        with self.lock():
            with self.connect() as db:
                batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
            if not batch:
                raise ValueError("Operação não encontrada.")
            root = Path(batch["root"])
            for action in reversed(self.actions(batch_id)):
                if action["status"] not in {"done", "pending"}:
                    continue
                source, destination = Path(action["source"]), Path(action["destination"])
                try:
                    _safe_parent(source, root)
                    _safe_parent(destination, root)
                    # Recupera interrupção após a cópia ou após uma restauração concluída.
                    if source.is_file() and not destination.exists():
                        if fingerprint(source) == action["sha256"]:
                            self._status(action["id"], "undone")
                            continue
                    if source.exists() or source.is_symlink():
                        raise ValueError("A origem já está ocupada; arquivo preservado.")
                    if not _regular(destination) or fingerprint(destination) != action["sha256"]:
                        raise ValueError("Destino alterado ou ausente; restauração ignorada.")
                    _move_without_overwrite(destination, source, action["sha256"])
                    self._status(action["id"], "undone")
                    result["restored"] += 1
                except (OSError, ValueError) as error:
                    # Mantém 'done' para permitir nova tentativa após resolver o conflito.
                    self._status(action["id"], action["status"], str(error))
                    result["errors"].append(f"{source.name}: {error}")
        return result


def export_csv(plan: Plan, target: Path | str) -> None:
    # Exclusivo: um relatório nunca sobrescreve um arquivo existente.
    with Path(target).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Origem", "Destino", "Categoria", "Bytes", "SHA256", "Duplicado de"])
        for item in plan.items:
            # Neutraliza fórmulas ao abrir nomes de arquivos em planilhas.
            def safe(value: str) -> str:
                return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value
            writer.writerow([safe(str(item.source)), safe(str(item.destination)), item.category,
                             item.size, item.sha256, safe(item.duplicate_of)])


class Monitor:
    """Polling local: só move arquivos estáveis em duas verificações sucessivas."""
    def __init__(self, root: Path | str, history: History, interval: float = 5,
                 settle: float = 10, recursive: bool = False, by_month: bool = False,
                 notify: Callable[[str], None] | None = None):
        if interval <= 0 or settle < 0:
            raise ValueError("Intervalo deve ser positivo e espera não pode ser negativa.")
        self.root, self.history = Path(root), history
        self.interval, self.settle = interval, settle
        self.recursive, self.by_month, self.notify = recursive, by_month, notify
        self.stop_event = threading.Event()
        self.previous: dict[str, tuple[int, int, str]] = {}

    def tick(self) -> dict:
        plan = scan(self.root, self.recursive, self.by_month, min_age=self.settle)
        current = {str(i.source): (i.size, i.mtime_ns, i.sha256) for i in plan.items}
        stable = [i for i in plan.items if self.previous.get(str(i.source)) == current[str(i.source)]]
        self.previous = current
        if self.stop_event.is_set():
            return {"id": "", "moved": 0, "errors": []}
        result = self.history.execute(Plan(plan.root, stable, plan.warnings, plan.skipped))
        result["errors"].extend(plan.warnings)
        if self.notify and (result["moved"] or result["errors"]):
            self.notify(f"{result['moved']} arquivo(s) organizado(s). " + " | ".join(result["errors"][:3]))
        return result

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.tick()
            except (OSError, ValueError, RuntimeError) as error:
                if self.notify:
                    self.notify(f"Monitor: {error}")
            self.stop_event.wait(self.interval)

    def stop(self) -> None:
        self.stop_event.set()

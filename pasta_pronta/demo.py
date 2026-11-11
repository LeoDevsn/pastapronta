"""Cria uma pasta isolada com arquivos fictícios para experimentar o aplicativo."""

import tempfile
import zipfile
from pathlib import Path


def create_demo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="PastaPronta-demo-"))
    samples = {
        "reuniao-equipe.txt": "Reunião fictícia\nRevisar proposta e organizar entregas.\n",
        "reuniao-equipe-copia.txt": "Reunião fictícia\nRevisar proposta e organizar entregas.\n",
        "clientes-exemplo.csv": "nome;etapa\nCliente fictício A;proposta\nCliente fictício B;revisão\n",
        "despesas-exemplo.csv": "descricao;valor\nMaterial fictício;42\nServiço fictício;150\n",
        "ideias.md": "# Ideias de projeto\n\nAutomatizar tarefas repetitivas.\n",
        "pagina-exemplo.html": "<!doctype html><html lang='pt-BR'><title>Exemplo</title><h1>Olá!</h1></html>",
        "config-exemplo.json": '{"projeto": "demonstração", "ativo": true}\n',
        "arquivo-sem-tipo": "Arquivo fictício sem extensão, para a categoria Outros.\n",
        "download-em-andamento.crdownload": "Este arquivo deve ser ignorado.\n",
    }
    for name, content in samples.items():
        (root / name).write_text(content, encoding="utf-8")
    with zipfile.ZipFile(root / "backup-exemplo.zip", "w") as archive:
        archive.writestr("leia-me.txt", "Conteúdo fictício de demonstração.")
    return root

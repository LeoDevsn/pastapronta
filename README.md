# PastaPronta

Uma automação desktop feita do zero em Python para reduzir o trabalho de organizar downloads, documentos e entregas. Interface em português, monitoramento contínuo, identificação de duplicados e histórico reversível. Executa localmente, sem cadastro, chave de API ou dependências externas.

## Baixar e usar (sem Python)

**[Baixe o PastaPronta para Windows](https://github.com/LeoDevsn/pastapronta/releases/latest)** e abra `PastaPronta.exe`. É um aplicativo portátil para Windows 10/11 de 64 bits: não exige instalação nem privilégios de administrador. O binário é distribuído sem assinatura digital.

Clique em **Experimentar demo** para conhecer o fluxo com arquivos fictícios. Depois selecione sua pasta, confira a prévia e organize. O menu **Como usar / Sobre** traz ajuda dentro do aplicativo.

O aplicativo lembra a última pasta e as opções, mas o monitor só é ativado quando você pedir. O arquivo `SHA256SUMS.txt` da versão permite conferir a integridade do download.

## Executar a partir do código

Requer **Python 3.12 ou superior com Tcl/Tk**, incluído na instalação padrão do Python para Windows.

1. Abra `iniciar.pyw` com dois cliques. Se a associação de arquivos não estiver configurada, execute `python -m pasta_pronta` nesta pasta.
2. Clique em **Experimentar demo**. Uma pasta temporária é criada com arquivos fictícios.
3. Confira a prévia e clique em **Organizar arquivos**.
4. Abra **Histórico e restauração**, selecione a operação e clique em **Desfazer selecionada**.
5. Para uso real, escolha uma pasta de documentos ou downloads e analise antes de organizar.

Para testar sem usar seus arquivos, também é possível iniciar assim:

```powershell
python -m pasta_pronta demo
```

## O que funciona

- **Organização em lote:** documentos, planilhas, imagens, vídeos, áudios, apresentações, compactados, instaladores, código e outros.
- **Prévia real:** mostra origem, categoria, tamanho e destino antes da movimentação.
- **Duplicados por conteúdo:** SHA-256 identifica cópias dentro dos arquivos analisados, mesmo com nomes diferentes. Todas as cópias são mantidas.
- **Colisões:** um arquivo de mesmo nome recebe um sufixo como `relatorio (2).pdf`. Um destino ocupado depois da análise produz um aviso, preservando os arquivos.
- **Subpastas e data:** opções para incluir subpastas e separar por ano/mês da última modificação.
- **Monitor automático:** verifica a pasta a cada 5 segundos. Arquivos precisam ter pelo menos 10 segundos e estar estáveis em duas verificações sucessivas.
- **Histórico persistente:** SQLite registra caminhos e hashes; permite desfazer depois de reabrir o aplicativo.
- **Relatório CSV:** exporta a prévia em UTF-8, com separador `;`, hashes e referências aos duplicados.
- **Terminal:** os mesmos recursos estão disponíveis para scripts e outras ferramentas.

O destino é sempre uma subpasta da pasta escolhida:

```text
Downloads/
  Organizados/
    Documentos/relatorio.pdf
    Planilhas/clientes.csv
    Imagens/foto.jpg
```

## Monitoramento

Clique em **Ativar monitor** e confirme. O monitor também organiza arquivos que já estavam na pasta, depois da espera de estabilidade. Pare o monitor antes de mudar a pasta ou desfazer uma operação, pois ele organizaria novamente os arquivos restaurados.

**O monitor funciona enquanto o aplicativo ou comando estiver aberto.** Não é instalado como serviço e não inicia com o Windows. Ao fechar, o aplicativo espera a movimentação em andamento terminar.

Downloads com extensões `.part`, `.crdownload`, `.download`, `.tmp` e `.partial`, arquivos ocultos com prefixo `.`, temporários do Office e links/junções são ignorados. A subpasta `Organizados` não entra em novas análises recursivas.

## Terminal

Execute os comandos dentro desta pasta. Caminhos com espaços devem ficar entre aspas.

```powershell
# Apenas prévia; nenhum arquivo é movido
python -m pasta_pronta scan "$env:USERPROFILE\Downloads"

# Prévia recursiva com relatório novo
python -m pasta_pronta scan "C:\Meus documentos" --recursive --csv "previa.csv"

# Mover efetivamente, separando por data de modificação
python -m pasta_pronta organize "C:\Meus documentos" --by-month --apply

# Manter o monitor em execução; Ctrl+C encerra
python -m pasta_pronta watch "$env:USERPROFILE\Downloads" --apply

# Consultar os IDs das operações e desfazer uma delas
python -m pasta_pronta history
python -m pasta_pronta undo ID_DA_OPERACAO --apply

# Histórico separado para demonstrações e testes
python -m pasta_pronta --state-dir ".estado-demo" demo
```

`organize` sem `--apply` executa somente a prévia. `watch` e `undo` exigem `--apply`. Saída `0` indica sucesso e `1` indica falhas ou avisos de leitura nos comandos de análise/organização. Filtros da interface alteram a exibição; **organizar move todos os arquivos da prévia**.

Instalação opcional para disponibilizar o comando `pastapronta`:

```powershell
python -m pip install .
pastapronta --help
```

Para gerar o executável em uma máquina Windows de desenvolvimento:

```powershell
python -m pip install pyinstaller==6.22.3
python scripts/build_windows.py
```

O executável é gerado em `dist/PastaPronta.exe`. O GitHub Actions também executa os testes nas versões 3.12, 3.13 e 3.14 do Python e disponibiliza o build de Windows como artefato.

## Integridade e limites

A movimentação cria o destino de forma exclusiva, copia o conteúdo, verifica SHA-256 de origem e destino e só então remove a origem. Falhas de cópia preservam a origem. Por usar cópia verificada, a operação precisa temporariamente de espaço livre equivalente ao arquivo e faz mais leitura de disco do que um simples renomeamento.

Ao desfazer, arquivos alterados e caminhos originais ocupados são preservados e aparecem como avisos. Resolva o conflito e tente desfazer novamente. As pastas vazias ficam no disco. O registro anterior à movimentação permite identificar operações interrompidas; interrupções no meio da cópia podem deixar uma cópia parcial que exige conferência manual. O aplicativo não substitui backups nem oferece transações atômicas entre arquivos.

Duplicados são comparados **dentro da análise atual**, sem indexar todos os arquivos já organizados. A classificação usa extensões, sem ler o significado dos documentos. **Esta versão é uma automação determinística; não usa IA e não há alegação de usuários externos ou implantação em produção.**

Use pastas de arquivos pessoais ou de trabalho. Ao ativar **Incluir subpastas**, a estrutura original é achatada por categoria; nomes repetidos recebem sufixos. Não use em instalações de aplicativos ou repositórios, cuja estrutura é necessária para funcionar.

O histórico fica em `%LOCALAPPDATA%\PastaPronta\historico.sqlite3` no Windows. Caminhos de arquivos ficam registrados somente nesse computador. Nenhum dado é enviado à internet. O argumento global `--state-dir` permite usar outro local. Apagar ou perder o banco impede desfazer as operações pelo aplicativo.

## Validação e estrutura

```powershell
python -X utf8 -m unittest discover -s tests -v
```

Os testes usam pastas temporárias e verificam prévia sem alterações, duplicados, colisões, restauração, mudança de conteúdo, cópia interrompida, monitoramento e comandos CLI. Testes de symlinks são ignorados quando o Windows não autoriza sua criação. A interface também foi conferida no Windows com organização e restauração de nove arquivos fictícios.

Para criar um ZIP de código-fonte para compartilhar, execute `python scripts/package_release.py`. O arquivo é salvo em `dist/`, sem o histórico e sem dados de demonstração. Quem receber precisa ter Python 3.12+ com Tkinter. O gerador exige um nome de versão ainda não usado e não sobrescreve ZIPs existentes.

```text
pasta_pronta/
  core.py       # análise, integridade, histórico, CSV e monitor
  gui.py        # interface Tkinter, tarefas em segundo plano
  __main__.py   # comandos de terminal
  demo.py       # arquivos fictícios isolados
tests/          # validação com arquivos reais em pastas temporárias
iniciar.pyw     # abertura da interface sem terminal no Windows
```

"""Interface desktop em português. Todo acesso ao Tk acontece na thread principal."""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import History, Monitor, Plan, export_csv, human_size, scan
from .demo import create_demo
from . import __version__, settings

BG = "#f4f6f9"
WHITE = "#ffffff"
INK = "#17243b"
MUTED = "#66758b"
GREEN = "#15745b"
LINE = "#e3e8ef"
NAVY = "#142439"


class Application(tk.Tk):
    def __init__(self, state_dir: Path | None = None, initial_folder: Path | None = None):
        super().__init__()
        self.title("PastaPronta — organização que acontece")
        self.geometry(f"{min(1220, self.winfo_screenwidth() - 50)}x{min(920, self.winfo_screenheight() - 90)}")
        self.minsize(1000, 680)
        self.configure(bg=BG)
        self.history = History(state_dir)
        preferences = settings.load(self.history.directory)
        self.plan: Plan | None = None
        self.busy = False
        self.monitor: Monitor | None = None
        self.monitor_thread: threading.Thread | None = None
        self.events: queue.Queue = queue.Queue()
        self.folder = tk.StringVar(value=str(initial_folder) if initial_folder else preferences.get("folder", ""))
        self.recursive = tk.BooleanVar(value=bool(preferences.get("recursive", False)))
        self.by_month = tk.BooleanVar(value=bool(preferences.get("by_month", False)))
        self.query = tk.StringVar()
        self.only_duplicates = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Escolha uma pasta ou experimente com arquivos fictícios.")
        self.metrics: list[tk.StringVar] = []
        self.controls: list[ttk.Widget] = []
        self._style()
        self._layout()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self._poll)
        self.query.trace_add("write", lambda *_: self.render_plan())
        self.refresh_history()
        if initial_folder:
            self.after(250, self.analyze)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*Font", ("Segoe UI", 10))
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=WHITE)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("TButton", padding=(14, 7), background=WHITE, foreground=INK,
                        borderwidth=1, font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#e9eff4"), ("disabled", "#edf0f4")],
                  foreground=[("disabled", "#99a4b2")])
        style.configure("Accent.TButton", background=GREEN, foreground=WHITE, borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#105a46"), ("disabled", "#a6c4ba")],
                  foreground=[("disabled", WHITE)])
        style.configure("Small.TButton", padding=(10, 4), font=("Segoe UI", 9))
        style.configure("TEntry", padding=7, fieldbackground=WHITE, bordercolor=LINE)
        style.configure("TCheckbutton", background=WHITE, foreground=MUTED, padding=3)
        style.map("TCheckbutton", background=[("active", WHITE)])
        style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        rowheight=36, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#eef2f6", foreground=MUTED,
                        padding=(10, 10), font=("Segoe UI Semibold", 9), relief="flat")
        style.map("Treeview", background=[("selected", "#dbede6")], foreground=[("selected", INK)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 10), background=BG, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", WHITE)], foreground=[("selected", GREEN)])
        style.configure("Horizontal.TProgressbar", background=GREEN, troughcolor=LINE, borderwidth=0)

    def label(self, parent, text, font=("Segoe UI", 10), fg=INK, bg=BG, **kw):
        return tk.Label(parent, text=text, font=font, fg=fg, bg=bg, **kw)

    def button(self, parent, text, command, accent=False, managed=True):
        button = ttk.Button(parent, text=text, command=command,
                            style="Accent.TButton" if accent else "TButton")
        if managed:
            self.controls.append(button)
        return button

    def _layout(self):
        side = tk.Frame(self, bg=NAVY, width=205)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=NAVY)
        brand.pack(fill="x", padx=24, pady=(32, 24))
        self.label(brand, "▣", ("Segoe UI", 28), "#70ddba", NAVY).pack(anchor="w")
        self.label(brand, "PastaPronta", ("Segoe UI Semibold", 19), WHITE, NAVY).pack(anchor="w", pady=(8, 0))
        self.label(brand, "MENOS CLIQUES. MAIS TEMPO.", ("Segoe UI", 7), "#9eafc5", NAVY).pack(anchor="w", pady=(5, 0))
        tk.Frame(side, height=1, bg="#2a3a4e").pack(fill="x", padx=24, pady=12)
        self.label(side, "SEU ESPAÇO", ("Segoe UI Semibold", 8), "#91a3bb", NAVY).pack(anchor="w", padx=24, pady=(12, 14))
        for text, index in (("  ◫   Organizar arquivos", 0), ("  ↺   Histórico", 1)):
            tk.Button(side, text=text, command=lambda i=index: self.tabs.select(i),
                      anchor="w", bg="#213b50", fg=WHITE, activebackground="#2b4a61",
                      activeforeground=WHITE, relief="flat", bd=0, padx=13, pady=13,
                      cursor="hand2", font=("Segoe UI", 10)).pack(fill="x", padx=12, pady=4)
        foot = tk.Frame(side, bg=NAVY)
        foot.pack(side="bottom", fill="x", padx=24, pady=28)
        self.label(foot, "●  LOCAL POR NATUREZA", ("Segoe UI Semibold", 8), "#70ddba", NAVY).pack(anchor="w")
        self.label(foot, "Seus arquivos ficam\nno seu computador.", ("Segoe UI", 10), "#b4c0d0", NAVY,
                   justify="left").pack(anchor="w", pady=(9, 20))
        tk.Button(foot, text="Como usar / Sobre", command=self.help, bg=NAVY, fg=WHITE,
                  activebackground="#213b50", activeforeground=WHITE, relief="flat",
                  cursor="hand2", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 9))
        self.label(foot, f"v{__version__}  /  Sem assinatura", ("Segoe UI", 8), "#91a3bb", NAVY).pack(anchor="w")

        main = tk.Frame(self, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=30, pady=22)
        top = tk.Frame(main, bg=BG)
        top.pack(fill="x")
        self.label(top, "AUTOMAÇÃO DE ARQUIVOS", ("Segoe UI Semibold", 9), GREEN).pack(anchor="w")
        self.label(top, "Sua pasta em ordem. Seu tempo de volta.",
                   ("Segoe UI Semibold", 21)).pack(anchor="w", pady=(5, 3))
        self.label(top, "Organize em lote, confira duplicados e automatize os próximos arquivos.",
                   fg=MUTED).pack(anchor="w")

        stats = tk.Frame(main, bg=BG)
        stats.pack(fill="x", pady=(14, 12))
        for i, (title, subtitle) in enumerate((("ARQUIVOS NA PRÉVIA", "prontos para organizar"),
                                               ("VOLUME TOTAL", "conteúdo analisado"),
                                               ("CÓPIAS DUPLICADAS", "mesmo conteúdo, outro arquivo"))):
            card = tk.Frame(stats, bg=WHITE, padx=18, pady=10, highlightthickness=1, highlightbackground=LINE)
            card.grid(row=0, column=i, sticky="ew", padx=(0, 12 if i < 2 else 0))
            stats.columnconfigure(i, weight=1, uniform="stats")
            self.label(card, title, ("Segoe UI Semibold", 8), MUTED, WHITE).pack(anchor="w")
            value = tk.StringVar(value="0 B" if i == 1 else "0")
            self.metrics.append(value)
            tk.Label(card, textvariable=value, font=("Segoe UI Semibold", 22), fg=INK, bg=WHITE).pack(anchor="w", pady=(3, 0))
            self.label(card, subtitle, ("Segoe UI", 9), MUTED, WHITE).pack(anchor="w")

        config = tk.Frame(main, bg=WHITE, padx=18, pady=12, highlightthickness=1, highlightbackground=LINE)
        config.pack(fill="x")
        head = tk.Frame(config, bg=WHITE)
        head.pack(fill="x")
        self.label(head, "01   Escolha o que organizar", ("Segoe UI Semibold", 11), bg=WHITE).pack(side="left")
        demo_button = self.button(head, "Experimentar demo", self.demo)
        demo_button.configure(style="Small.TButton")
        demo_button.pack(side="right")
        pathrow = tk.Frame(config, bg=WHITE)
        pathrow.pack(fill="x", pady=(10, 8))
        entry = ttk.Entry(pathrow, textvariable=self.folder, state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(pathrow, "Escolher pasta…", self.choose_folder).pack(side="right")
        options = tk.Frame(config, bg=WHITE)
        options.pack(fill="x")
        for text, variable in (("Incluir subpastas", self.recursive), ("Separar por ano / mês", self.by_month)):
            check = ttk.Checkbutton(options, text=text, variable=variable, command=self.invalidate)
            check.pack(side="left", padx=(0, 18))
            self.controls.append(check)
        self.label(config, "Destino: Organizados / categoria  ·  Duplicados são mantidos  ·  Nenhum arquivo é excluído",
                   ("Segoe UI", 9), MUTED, WHITE).pack(anchor="w", pady=(6, 0))

        actions = tk.Frame(main, bg=BG)
        actions.pack(fill="x", pady=12)
        self.analyze_btn = self.button(actions, "Analisar pasta", self.analyze)
        self.analyze_btn.pack(side="left", padx=(0, 8))
        self.organize_btn = self.button(actions, "Organizar arquivos  →", self.organize, accent=True)
        self.organize_btn.pack(side="left", padx=(0, 8))
        self.watch_btn = self.button(actions, "Ativar monitor", self.toggle_monitor, managed=False)
        self.watch_btn.pack(side="right")

        # Reserva o rodapé antes da área flexível para não cortar mensagens.
        tk.Label(main, textvariable=self.status, bg=BG, fg=MUTED,
                 anchor="w", justify="left", height=2, font=("Segoe UI", 9),
                 wraplength=800).pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(main, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress.pack(side="bottom", fill="x", pady=(12, 6))
        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill="both", expand=True)
        preview = ttk.Frame(self.tabs, style="Card.TFrame", padding=12)
        history = ttk.Frame(self.tabs, style="Card.TFrame", padding=12)
        self.tabs.add(preview, text="Prévia dos arquivos")
        self.tabs.add(history, text="Histórico e restauração")
        toolbar = tk.Frame(preview, bg=WHITE)
        toolbar.pack(fill="x", pady=(0, 8))
        self.label(toolbar, "Buscar:", fg=MUTED, bg=WHITE).pack(side="left", padx=(0, 6))
        ttk.Entry(toolbar, textvariable=self.query, width=22).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(toolbar, text="Só duplicados", variable=self.only_duplicates,
                        command=self.render_plan).pack(side="left")
        self.export_btn = self.button(toolbar, "Exportar CSV", self.export)
        self.export_btn.pack(side="right")
        table = tk.Frame(preview, bg=WHITE)
        self.tree = ttk.Treeview(table, columns=("file", "category", "size", "destination"),
                                 show="headings", selectmode="browse", height=5)
        for col, text, width in (("file", "ARQUIVO", 205), ("category", "CATEGORIA", 110),
                                 ("size", "TAMANHO", 85), ("destination", "DESTINO / DUPLICADO", 300)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, minwidth=60, stretch=col in {"file", "destination"})
        self.tree.tag_configure("duplicate", foreground="#986318", background="#fff8e8")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        xscroll = ttk.Scrollbar(preview, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=xscroll.set)
        self.preview_note = tk.StringVar(value="A prévia aparece aqui após analisar uma pasta.")
        tk.Label(preview, textvariable=self.preview_note, bg=WHITE, fg=MUTED,
                 font=("Segoe UI", 9), anchor="w", justify="left", wraplength=800).pack(side="bottom", fill="x", pady=(7, 0))
        xscroll.pack(side="bottom", fill="x")
        table.pack(fill="both", expand=True)

        hbar = tk.Frame(history, bg=WHITE)
        hbar.pack(fill="x", pady=(0, 10))
        self.label(hbar, "Selecione uma operação para restaurar os arquivos.", bg=WHITE, fg=MUTED).pack(side="left")
        self.undo_btn = self.button(hbar, "Desfazer selecionada", self.undo)
        self.undo_btn.pack(side="right")
        self.history_tree = ttk.Treeview(history, columns=("date", "folder", "moved", "undone", "errors"),
                                        show="headings", selectmode="browse", height=5)
        for col, text, width in (("date", "DATA / HORA", 140), ("folder", "PASTA", 310),
                                 ("moved", "MOVIDOS", 75), ("undone", "RESTAURADOS", 100), ("errors", "FALHAS", 65)):
            self.history_tree.heading(col, text=text)
            self.history_tree.column(col, width=width, minwidth=55)
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind("<<TreeviewSelect>>", self.history_details)
        self.history_note = tk.StringVar(value="O histórico fica neste computador, inclusive depois de fechar o aplicativo.")
        tk.Label(history, textvariable=self.history_note, bg=WHITE, fg=MUTED, justify="left",
                 wraplength=720, anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(8, 0))

        self.update_controls()

    def invalidate(self):
        self.plan = None
        self.render_plan()
        self.update_controls()

    def choose_folder(self):
        selected = filedialog.askdirectory(title="Selecione a pasta que deseja organizar", parent=self)
        if selected:
            self.folder.set(selected)
            self.invalidate()
            self.analyze()

    def demo(self):
        try:
            folder = create_demo()
            self.folder.set(str(folder))
            self.invalidate()
            self.status.set("Demonstração criada em uma pasta temporária, com arquivos fictícios.")
            self.analyze()
        except OSError as error:
            messagebox.showerror("Não foi possível criar a demo", str(error), parent=self)

    def update_controls(self):
        enabled = not self.busy and self.monitor is None
        for control in self.controls:
            control.configure(state="normal" if enabled else "disabled")
        for control in (self.organize_btn, self.export_btn):
            control.configure(state="normal" if enabled and self.plan and self.plan.items else "disabled")
        self.watch_btn.configure(state="normal" if not self.busy else "disabled",
                                 text="Parar monitor" if self.monitor else "Ativar monitor")

    def worker(self, operation, completed):
        self.busy = True
        self.update_controls()
        self.progress.start(12)
        def run():
            try:
                self.events.put(("result", completed, operation()))
            except Exception as error:
                self.events.put(("error", str(error)))
        threading.Thread(target=run, name="PastaPronta-operacao", daemon=False).start()

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] in {"result", "error"}:
                    self.busy = False
                    self.progress.stop()
                    if event[0] == "result":
                        event[1](event[2])
                    else:
                        self.status.set(event[1])
                        messagebox.showerror("Operação não concluída", event[1], parent=self)
                    self.update_controls()
                elif event[0] == "status":
                    self.status.set(event[1])
                elif event[0] == "monitor":
                    self.status.set(event[1])
                    self.refresh_history()
                elif event[0] == "stopped":
                    self.monitor = None
                    self.monitor_thread = None
                    self.progress.stop()
                    self.status.set("Monitor encerrado. As operações continuam disponíveis no histórico.")
                    self.refresh_history()
                    self.update_controls()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def progress_callback(self):
        last = [0.0]
        def callback(name):
            now = time.monotonic()
            if now - last[0] > 0.15:
                last[0] = now
                self.events.put(("status", f"Processando: {name}"))
        return callback

    def analyze(self):
        if not self.folder.get():
            self.choose_folder()
            return
        folder, recursive, by_month = self.folder.get(), self.recursive.get(), self.by_month.get()
        self.invalidate()
        self.status.set("Analisando arquivos e comparando conteúdo…")
        progress = self.progress_callback()
        def done(plan):
            self.plan = plan
            self.render_plan()
            self.tabs.select(0)
            self.status.set(f"Análise concluída. {len(plan.items)} arquivo(s), {plan.skipped} ignorado(s), {len(plan.warnings)} aviso(s).")
            if plan.warnings:
                messagebox.showwarning("Alguns arquivos foram ignorados", "\n".join(plan.warnings[:15]), parent=self)
        self.worker(lambda: scan(folder, recursive, by_month, progress=progress), done)

    def render_plan(self):
        self.tree.delete(*self.tree.get_children())
        plan = self.plan
        for value, text in zip(self.metrics, (str(len(plan.items)) if plan else "0",
                                              human_size(plan.total_bytes) if plan else "0 B",
                                              str(plan.duplicates) if plan else "0")):
            value.set(text)
        if not plan:
            self.preview_note.set("Analise uma pasta para conferir cada destino antes de mover.")
            return
        query = self.query.get().casefold()
        shown = 0
        for item in plan.items:
            relative = str(item.source.relative_to(plan.root))
            if query not in f"{relative} {item.category} {item.duplicate_of}".casefold():
                continue
            if self.only_duplicates.get() and not item.duplicate_of:
                continue
            target = str(item.destination.relative_to(plan.root))
            if item.duplicate_of:
                target += f"  ·  cópia de {item.duplicate_of}"
            self.tree.insert("", "end", values=(relative, item.category, human_size(item.size), target),
                             tags=("duplicate",) if item.duplicate_of else ())
            shown += 1
        self.preview_note.set(f"{shown} de {len(plan.items)} arquivo(s) exibido(s). A organização inclui toda a prévia; filtros só alteram a exibição.")

    def organize(self):
        plan = self.plan
        if not plan or not plan.items:
            return
        if not messagebox.askyesno("Organizar arquivos", f"Mover {len(plan.items)} arquivo(s) para:\n{plan.root / 'Organizados'}\n\nDuplicados serão mantidos. Você pode desfazer pelo histórico.", parent=self):
            return
        def done(result):
            self.invalidate()
            self.refresh_history()
            self.status.set(f"Concluído: {result['moved']} arquivo(s) organizado(s). Operação {result['id']}.")
            if result["errors"]:
                messagebox.showwarning("Concluído com avisos", "\n".join(result["errors"][:15]), parent=self)
        progress = self.progress_callback()
        self.worker(lambda: self.history.execute(plan, progress), done)

    def export(self):
        if not self.plan:
            return
        target = filedialog.asksaveasfilename(parent=self, title="Exportar prévia para um novo arquivo",
                                            initialfile=f"pastapronta-{datetime.now():%Y%m%d-%H%M%S}.csv",
                                            defaultextension=".csv", filetypes=[("Relatório CSV", "*.csv")])
        if target:
            try:
                export_csv(self.plan, target)
                self.status.set(f"Prévia exportada: {target}")
            except OSError as error:
                messagebox.showerror("Não foi possível exportar", f"{error}\n\nEscolha um nome de arquivo novo.", parent=self)

    def refresh_history(self):
        selection = self.history_tree.selection()
        self.history_tree.delete(*self.history_tree.get_children())
        for batch in self.history.batches():
            date = datetime.fromisoformat(batch["created"]).astimezone().strftime("%d/%m/%Y %H:%M")
            self.history_tree.insert("", "end", iid=batch["id"], values=(
                date, batch["root"], batch["moved"], batch["undone"], batch["errors"]))
        if selection and self.history_tree.exists(selection[0]):
            self.history_tree.selection_set(selection[0])

    def history_details(self, _event=None):
        selected = self.history_tree.selection()
        if selected:
            actions = self.history.actions(selected[0])
            errors = [f"{Path(a['source']).name}: {a['error']}" for a in actions if a["error"]]
            self.history_note.set(f"Operação {selected[0]}. " + (" | ".join(errors[:3]) if errors else
                                  "Arquivos alterados e caminhos ocupados são preservados ao desfazer."))

    def undo(self):
        selected = self.history_tree.selection()
        if not selected:
            messagebox.showinfo("Selecione uma operação", "Escolha uma linha no histórico para desfazer.", parent=self)
            return
        if not messagebox.askyesno("Restaurar arquivos", "Restaurar os arquivos desta operação aos caminhos originais?\n\nArquivos alterados ou caminhos ocupados serão preservados.", parent=self):
            return
        batch_id = selected[0]
        def done(result):
            self.invalidate()
            self.refresh_history()
            self.status.set(f"{result['restored']} arquivo(s) restaurado(s).")
            if result["errors"]:
                messagebox.showwarning("Restauração com avisos", "\n".join(result["errors"][:15]), parent=self)
        self.worker(lambda: self.history.undo(batch_id), done)

    def toggle_monitor(self):
        if self.monitor:
            self.monitor.stop()
            self.watch_btn.configure(state="disabled", text="Encerrando…")
            self.status.set("Encerrando após concluir a operação em andamento…")
            return
        if not self.folder.get():
            self.choose_folder()
            return
        if not messagebox.askyesno("Ativar organização automática", "Enquanto o aplicativo estiver aberto, novos arquivos serão organizados automaticamente.\n\nVerificação a cada 5 segundos. Arquivos precisam ter 10 segundos e estar estáveis em duas verificações.\n\nAs operações ficam no histórico. Ativar?", parent=self):
            return
        self.invalidate()
        monitor = Monitor(self.folder.get(), self.history, recursive=self.recursive.get(),
                          by_month=self.by_month.get(), notify=lambda text: self.events.put(("monitor", text)))
        self.monitor = monitor
        def run():
            try:
                monitor.run()
            finally:
                self.events.put(("stopped",))
        self.monitor_thread = threading.Thread(target=run, name="PastaPronta-monitor", daemon=False)
        self.monitor_thread.start()
        self.progress.start(20)
        self.status.set("Monitor ativo · verificação a cada 5 s · arquivos estáveis · pare o monitor para analisar ou desfazer.")
        self.update_controls()

    def close(self):
        if self.busy:
            messagebox.showinfo("Operação em andamento", "Aguarde a operação terminar antes de fechar.", parent=self)
            return
        try:
            settings.save(self.history.directory, self.folder.get(), self.recursive.get(), self.by_month.get())
        except OSError:
            pass
        if self.monitor:
            self.monitor.stop()
            self.watch_btn.configure(state="disabled", text="Encerrando…")
            def wait():
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.after(100, wait)
                else:
                    self.destroy()
            wait()
        else:
            self.destroy()

    def help(self):
        messagebox.showinfo("Como usar o PastaPronta", "1. Experimente a demo ou escolha uma pasta.\n2. Clique em Analisar pasta e confira os destinos.\n3. Clique em Organizar arquivos para mover.\n4. Para desfazer, selecione a operação no Histórico.\n\nO monitor organiza automaticamente enquanto o aplicativo estiver aberto. Pare-o antes de desfazer. Duplicados são mantidos.\n\nSeus dados ficam neste computador.\nO histórico não substitui backups.\n\nPastaPronta " + __version__ + " · Leonardo Santos\ngithub.com/LeoDevsn/pastapronta", parent=self)


def launch(state_dir: Path | None = None, initial_folder: Path | None = None):
    app = Application(state_dir, initial_folder)
    app.mainloop()

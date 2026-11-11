"""Clique duas vezes neste arquivo no Windows para abrir sem terminal."""

import traceback
if __name__ == "__main__":
    try:
        from pasta_pronta.gui import launch
        launch()
    except Exception:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("PastaPronta não iniciou", traceback.format_exc())
        root.destroy()

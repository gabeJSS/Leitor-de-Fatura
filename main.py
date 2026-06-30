import os
import tkinter as tk

from ui.app import MacroApp
from ui.dnd import TkinterDnD, _DND_AVAILABLE
from ui.theme import APPDATA_DIR, JSON_VERO, JSON_ALGAR, JSON_VIVO, JSON_CLARO, JSON_MAIS


if __name__ == "__main__":
    print(f"[INFO] JSONs esperados em: {APPDATA_DIR}")
    for nome, path in [("vero", JSON_VERO), ("algar", JSON_ALGAR),
                       ("vivo", JSON_VIVO), ("claro", JSON_CLARO), ("mais", JSON_MAIS)]:
        print(f"       {nome}.json -> {path}")

    if _DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
        print("[AVISO] Biblioteca 'tkinterdnd2' não encontrada. O Drag & Drop está desativado.")
        print("        Para ativar, instale com o comando: pip install tkinterdnd2")

    app = MacroApp(root)
    root.mainloop()

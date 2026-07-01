import os
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import pyautogui

from ui.theme import (APPDATA_DIR, BG, PANEL, ACCENT, SUCCESS, DANGER, WARNING,
                      TEXT, SUBTEXT, BORDER, BTN_BG, BTN_HOV, ENTRY_BG,
                      GREEN_BTN, GREEN_HOV, VERO_COLOR, ALGAR_COLOR,
                      VIVO_COLOR, CLARO_COLOR, MAIS_COLOR,
                      JSON_VERO, JSON_ALGAR, JSON_VIVO, JSON_CLARO, JSON_MAIS)
from ui.dnd import parse_drop_data, bind_drop
from ui.widgets import apply_style, create_button, create_info_row, create_section
from core.macro_runner import carregar_json, MacroRunner
from core.database import normalizar_servidor_sql, testar_conexao
from downloaders.mais import MaisDownloader
from downloaders.vero import VeroDownloader
from downloaders.claro import ClaroDownloader
from core.settings import load_settings, save_settings


class MacroApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Macro Unificado — Vero, Algar, Vivo, Claro & Mais")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(900, 740)

        self.pasta_pdf = ""
        self.pdfs_individuais = []
        self.pdfs_baixados = []
        self.dados_vero = carregar_json(JSON_VERO)
        self.dados_algar = carregar_json(JSON_ALGAR)
        self.dados_vivo = carregar_json(JSON_VIVO)
        self.dados_claro = carregar_json(JSON_CLARO)
        self.dados_mais = carregar_json(JSON_MAIS)
        self.inputs_manuais = {}
        self.posicoes = {}
        self.usar_padrao = tk.BooleanVar()
        self.usar_baixados = tk.BooleanVar(value=False)
        self.pausado = False
        self.settings = load_settings()
        self.settings_vars = {"database": {}, "downloaders": {}}

        apply_style(self.root)
        self._build_ui()
        self.runner = MacroRunner(
            log_fn=self._log,
            status_fn=self._set_status,
            stats_update_fn=self._update_stats,
            op_label_fn=lambda text, color: self.lbl_op.config(text=text, fg=color),
            get_posicao_fn=self.get_posicao,
            dados_por_operadora=self._json_por_operadora(),
            pause_check_fn=lambda: self.pausado,
            prompt_user_fn=self._prompt_usuario_decisao,
            on_finish_fn=self._on_macro_finish,
        )
        self.root.bind("<F8>", self.toggle_pausa)
        self.root.after(500, self._checar_jsons)
        self.root.after(600, self._checar_faturas_temporarias)

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        self._build_header()
        pane = ttk.Frame(self.root, style="TFrame")
        pane.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        pane.columnconfigure(0, weight=0, minsize=300)
        pane.columnconfigure(1, weight=1)
        pane.rowconfigure(0, weight=1)
        self._build_left(pane)
        self._build_right(pane)
        self._build_status_bar()

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=PANEL, height=56)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        canvas = tk.Canvas(hdr, bg=PANEL, highlightthickness=0, height=4)
        canvas.place(x=0, y=52, relwidth=1)
        canvas.create_rectangle(0, 0, 10000, 4, fill=ACCENT, outline="")
        tk.Label(hdr, text="⚡  MACRO UNIFICADO", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=20, pady=10)
        tk.Label(hdr, text="Vero, Algar, Vivo, Claro & Mais — detecção automática", bg=PANEL, fg=SUBTEXT,
                 font=("Segoe UI", 10)).pack(side="left", pady=10)
        self.lbl_pause = tk.Label(hdr, text="▶  RODANDO", bg=PANEL, fg=SUCCESS, font=("Segoe UI", 9, "bold"))
        self.lbl_pause.pack(side="right", padx=20)
        tk.Label(hdr, text="F8 pausar / retomar   |", bg=PANEL, fg=SUBTEXT, font=("Segoe UI", 9)).pack(side="right")

    def _build_left(self, parent):
        wrapper = tk.Frame(parent, bg=BG)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)

        canvas = tk.Canvas(wrapper, bg=BG, highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=vsb.set)

        left = ttk.Frame(canvas, style="TFrame")
        left.columnconfigure(0, weight=1)
        left_win = canvas.create_window((0, 0), window=left, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(left_win, width=event.width)

        left.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        create_section(left, "📂  Arquivos", 0)
        self.lbl_pasta = create_info_row(left, "Pasta de PDFs:", "Nenhuma selecionada", 1)

        self.check_usar_baixados = ttk.Checkbutton(left, text="Usar 0 faturas baixadas da web",
                                                   variable=self.usar_baixados, style="TCheckbutton",
                                                   command=self._on_usar_baixados_toggle)
        self.check_usar_baixados.grid(row=2, column=0, sticky="w", pady=(4, 0), padx=4)
        self.check_usar_baixados.grid_remove() # Oculto até ter arquivos

        create_button(left, "Selecionar pasta com PDFs", self.selecionar_pasta, row=2)

        drop_hint = tk.Frame(left, bg=ENTRY_BG, relief="flat", bd=0, padx=10, pady=8,
                             cursor="hand2")
        drop_hint.grid(row=3, column=0, sticky="ew", pady=(4, 0))
        drop_hint.columnconfigure(0, weight=1)
        tk.Label(drop_hint, text="📥  Arraste PDFs ou pasta aqui",
                 bg=ENTRY_BG, fg=SUBTEXT, font=("Segoe UI", 9, "italic")).pack()
        self._bind_drop(drop_hint, drop_hint)

        json_frame = tk.Frame(left, bg=ENTRY_BG, padx=10, pady=8)
        json_frame.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        tk.Label(json_frame, text="JSONs carregados do AppData:", bg=ENTRY_BG,
                 fg=SUBTEXT, font=("Segoe UI", 8)).pack(anchor="w")
        self.lbl_vero_json = tk.Label(json_frame, bg=ENTRY_BG, font=("Segoe UI", 9), anchor="w")
        self.lbl_algar_json = tk.Label(json_frame, bg=ENTRY_BG, font=("Segoe UI", 9), anchor="w")
        self.lbl_vivo_json = tk.Label(json_frame, bg=ENTRY_BG, font=("Segoe UI", 9), anchor="w")
        self.lbl_claro_json = tk.Label(json_frame, bg=ENTRY_BG, font=("Segoe UI", 9), anchor="w")
        self.lbl_mais_json = tk.Label(json_frame, bg=ENTRY_BG, font=("Segoe UI", 9), anchor="w")
        for lbl in (self.lbl_vero_json, self.lbl_algar_json, self.lbl_vivo_json,
                    self.lbl_claro_json, self.lbl_mais_json):
            lbl.pack(anchor="w")
        self._atualizar_status_json()

        create_button(left, "🔄  Recarregar JSONs", self._recarregar_jsons, row=5, small=True)
        create_button(left, "📁  Abrir pasta dos JSONs", self._abrir_pasta_appdata, row=6, small=True)

        ttk.Separator(left, orient="horizontal").grid(row=7, column=0, sticky="ew", pady=10)
        create_section(left, "🖱  Coordenadas de clique", 8)

        check_frame = ttk.Frame(left, style="Panel.TFrame", padding=8)
        check_frame.grid(row=9, column=0, sticky="ew", pady=(4, 8))
        check_frame.columnconfigure(0, weight=1)
        ttk.Checkbutton(check_frame, text="Usar coordenadas padrão",
                        variable=self.usar_padrao).grid(row=0, column=0, sticky="w")
        ttk.Label(check_frame, text="Desmarque para definir manualmente",
                  style="Sub.TLabel").grid(row=1, column=0, sticky="w")

        campos = ["fornecedor", "nota_fiscal", "confirmar", "anexar", "anexar2", "pgto", "pgto2"]
        container = ttk.Frame(left, style="Panel.TFrame", padding=10)
        container.grid(row=10, column=0, sticky="ew")
        container.columnconfigure(1, weight=1)
        container.columnconfigure(3, weight=1)

        for i, campo in enumerate(campos):
            ttk.Label(container, text=campo, style="Sub.TLabel", width=12, anchor="e").grid(
                row=i, column=0, padx=(0, 6), pady=3, sticky="e")
            x_var, y_var = tk.StringVar(), tk.StringVar()
            self.inputs_manuais[campo] = (x_var, y_var)
            ttk.Label(container, text="X", style="Sub.TLabel").grid(row=i, column=1, sticky="e")
            ttk.Entry(container, textvariable=x_var, width=6).grid(row=i, column=2, padx=3)
            ttk.Label(container, text="Y", style="Sub.TLabel").grid(row=i, column=3, sticky="e")
            ttk.Entry(container, textvariable=y_var, width=6).grid(row=i, column=4, padx=(3, 8))
            btn = tk.Button(container, text="📍", bg=BTN_BG, fg=ACCENT, relief="flat",
                            cursor="hand2", font=("Segoe UI", 10),
                            command=lambda c=campo: self.definir_posicao(c))
            btn.grid(row=i, column=5, pady=2)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=BTN_HOV))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=BTN_BG))

        ttk.Separator(left, orient="horizontal").grid(row=11, column=0, sticky="ew", pady=10)

        rel_btn = tk.Button(left, text="📊  Gerar Relatório (sem executar macro)",
            command=lambda: threading.Thread(target=lambda: self.runner.gerar_relatorio_prevoo(self._get_pdfs_para_processar()), daemon=True).start(),
            bg=GREEN_BTN, fg="white", relief="flat", cursor="hand2",
            font=("Segoe UI", 10, "bold"), activebackground=GREEN_HOV, activeforeground="white",
            pady=9, padx=12, bd=0)
        rel_btn.grid(row=12, column=0, sticky="ew", pady=(0, 4))
        rel_btn.bind("<Enter>", lambda e: rel_btn.config(bg=GREEN_HOV))
        rel_btn.bind("<Leave>", lambda e: rel_btn.config(bg=GREEN_BTN))

        create_button(left, "▶  Executar macro em massa", self.executar_macro_em_massa_thread,
                      row=13, color=ACCENT, text_color="white", big=True)

        stats_frame = ttk.Frame(left, style="Panel.TFrame", padding=10)
        stats_frame.grid(row=14, column=0, sticky="ew", pady=(10, 0))
        stats_frame.columnconfigure((0, 1, 2), weight=1)
        for col, (label, color, attr) in enumerate([
            ("Total", SUBTEXT, "lbl_total"), ("✅ OK", SUCCESS, "lbl_ok"), ("❌ Falha", DANGER, "lbl_fail")
        ]):
            f = tk.Frame(stats_frame, bg=ENTRY_BG, padx=10, pady=8)
            f.grid(row=0, column=col, padx=4, sticky="ew")
            tk.Label(f, text=label, bg=ENTRY_BG, fg=SUBTEXT, font=("Segoe UI", 8)).pack()
            lbl = tk.Label(f, text="0", bg=ENTRY_BG, fg=color, font=("Segoe UI", 18, "bold"))
            lbl.pack()
            setattr(self, attr, lbl)

    def _build_right(self, parent):
        right = ttk.Frame(parent, style="TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        create_section(right, "📋  Log de execução", 0)
        tabs = ttk.Notebook(right)
        tabs.grid(row=1, column=0, sticky="nsew")

        log_frame = tk.Frame(tabs, bg=ENTRY_BG, relief="flat", bd=0)
        tabs.add(log_frame, text="Log")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.output = tk.Text(log_frame, bg=ENTRY_BG, fg=TEXT, insertbackground=TEXT,
            font=("Cascadia Code", 9), relief="flat", bd=0, padx=12, pady=10, wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.output.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scrollbar.set)
        self._bind_drop(self.output, log_frame)

        for tag, color in [("ok", SUCCESS), ("error", DANGER), ("warn", WARNING),
                           ("info", ACCENT), ("sub", SUBTEXT), ("green", "#27ae60"),
                           ("vero", VERO_COLOR), ("algar", ALGAR_COLOR),
                           ("vivo", VIVO_COLOR), ("claro", CLARO_COLOR), ("mais", MAIS_COLOR)]:
            self.output.tag_configure(tag, foreground=color)
        self.output.tag_configure("bold", foreground=TEXT, font=("Cascadia Code", 9, "bold"))

        btn_frame = ttk.Frame(right, style="TFrame")
        btn_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        create_button(btn_frame, "🗑  Limpar log", self._clear_log, row=0, side="left", small=True)

        downloads_frame = tk.Frame(tabs, bg=ENTRY_BG, padx=16, pady=16)
        tabs.add(downloads_frame, text="Downloads")
        self._build_downloads_tab(downloads_frame)

        settings_frame = tk.Frame(tabs, bg=ENTRY_BG, padx=16, pady=16)
        tabs.add(settings_frame, text="Configurações")
        self._build_settings_tab(settings_frame)

    def _build_settings_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        tk.Label(parent, text="Configurações Gerais", bg=ENTRY_BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # --- Seção Banco de Dados ---
        tk.Label(parent, text="Banco de Dados", bg=ENTRY_BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 4))

        campos = [
            ("driver", "Driver"),
            ("server", "Servidor"),
            ("database", "Database"),
            ("username", "Usuario"),
            ("password", "Senha"),
        ]
        for row, (key, label) in enumerate(campos, 2):
            tk.Label(parent, text=label, bg=ENTRY_BG, fg=SUBTEXT,
                     font=("Segoe UI", 9)).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=4)
            var = tk.StringVar(value=str(self.settings["database"].get(key, "")))
            self.settings_vars["database"][key] = var
            show = "*" if key == "password" else ""
            ttk.Entry(parent, textvariable=var, show=show).grid(row=row, column=1, sticky="ew", pady=4)

        self.settings_vars["database"]["trust_server_certificate"] = tk.BooleanVar(
            value=bool(self.settings["database"].get("trust_server_certificate", True))
        )
        ttk.Checkbutton(
            parent,
            text="TrustServerCertificate",
            variable=self.settings_vars["database"]["trust_server_certificate"],
        ).grid(row=len(campos) + 2, column=1, sticky="w", pady=(6, 10))

        tk.Label(parent, text=r"Exemplo: 10.128.50.250\sqlexpress",
                 bg=ENTRY_BG, fg=SUBTEXT, font=("Segoe UI", 8)).grid(
            row=len(campos) + 3, column=1, sticky="w", pady=(0, 8)
        )

        # --- Seção Downloaders ---
        ttk.Separator(parent, orient="horizontal").grid(row=len(campos) + 4, column=0, columnspan=2, sticky="ew", pady=15)
        tk.Label(parent, text="Credenciais de Download", bg=ENTRY_BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).grid(row=len(campos) + 5, column=0, columnspan=2, sticky="w", pady=(8, 4))

        # Mais Internet
        tk.Label(parent, text="Mais Internet (CNPJ/CPF):", bg=ENTRY_BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).grid(row=len(campos) + 6, column=0, sticky="e", padx=(0, 8), pady=4)
        self.settings_vars["downloaders"]["mais_txid"] = tk.StringVar(value=self.settings["downloaders"]["mais"].get("txid", ""))
        ttk.Entry(parent, textvariable=self.settings_vars["downloaders"]["mais_txid"]).grid(row=len(campos) + 6, column=1, sticky="ew", pady=4)

        tk.Label(parent, text="Mais Internet (Senha):", bg=ENTRY_BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).grid(row=len(campos) + 7, column=0, sticky="e", padx=(0, 8), pady=4)
        self.settings_vars["downloaders"]["mais_pass"] = tk.StringVar(value=self.settings["downloaders"]["mais"].get("password", ""))
        ttk.Entry(parent, textvariable=self.settings_vars["downloaders"]["mais_pass"], show="*").grid(row=len(campos) + 7, column=1, sticky="ew", pady=4)

        # Vero Internet
        tk.Label(parent, text="Vero Internet (CNPJ/CPF):", bg=ENTRY_BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).grid(row=len(campos) + 8, column=0, sticky="e", padx=(0, 8), pady=4)
        self.settings_vars["downloaders"]["vero_user"] = tk.StringVar(value=self.settings["downloaders"].get("vero", {}).get("username", ""))
        ttk.Entry(parent, textvariable=self.settings_vars["downloaders"]["vero_user"]).grid(row=len(campos) + 8, column=1, sticky="ew", pady=4)

        tk.Label(parent, text="Vero Internet (Senha):", bg=ENTRY_BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).grid(row=len(campos) + 9, column=0, sticky="e", padx=(0, 8), pady=4)
        self.settings_vars["downloaders"]["vero_pass"] = tk.StringVar(value=self.settings["downloaders"].get("vero", {}).get("password", ""))
        ttk.Entry(parent, textvariable=self.settings_vars["downloaders"]["vero_pass"], show="*").grid(row=len(campos) + 9, column=1, sticky="ew", pady=4)

        # Claro
        tk.Label(parent, text="Claro (CNPJ/Documento):", bg=ENTRY_BG, fg=SUBTEXT,
                 font=("Segoe UI", 9)).grid(row=len(campos) + 10, column=0, sticky="e", padx=(0, 8), pady=4)
        self.settings_vars["downloaders"]["claro_doc"] = tk.StringVar(value=self.settings["downloaders"].get("claro", {}).get("document", ""))
        ttk.Entry(parent, textvariable=self.settings_vars["downloaders"]["claro_doc"]).grid(row=len(campos) + 10, column=1, sticky="ew", pady=4)

        # --- Botões Salvar/Testar ---
        ttk.Separator(parent, orient="horizontal").grid(row=len(campos) + 11, column=0, columnspan=2, sticky="ew", pady=15)
        btns = tk.Frame(parent, bg=ENTRY_BG)
        btns.grid(row=len(campos) + 12, column=1, sticky="e")
        create_button(btns, "Salvar Configurações", self._salvar_settings, row=0, side="left", small=True)
        create_button(btns, "Testar Conexão DB", self._testar_db_config, row=0, side="left", small=True)

        self.lbl_db_config = tk.Label(parent, text="", bg=ENTRY_BG, fg=SUBTEXT,
                                      font=("Segoe UI", 8), justify="left", anchor="w")
        self.lbl_db_config.grid(row=len(campos) + 13, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self._atualizar_status_db()

    def _build_downloads_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        tk.Label(parent, text="Downloads de Faturas", bg=ENTRY_BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        dl_btns = tk.Frame(parent, bg=ENTRY_BG)
        dl_btns.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        create_button(dl_btns, "Baixar faturas da Mais Internet",
                      lambda: self._run_downloader_thread("mais"), row=0, side="left", small=True)
        create_button(dl_btns, "Baixar faturas da Vero Internet",
                      lambda: self._run_downloader_thread("vero"), row=0, side="left", small=True)

        ttk.Separator(parent, orient="horizontal").grid(row=2, column=0, columnspan=2, sticky="ew", pady=15)
        tk.Label(parent, text="Claro (via Cookies)", bg=ENTRY_BG, fg=CLARO_COLOR,
                 font=("Segoe UI", 10, "bold")).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        link_font = ("Segoe UI", 9, "underline")
        link = tk.Label(parent, text="1. Clique aqui para abrir o portal da Claro, fazer login e ir para a página de contratos.", bg=ENTRY_BG, fg=ACCENT, cursor="hand2", font=link_font)
        link.grid(row=4, column=0, columnspan=2, sticky="w")
        link.bind("<Button-1>", lambda e: webbrowser.open_new("https://minhaclaroresidencial.claro.com.br/empresas/contratos"))
        tk.Label(parent, text="2. Com a página aberta, copie os cookies (veja o README para instruções detalhadas).", bg=ENTRY_BG, fg=SUBTEXT, font=("Segoe UI", 9)).grid(row=5, column=0, columnspan=2, sticky="w")
        create_button(parent, "3. Baixar faturas da Claro (usar cookies do clipboard)", lambda: self._run_downloader_thread("claro"), row=6, small=True)

    def _settings_from_vars(self):
        db_vars = self.settings_vars["database"]
        dl_vars = self.settings_vars["downloaders"]
        return {
            "database": {
                "driver": db_vars["driver"].get().strip(),
                "server": normalizar_servidor_sql(db_vars["server"].get()),
                "database": db_vars["database"].get().strip(),
                "username": db_vars["username"].get().strip(),
                "password": db_vars["password"].get(),
                "trust_server_certificate": bool(db_vars["trust_server_certificate"].get()),
            },
            "downloaders": {
                "mais": {
                    "txid": dl_vars["mais_txid"].get().strip(),
                    "password": dl_vars["mais_pass"].get(),
                },
                "vero": {
                    "username": dl_vars["vero_user"].get().strip(),
                    "password": dl_vars["vero_pass"].get(),
                },
                "claro": {
                    "document": dl_vars["claro_doc"].get().strip(),
                },
            }
        }

    def _atualizar_status_db(self):
        server = self.settings["database"].get("server") or "nao configurado"
        database = self.settings["database"].get("database") or "nao configurado"
        self.lbl_db_config.config(text=f"Config local: {server} / {database}")

    def _salvar_settings(self):
        self.settings = self._settings_from_vars()
        # Atualiza o campo de servidor normalizado na UI
        self.settings_vars["database"]["server"].set(self.settings["database"]["server"])
        caminho = save_settings(self.settings)
        self._atualizar_status_db()
        self._log(f"Configurações salvas em: {caminho}", "ok")

    def _testar_db_config(self):
        current_settings = self._settings_from_vars()
        db_config = current_settings["database"]
        self.settings_vars["database"]["server"].set(db_config["server"])
        try:
            testar_conexao(db_config)
        except Exception as erro:
            self._log(f"Falha ao conectar no DB: {erro}", "error")
            messagebox.showerror("DB", f"Falha ao conectar:\n{erro}")
            return

        self._log("Conexao com o DB testada com sucesso.", "ok")
        messagebox.showinfo("DB", "Conexao testada com sucesso.")

    def _build_status_bar(self):
        bar = tk.Frame(self.root, bg=PANEL, height=26)
        bar.grid(row=2, column=0, sticky="ew")
        self.status_var = tk.StringVar(value="Pronto")
        tk.Label(bar, textvariable=self.status_var, bg=PANEL, fg=SUBTEXT,
                 font=("Segoe UI", 8), anchor="w").pack(side="left", padx=12, pady=4)
        self.lbl_op = tk.Label(bar, text="", bg=PANEL, font=("Segoe UI", 8, "bold"))
        self.lbl_op.pack(side="right", padx=12)

    def _log(self, msg, tag=""):
        self.output.insert(tk.END, msg + "\n", tag)
        self.output.see(tk.END)

    def _clear_log(self):
        self.output.delete("1.0", tk.END)

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _update_stats(self):
        if not hasattr(self, "runner"):
            return
        self.lbl_total.config(text=str(self.runner._stats["total"]))
        self.lbl_ok.config(text=str(self.runner._stats["ok"]))
        self.lbl_fail.config(text=str(self.runner._stats["fail"]))

    def _json_por_operadora(self):
        return {
            "vero": self.dados_vero,
            "algar": self.dados_algar,
            "vivo": self.dados_vivo,
            "claro": self.dados_claro,
            "mais": self.dados_mais,
        }

    def _atualizar_status_json(self):
        for dados, lbl, nome in [
            (self.dados_vero, self.lbl_vero_json, "vero.json"),
            (self.dados_algar, self.lbl_algar_json, "algar.json"),
            (self.dados_vivo, self.lbl_vivo_json, "vivo.json"),
            (self.dados_claro, self.lbl_claro_json, "claro.json"),
            (self.dados_mais, self.lbl_mais_json, "mais.json"),
        ]:
            n = len(dados)
            lbl.config(
                text=f"✅ {nome} — {n} registros" if n else f"❌ {nome} — não encontrado",
                fg=SUCCESS if n else DANGER,
            )

    def _checar_jsons(self):
        faltando = [n for d, n in [
            (self.dados_vero, "vero.json"), (self.dados_algar, "algar.json"),
            (self.dados_vivo, "vivo.json"), (self.dados_claro, "claro.json"),
            (self.dados_mais, "mais.json"),
        ] if not d]
        if faltando:
            self._log(f"⚠️  JSON(s) não encontrado(s): {', '.join(faltando)}", "warn")
            self._log(f"   Coloque-os em: {APPDATA_DIR}", "sub")

    def _checar_faturas_temporarias(self):
        """Verifica se há PDFs na pasta temporária ao iniciar e pergunta ao usuário se quer carregá-los."""
        temp_dir = Path(APPDATA_DIR) / "temp_downloads"
        if not temp_dir.is_dir():
            return

        pdfs_encontrados = sorted([p for p in temp_dir.glob("*.pdf") if p.is_file()])

        if not pdfs_encontrados:
            return

        n_pdfs = len(pdfs_encontrados)
        resposta = messagebox.askyesno(
            "Faturas Anteriores Encontradas",
            f"Foram encontradas {n_pdfs} faturas na pasta de downloads da sessão anterior.\n\n"
            "Deseja carregá-las para processamento?"
        )
        if resposta:
            self.pdfs_baixados = pdfs_encontrados
            self._atualizar_ui_pos_download()
            self._log(f"ℹ️ {n_pdfs} faturas da sessão anterior foram carregadas.", "info")

    def _recarregar_jsons(self):
        self.dados_vero = carregar_json(JSON_VERO)
        self.dados_algar = carregar_json(JSON_ALGAR)
        self.dados_vivo = carregar_json(JSON_VIVO)
        self.dados_claro = carregar_json(JSON_CLARO)
        self.dados_mais = carregar_json(JSON_MAIS)
        self.runner.dados_por_operadora = self._json_por_operadora()
        self._atualizar_status_json()
        self._log("🔄 JSONs recarregados.", "info")

    def _abrir_pasta_appdata(self):
        os.startfile(APPDATA_DIR)

    def selecionar_pasta(self, path=None):
        if path is None:
            path = filedialog.askdirectory()
        if path:
            self.pasta_pdf = path
            self.pdfs_individuais = []
            self.usar_baixados.set(False)
            self.lbl_pasta.config(text=os.path.basename(path) or path, fg=TEXT)
            self._log(f"📂 Pasta: {path}", "info")

    def _on_drop(self, event):
        paths = parse_drop_data(self.root, event.data)
        if not paths:
            return

        if len(paths) == 1 and os.path.isdir(paths[0]):
            self.selecionar_pasta(paths[0])
            return

        pdfs_validos = []
        for p in paths:
            if os.path.isdir(p):
                self.selecionar_pasta(p)
                return
            if p.lower().endswith(".pdf"):
                pdfs_validos.append(p)
            else:
                self._log(f"⛔ arquivo incompativel, apenas pasta ou .pdf: {os.path.basename(p)}", "error")

        if pdfs_validos:
            self.pdfs_individuais = pdfs_validos
            self.pasta_pdf = ""
            self.usar_baixados.set(False)
            nomes = ", ".join(os.path.basename(p) for p in pdfs_validos[:3])
            sufixo = f" +{len(pdfs_validos)-3} mais" if len(pdfs_validos) > 3 else ""
            self.lbl_pasta.config(text=f"{len(pdfs_validos)} PDF(s): {nomes}{sufixo}", fg=ACCENT)
            self._log(f"📄 {len(pdfs_validos)} PDF(s) recebido(s) via drag-drop", "info")

    def _on_usar_baixados_toggle(self):
        if self.usar_baixados.get():
            self.pasta_pdf = ""
            self.pdfs_individuais = []
            self.lbl_pasta.config(text="Usando faturas baixadas da web", fg=ACCENT)
            self._log("ℹ️ Usando faturas baixadas da web para o processamento.", "info")
        else:
            self.lbl_pasta.config(text="Nenhuma selecionada", fg=TEXT)
            self._log("ℹ️ Seleção de faturas baixadas desmarcada.", "info")

    def _bind_drop(self, widget, highlight_widget=None):
        bind_drop(widget, self.root, self._on_drop, highlight_widget)

    def _run_downloader_thread(self, operadora):
        if operadora == "mais":
            creds = self.settings["downloaders"].get("mais", {})
            txid = creds.get("txid")
            password = creds.get("password")
            if not txid or not password:
                messagebox.showerror("Mais Internet", "Credenciais não configuradas. Por favor, vá até a aba 'Configurações'.")
                return
            downloader_cls = MaisDownloader
            args = (txid, password, self._log)
        elif operadora == "vero":
            creds = self.settings["downloaders"].get("vero", {})
            username = creds.get("username")
            password = creds.get("password")
            if not username or not password:
                messagebox.showerror("Vero Internet", "Credenciais não configuradas. Por favor, vá até a aba 'Configurações'.")
                return
            downloader_cls = VeroDownloader
            args = (username, password, self._log)
        elif operadora == "claro":
            creds = self.settings["downloaders"].get("claro", {})
            document = creds.get("document")
            if not document:
                messagebox.showerror("Claro", "CNPJ (Documento) não configurado. Por favor, vá até a aba 'Configurações'.")
                return
            try:
                cookie_json_str = self.root.clipboard_get()
                if not isinstance(cookie_json_str, str) or not cookie_json_str.strip().startswith('['):
                    messagebox.showerror("Claro - Cookies", "O conteúdo da área de transferência não parece ser um JSON de cookies válido.\n\nCopie o array de cookies da ferramenta de desenvolvedor do seu navegador.")
                    return
            except tk.TclError:
                messagebox.showerror("Claro - Cookies", "Área de transferência vazia ou com conteúdo inválido.\n\nCopie o array de cookies da ferramenta de desenvolvedor do seu navegador.")
                return
            contracts_list = []
            if not self.dados_claro:
                self._log("⚠️ claro.json não carregado ou vazio. Não é possível buscar contratos.", "warn")
            else:
                for item in self.dados_claro:
                    contrato_str = item.get("contrato", "")
                    if "/" in contrato_str and len(contrato_str.split("/")) == 2:
                        parts = contrato_str.split("/")
                        contracts_list.append((parts[0].strip(), parts[1].strip()))
            if not contracts_list:
                messagebox.showwarning("Claro", "Nenhum contrato válido (formato 'codigo/numero') encontrado no arquivo claro.json. O download não pode continuar.")
                return
            downloader_cls = ClaroDownloader
            args = (document, cookie_json_str, contracts_list, self._log)
        else:
            self._log(f"Downloader para '{operadora}' não implementado.", "error")
            return

        temp_dir = Path(APPDATA_DIR) / "temp_downloads"
        downloader = downloader_cls(*args)

        def run():
            novos_pdfs = downloader.baixar_faturas_em_aberto(temp_dir)
            self.pdfs_baixados = sorted(list(set(self.pdfs_baixados + novos_pdfs)))
            self.root.after(10, self._atualizar_ui_pos_download)
        threading.Thread(target=run, daemon=True).start()

    def _get_pdfs_para_processar(self):
        if self.pdfs_individuais:
            return [(os.path.basename(p), p) for p in self.pdfs_individuais]
        if self.pasta_pdf:
            return [
                (f, os.path.join(self.pasta_pdf, f))
                for f in os.listdir(self.pasta_pdf)
                if f.lower().endswith(".pdf")
            ]
        if self.usar_baixados.get() and self.pdfs_baixados:
            return [
                (os.path.basename(p), str(p))
                for p in self.pdfs_baixados
            ]
        return []

    def _atualizar_ui_pos_download(self):
        n_pdfs = len(self.pdfs_baixados)
        if n_pdfs > 0:
            self.check_usar_baixados.config(text=f"Usar {n_pdfs} faturas baixadas da web")
            self.check_usar_baixados.grid() # Mostra o checkbox
            self.usar_baixados.set(True)
            self._on_usar_baixados_toggle()
        else:
            self.check_usar_baixados.grid_remove() # Esconde se não baixou nada
            self.usar_baixados.set(False)

    def _on_macro_finish(self, usando_baixados):
        """Callback executado ao final da macro em massa para limpeza."""
        if usando_baixados:
            self.root.after(20, self._limpar_faturas_baixadas)

    def _limpar_faturas_baixadas(self):
        """Apaga os arquivos da pasta temporária e reseta a UI."""
        if not self.pdfs_baixados:
            return

        self._log("\nLimpando faturas temporárias baixadas...", "info")
        arquivos_apagados = 0
        for p in self.pdfs_baixados:
            try:
                if p.exists():
                    p.unlink()
                    arquivos_apagados += 1
            except Exception as e:
                self._log(f"   Erro ao apagar {p.name}: {e}", "error")

        self.pdfs_baixados = []
        self._atualizar_ui_pos_download()
        self.lbl_pasta.config(text="Nenhuma selecionada", fg=TEXT)

    def executar_macro_em_massa_thread(self):
        usando_baixados = self.usar_baixados.get()
        self.runner.executar_macro_em_massa_thread(self._get_pdfs_para_processar, usando_baixados)

    def definir_posicao(self, campo):
        self.root.withdraw()
        pyautogui.confirm(text=f'Posicione o mouse sobre "{campo}" e clique OK.',
                          title="Capturar posição", buttons=["OK"])
        pos = pyautogui.position()
        self.posicoes[campo] = pos
        self.inputs_manuais[campo][0].set(str(pos.x))
        self.inputs_manuais[campo][1].set(str(pos.y))
        self.root.deiconify()

    def get_posicao(self, campo):
        if self.usar_padrao.get():
            padroes = {"fornecedor": (2680, 170), "nota_fiscal": (2680, 190),
                       "confirmar": (3058, 825), "anexar": (2688, 229),
                       "anexar2": (2637, 147), "pgto": (2757, 598), "pgto2": (2729, 681)}
            return padroes.get(campo)
        if campo not in self.inputs_manuais:
            return self.posicoes.get(campo)
        x_var, y_var = self.inputs_manuais[campo]
        try:
            return (int(x_var.get()), int(y_var.get()))
        except ValueError:
            return self.posicoes.get(campo)

    def _set_pausa_programatica(self, pausar: bool):
        """Pausa ou retoma a macro via código, atualizando a UI."""
        self.pausado = pausar
        if self.pausado:
            self.lbl_pause.config(text="⏸  PAUSADO", fg=WARNING)
        else:
            self.lbl_pause.config(text="▶  RODANDO", fg=SUCCESS)

    def _prompt_usuario_decisao(self, titulo, mensagem):
        """Pausa a macro e mostra um pop-up para o usuário decidir se continua."""
        self._set_pausa_programatica(True)
        resposta = messagebox.askyesno(titulo, f"{mensagem}\n\nSim = Continuar\nNão = Parar")
        self._set_pausa_programatica(False)
        return resposta

    def toggle_pausa(self, event=None):
        self.pausado = not self.pausado
        if self.pausado:
            self.lbl_pause.config(text="⏸  PAUSADO", fg=WARNING)
            self._log("⏸️  Pausado — F8 para continuar.", "warn")
        else:
            self.lbl_pause.config(text="▶  RODANDO", fg=SUCCESS)
            self._log("▶️  Retomado.", "ok")

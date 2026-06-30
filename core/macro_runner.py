import json
import os
import re
import threading
import time

import pdfplumber
import pyautogui

from core.database import nota_ja_lancada
from core.reports import gerar_relatorio_excel, salvar_relatorio_prevoo
from extratores import EXTRACTOR_CLASSES
from extratores.detector import detectar_operadora


SENHAS_PDF = (None, "15523", "1552")
CORES_OPERADORAS = {
    "algar": "#138126",
    "vivo": "#9b59b6",
    "claro": "#e74c3c",
    "mais": "#C5C200",
    "vero": "#ff8c08",
}
CNPJS_FORNECEDORES = {
    "vero": "31748174010204",
    "algar": "71208516016178",
    "vivo": "02558157000162",
    "claro": "66970229003930",
    "mais": "11832927000104",
}


def abrir_pdf_com_fallback(caminho):
    ultimo_erro = None
    for senha in SENHAS_PDF:
        try:
            if senha is None:
                return pdfplumber.open(caminho)
            return pdfplumber.open(caminho, password=senha)
        except Exception as erro:
            ultimo_erro = erro
    raise ultimo_erro


def carregar_json(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
            return dados if isinstance(dados, list) else []
    except Exception:
        return []


def get_extractor(caminho, dados_json_por_operadora, log_fn):
    texto_amostra = ""
    try:
        with abrir_pdf_com_fallback(caminho) as pdf:
            for pagina in pdf.pages[:3]:
                texto_amostra += (pagina.extract_text() or "") + "\n"
                if len(texto_amostra) > 2000:
                    break
    except Exception as erro:
        log_fn(f"Erro lendo PDF: {caminho} | {erro}", "error")
        return None, "erro"

    texto_amostra = re.sub(r"\s+", " ", texto_amostra).upper()
    op = detectar_operadora(texto_amostra)
    extractor_cls = EXTRACTOR_CLASSES.get(op)
    if extractor_cls is None:
        log_fn(f"Operadora nao reconhecida no arquivo: {caminho}", "error")
        return None, "desconhecida"

    return extractor_cls(dados_json_por_operadora.get(op, []), log_fn), op


def _op_str(op):
    return {
        "algar": "ALGAR",
        "vivo": "VIVO",
        "claro": "CLARO",
        "mais": "MAIS",
        "vero": "VERO",
    }.get(op, str(op).upper())


def _op_color(op):
    return CORES_OPERADORAS.get(op, "#e8eaf0")


class MacroRunner:
    def __init__(
        self,
        log_fn,
        status_fn,
        stats_update_fn,
        op_label_fn,
        get_posicao_fn,
        dados_por_operadora,
        pause_check_fn,
        prompt_user_fn,
        on_finish_fn=None,
    ):
        self.log_fn = log_fn
        self.status_fn = status_fn
        self.stats_update_fn = stats_update_fn
        self.op_label_fn = op_label_fn
        self.get_posicao_fn = get_posicao_fn
        self.dados_por_operadora = dados_por_operadora
        self.pause_check_fn = pause_check_fn
        self.prompt_user_fn = prompt_user_fn
        self.on_finish_fn = on_finish_fn
        self.resultados = []
        self._stats = {"total": 0, "ok": 0, "fail": 0}

    def _get_extrator(self, caminho):
        return get_extractor(caminho, self.dados_por_operadora, self.log_fn)

    def _add_resultado(self, nome_pdf, op, status, dados, motivo=""):
        self.resultados.append({
            "PDF": nome_pdf,
            "Operadora": _op_str(op),
            "Status": status,
            "Nota Fiscal": dados.get("numero_nota") or "",
            "Valor": dados.get("valor") or "",
            "Cliente": dados.get("nome_cliente") or "",
            "Contrato": dados.get("numero_contrato") or "",
            "Emissao": dados.get("data_emissao") or "",
            "Vencimento": dados.get("data_vencimento") or "",
            "Motivo": motivo,
        })

    def gerar_relatorio_prevoo(self, pdfs_lista):
        pdfs_lista = pdfs_lista or []
        if not pdfs_lista:
            self.log_fn("Nenhum PDF ou pasta selecionada!", "error")
            return None

        self.log_fn(f"\n{'=' * 54}", "sub")
        self.log_fn(f"MODO RELATORIO - {len(pdfs_lista)} PDF(s)", "green")
        self.log_fn(f"{'=' * 54}", "sub")

        registros = []
        for i, (nome_pdf, caminho) in enumerate(pdfs_lista, 1):
            self.status_fn(f"Lendo {nome_pdf} ({i}/{len(pdfs_lista)})")
            extrator, op = self._get_extrator(caminho)
            if extrator is None:
                continue

            self.log_fn(f"\n[{i}/{len(pdfs_lista)}] {nome_pdf} [{_op_str(op)}]", "bold")
            reg = extrator.extrair_completo(nome_pdf, caminho)

            try:
                nota_fiscal = reg.get("Nota Fiscal (Nº)") or reg.get("Nota Fiscal (NÂº)")
                nff = reg.get("NFF")
                lancado = nota_ja_lancada(nota_fiscal, nff, op, self.log_fn)
                reg["Lancado no BD"] = "Sim" if lancado else "Nao"
            except Exception:
                reg["Lancado no BD"] = "Erro BD"

            registros.append(reg)
            status = reg.get("Status", "")
            tag = "ok" if "ok" in status.lower() or "sim" in status.lower() else "info"
            self.log_fn(
                f"   {status} | NFF: {reg.get('NFF') or '-'} | "
                f"R$ {reg.get('Valor Total (R$)') or '-'} | {reg.get('Nome (JSON)') or '-'}",
                tag,
            )

        self.log_fn(f"\n{'-' * 54}", "sub")
        self.log_fn("Salvando Excel...", "info")
        self.status_fn("Gerando relatorio...")
        caminho_xl = salvar_relatorio_prevoo(registros, output_dir=os.path.dirname(os.path.abspath(__file__)))
        self.log_fn(f"Relatorio salvo:\n   {caminho_xl}", "ok")
        self.status_fn("Relatorio gerado!")
        return caminho_xl

    def executar_macro_em_massa_thread(self, get_pdfs_fn, usando_baixados=False):
        self._stats = {"total": 0, "ok": 0, "fail": 0}
        self.stats_update_fn()
        threading.Thread(
            target=lambda: self.executar_macro_em_massa(get_pdfs_fn(), usando_baixados),
            daemon=True,
        ).start()

    def executar_macro_em_massa(self, pdfs_lista, usando_baixados=False):
        self.resultados.clear()
        pdfs_lista = pdfs_lista or []

        if not pdfs_lista:
            self.log_fn("Nenhuma pasta ou PDF selecionado!", "error")
            return None

        self.log_fn(f"\n{'-' * 52}", "sub")
        self.log_fn(f"Iniciando {len(pdfs_lista)} PDF(s).", "bold")
        self.log_fn(f"{'-' * 52}", "sub")

        for nome_pdf, caminho in pdfs_lista:
            while self.pause_check_fn():
                time.sleep(0.5)

            self._stats["total"] += 1
            self.stats_update_fn()
            self.status_fn(f"Processando {nome_pdf} ({self._stats['total']}/{len(pdfs_lista)})")

            extrator, op = self._get_extrator(caminho)
            if extrator is None:
                self._stats["fail"] += 1
                self.stats_update_fn()
                self._add_resultado(nome_pdf, op, "Falha", {}, "Operadora nao reconhecida ou PDF invalido")
                continue

            self.log_fn(f"\n{nome_pdf} [{_op_str(op)}]", "bold")
            self.op_label_fn(_op_str(op), _op_color(op))
            dados = extrator.extrair_macro(caminho)

            falhas = self._validar_dados_macro(op, dados)
            if falhas:
                self._stats["fail"] += 1
                self.stats_update_fn()
                motivo = "; ".join(falhas)
                self._add_resultado(nome_pdf, op, "Falha", dados, motivo)
                self.log_fn(f"   {motivo}", "error")
                continue

            nota = dados.get("numero_nota")
            nff = dados.get("nff") or dados.get("NFF")
            if nota_ja_lancada(nota, nff, op, self.log_fn):
                self._stats["ok"] += 1
                self.stats_update_fn()
                self._add_resultado(nome_pdf, op, "Ja lancada", dados, "Nota ja lancada anteriormente")
                self.log_fn(f"   Nota {nota} ja lancada. Pulando.", "ok")
                continue

            # Executa a automação e aguarda o lançamento no DB
            self._executar_automacao_erp(op, caminho, dados)
            lancado_com_sucesso = self._aguardar_lancamento_db(nota, nff, op)

            if lancado_com_sucesso:
                self._stats["ok"] += 1
                self.stats_update_fn()
                self._add_resultado(nome_pdf, op, "Processado", dados)
                self.log_fn("   ✅ Nota confirmada no banco.", "ok")
            else:
                self._stats["fail"] += 1
                self.stats_update_fn()
                # O motivo da falha (timeout ou parada do usuário) já foi logado em _aguardar_lancamento_db
                self._add_resultado(nome_pdf, op, "Falha no banco", dados, "Nota nao encontrada no banco apos lancamento")

        self.log_fn(f"\n{'-' * 52}", "sub")
        self.log_fn(f"Concluido: {self._stats['ok']} OK | {self._stats['fail']} falha(s)", "bold")
        self.status_fn("Concluido")
        caminho_xl = gerar_relatorio_excel(self.resultados, output_dir=os.path.dirname(os.path.abspath(__file__)))
        if caminho_xl:
            self.log_fn(f"Relatorio salvo: {caminho_xl}", "info")
        else:
            self.log_fn("Nenhum resultado para gerar relatório.", "warn")

        if self.on_finish_fn:
            self.on_finish_fn(usando_baixados)

        return caminho_xl

    @staticmethod
    def _validar_dados_macro(op, dados):
        falhas = []
        if not dados.get("numero_nota"):
            falhas.append("Nota fiscal nao encontrada")
        if not dados.get("valor"):
            falhas.append("Valor nao encontrado")
        if not dados.get("numero_contrato") or not dados.get("nome_cliente"):
            falhas.append("Contrato/cliente nao encontrado")
        if not dados.get("data_emissao"):
            falhas.append("Data de emissao nao encontrada")
        if not dados.get("data_vencimento"):
            falhas.append("Data de vencimento nao encontrada")
        if op in ("algar", "vivo", "claro") and not dados.get("codigo_barras"):
            falhas.append("Codigo de barras nao encontrado")
        return falhas

    def _aguardar_lancamento_db(self, nota, nff, op):
        """
        Espera e verifica o lançamento no DB em até 3 tentativas.
        Retorna True se lançado, False se o tempo esgotou ou o usuário parou.
        """
        tentativas = [
            {"espera": 1, "tentativa": 1},
            {"espera": 4, "tentativa": 2},
            {"espera": 4, "tentativa": 3},
        ]

        for config in tentativas:
            self.log_fn(f"   Aguardando {config['espera']}s para checar o DB (tentativa {config['tentativa']}/3)...", "sub")
            time.sleep(config["espera"])

            if nota_ja_lancada(nota, nff, op, self.log_fn):
                pyautogui.press("enter")
                pyautogui.press("enter")
                pyautogui.press("enter")
                pyautogui.press("right")
                pyautogui.press("right")
                pyautogui.press("enter")
                time.sleep(1)
                return True

        self.log_fn("   ❌ Servidor não respondeu após 3 tentativas.", "error")
        continuar = self.prompt_user_fn(
            "Servidor não respondeu",
            "O lançamento da nota não foi confirmado no banco de dados após 3 tentativas.\n\n"
            "Deseja continuar com a macro mesmo assim ou parar o processo?"
        )

        if not continuar:
            self.log_fn("   🛑 Usuário optou por parar a execução.", "error")
        return False

    def _executar_automacao_erp(self, op, caminho, dados):
        nota = dados["numero_nota"]
        valor = dados["valor"]
        emissao = dados["data_emissao"]
        venc = dados["data_vencimento"]
        contrato = dados["numero_contrato"]
        cliente = dados["nome_cliente"]
        cod_barras = dados.get("codigo_barras")

        self.log_fn(f"   Nota: {nota} | R$ {valor} | {cliente}", "sub")
        self.log_fn(f"   Emissao: {emissao} | Venc: {venc}", "sub")
        time.sleep(1)

        pyautogui.click(self.get_posicao_fn("fornecedor"))
        pyautogui.typewrite(CNPJS_FORNECEDORES.get(op, CNPJS_FORNECEDORES["vero"]))
        for _ in range(3):
            pyautogui.press("enter")
            time.sleep(1)

        pyautogui.typewrite(nota)
        pyautogui.press("enter")
        pyautogui.typewrite("1")
        pyautogui.press("enter")
        pyautogui.typewrite("62")
        pyautogui.press("enter")
        pyautogui.press("enter")
        pyautogui.typewrite("2303")
        for _ in range(3):
            pyautogui.press("enter")
        pyautogui.press("enter")
        pyautogui.typewrite(emissao)
        for _ in range(4):
            pyautogui.press("enter")
        time.sleep(0.3)
        pyautogui.typewrite(valor)
        for _ in range(46):
            pyautogui.press("tab")
        pyautogui.press("enter")
        pyautogui.press("enter")
        pyautogui.typewrite("Contrato " + contrato)
        pyautogui.hotkey("ctrl", "enter")
        pyautogui.typewrite(cliente)
        pyautogui.press("enter")

        if cod_barras:
            pyautogui.typewrite(cod_barras)
            pyautogui.press("enter")

        pyautogui.click(self.get_posicao_fn("anexar2"))
        pyautogui.press("enter")
        pyautogui.typewrite(caminho)
        pyautogui.press("enter")
        time.sleep(0.3)
        pyautogui.press("enter")

        pyautogui.click(self.get_posicao_fn("pgto"))
        pyautogui.click(self.get_posicao_fn("pgto2"))
        pyautogui.press("enter")
        pyautogui.press("enter")
        pyautogui.typewrite(venc)
        for _ in range(4):
            pyautogui.press("enter")
        for _ in range(11):
            pyautogui.press("enter")
            time.sleep(0.1)

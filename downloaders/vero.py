import re
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "https://verointernet.com.br/cypher"
CRM_HEADER = "objectiveng"

HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "CRM": CRM_HEADER,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/148.0.0.0 Safari/537.36"
    ),
}


class VeroDownloader:
    def __init__(self, username, password, log_fn):
        self.username = username
        self.password = password
        self.log = log_fn
        self.session = requests.Session()
        self.session.headers.update(HEADERS_BASE)
        self.token = None

    def _login(self):
        self.log("🔐 Fazendo login na Vero Internet...", "info")
        try:
            resp = self.session.post(
                f"{BASE_URL}/auth/authenticate",
                json={"username": self.username, "password": self.password},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data["access_token"]
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            self.log("✅ Login realizado com sucesso.", "ok")
            return True
        except requests.HTTPError as e:
            self.log(f"❌ Erro de login (HTTP {e.response.status_code}): {e.response.text}", "error")
        except Exception as e:
            self.log(f"❌ Falha inesperada no login: {e}", "error")
        return False

    def _listar_faturas(self):
        self.log("📋 Buscando lista de faturas...", "info")
        try:
            resp = self.session.get(f"{BASE_URL}/financeiro/{self.username}/faturas", timeout=30)
            resp.raise_for_status()
            faturas = resp.json()
            faturas_abertas = [f for f in faturas if f.get("status") == "Aberto"]
            self.log(f"📦 {len(faturas_abertas)} faturas em aberto encontradas.", "info")
            return faturas_abertas
        except Exception as e:
            self.log(f"❌ Erro ao listar faturas: {e}", "error")
            return []

    def _baixar_pdf(self, fatura, destino):
        id_fatura = fatura["idFatura"]
        vencimento = fatura["dataVencimento"]
        valor = fatura.get("valor", 0)
        contrato = fatura.get("descricaoContrato", "").strip()
        contrato_sanitizado = re.sub(r'[\\/*?:"<>|]', "-", contrato) if contrato else f"ID{id_fatura}"
        nome_arquivo = f"{vencimento}_{contrato_sanitizado}_R${valor:.2f}_{id_fatura}.pdf"
        caminho = destino / nome_arquivo

        if caminho.exists():
            self.log(f"  ⏭️ Já existe: {nome_arquivo}", "sub")
            return caminho

        self.log(f"   Contrato: {contrato} | Venc: {vencimento} | R$ {valor:.2f}", "sub")
        try:
            resp = self.session.get(f"{BASE_URL}/veroapi/financeiro/fatura/{id_fatura}/exportar-pdf", timeout=60)
            resp.raise_for_status()
            pdf_bytes = bytes(resp.json())
            with open(caminho, "wb") as f:
                f.write(pdf_bytes)
            tamanho = caminho.stat().st_size
            self.log(f"  ✅ {nome_arquivo} ({tamanho / 1024:.1f} KB)", "ok")
            return caminho
        except Exception as e:
            self.log(f"  ❌ Erro ao baixar fatura {id_fatura}: {e}", "error")
            return None

    def baixar_faturas_em_aberto(self, pasta_destino: Path):
        if not self._login():
            return []

        faturas_abertas = self._listar_faturas()
        if not faturas_abertas:
            self.log("✅ Nenhuma fatura em aberto encontrada.", "ok")
            return []

        self.log(f"⬇️ Baixando {len(faturas_abertas)} fatura(s) em aberto...", "info")
        pasta_destino.mkdir(parents=True, exist_ok=True)
        arquivos_baixados = []

        for i, fatura in enumerate(faturas_abertas, 1):
            self.log(f"[{i}/{len(faturas_abertas)}]", "sub")
            caminho = self._baixar_pdf(fatura, pasta_destino)
            if caminho:
                arquivos_baixados.append(caminho)

        self.log(f"🏁 Download concluído: {len(arquivos_baixados)} faturas salvas.", "ok")
        return arquivos_baixados
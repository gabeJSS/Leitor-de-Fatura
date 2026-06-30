import requests
from datetime import datetime
from pathlib import Path

DOMAIN = "portal.maisinternet.net.br"
BASE_URL = f"https://{DOMAIN}/api"

HEADERS_BASE = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "origin": f"https://{DOMAIN}",
    "referer": f"https://{DOMAIN}/login",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "x-is-human": '{"b":0,"v":0.5,"d":0,"vr":"3"}',
}


class MaisDownloader:
    def __init__(self, txid, password, log_fn):
        self.txid = txid
        self.password = password
        self.log = log_fn
        self.session = requests.Session()
        self.token = None

    def _login(self):
        """Faz login e armazena o Bearer token."""
        self.log("🔐 Fazendo login na Mais Internet...", "info")

        headers = {**HEADERS_BASE, "content-type": "application/json", "x-method": "POST", "x-path": "/api/auth"}
        payload = {"txId": self.txid, "password": self.password, "domain": DOMAIN, "recaptchaToken": None}

        try:
            resp = self.session.post(f"{BASE_URL}/auth", headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            self.token = data["token"]
            expires = data.get("expiresIn", 300)
            self.log(f"✅ Login OK (token expira em {expires}s)", "ok")
            return True
        except requests.HTTPError as e:
            self.log(f"❌ Erro de login (HTTP {e.response.status_code}): {e.response.text}", "error")
        except Exception as e:
            self.log(f"❌ Falha inesperada no login: {e}", "error")
        return False

    def _listar_faturas(self, mes=None, ano=None):
        """Busca e filtra faturas."""
        self.log("📋 Buscando lista de faturas...", "info")
        headers = {**HEADERS_BASE, "authorization": f"Bearer {self.token}", "referer": f"https://{DOMAIN}/invoices", "x-method": "GET", "x-path": "/api/invoices/all"}

        try:
            resp = self.session.get(f"{BASE_URL}/invoices/all", headers=headers, timeout=30)
            resp.raise_for_status()
            faturas = resp.json()
            self.log(f"📦 {len(faturas)} faturas encontradas no histórico.", "info")

            if mes is None and ano is None: # Apenas em aberto
                return [f for f in faturas if not f.get("paid")]

            resultado = []
            for f in faturas:
                due = f.get("dueDate", "")
                if not due: continue
                try:
                    dt = datetime.fromisoformat(due.replace("Z", ""))
                except ValueError:
                    continue
                if ano is not None and dt.year != ano: continue
                if mes is not None and dt.month != mes: continue
                resultado.append(f)
            return resultado
        except Exception as e:
            self.log(f"❌ Erro ao listar faturas: {e}", "error")
            return []

    def _baixar_pdf(self, fatura, destino):
        """Baixa o PDF de uma fatura."""
        invoice_id = fatura["id"]
        referencia = fatura.get("reference", invoice_id)
        vencimento = fatura.get("dueDate", "")[:10]
        valor = fatura.get("finalAmount", 0)
        pago = "PAGO" if fatura.get("paid") else "ABERTO"
        nome_arquivo = f"{vencimento}_{referencia}_{pago}_R${valor:.2f}.pdf".replace("/", "-")
        caminho = destino / nome_arquivo

        if caminho.exists():
            self.log(f"  ⏭️ Já existe: {nome_arquivo}", "sub")
            return caminho

        headers = {**HEADERS_BASE, "accept": "*/*", "authorization": f"Bearer {self.token}", "referer": f"https://{DOMAIN}/invoices", "x-method": "GET", "x-path": f"/api/invoices/{invoice_id}/pdf"}

        try:
            resp = self.session.get(f"{BASE_URL}/invoices/{invoice_id}/pdf", headers=headers, timeout=60, stream=True)
            resp.raise_for_status()
            with open(caminho, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            tamanho = caminho.stat().st_size
            self.log(f"  ✅ {nome_arquivo} ({tamanho / 1024:.1f} KB)", "ok")
            return caminho
        except Exception as e:
            self.log(f"  ❌ Erro ao baixar fatura {invoice_id}: {e}", "error")
            return None

    def baixar_faturas_em_aberto(self, pasta_destino: Path):
        """
        Conecta, baixa todas as faturas em aberto e retorna os caminhos dos arquivos.
        """
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
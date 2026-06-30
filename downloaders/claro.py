import json
from pathlib import Path

import requests


class ClaroDownloader:
    """Baixa faturas em aberto do portal 'Minha Claro Empresas' usando cookies."""

    def __init__(self, document, cookie_json_str, contracts, log_fn):
        """
        Inicializa o downloader.
        :param document: CNPJ da empresa.
        :param cookie_json_str: String JSON contendo os cookies copiados do navegador.
        :param contracts: Lista de tuplas (operator_code, contract_number).
        :param log_fn: Função para logar mensagens na UI.
        """
        self.document = document
        self.cookie_json_str = cookie_json_str
        self.contracts = contracts
        self.log = log_fn
        self.session = requests.Session()
        self.token = None

    def _get_token_from_cookies(self):
        """Extrai o token de autenticação 'mc.token.sso' do JSON de cookies."""
        self.log("🍪 Extraindo token dos cookies...", "info")
        try:
            cookies_data = json.loads(self.cookie_json_str)
            cookies_list = cookies_data if isinstance(cookies_data, list) else [cookies_data]

            for cookie in cookies_list:
                if cookie.get("name") == "mc.token.sso":
                    self.token = cookie.get("value")
                    self.log("✅ Token SSO da Claro encontrado.", "ok")
                    return True

            self.log("❌ Token 'mc.token.sso' não encontrado no JSON de cookies.", "error")
            return False
        except json.JSONDecodeError:
            self.log("❌ O texto na área de transferência não é um JSON de cookies válido.", "error")
            return False
        except Exception as e:
            self.log(f"❌ Erro inesperado ao processar cookies: {e}", "error")
            return False

    def baixar_faturas_em_aberto(self, pasta_destino: Path):
        """
        Processo principal: extrai token, itera sobre contratos e baixa faturas abertas.
        """
        if not self._get_token_from_cookies():
            return []

        base_headers = {
            "Authorization": f"Bearer {self.token}",
            "client-id": "SITERES",
            "x-client-key": "l8FrGMcQYHBnXwILRfuxF6uJk8tekwHz",
        }
        self.session.headers.update(base_headers)

        pasta_destino.mkdir(parents=True, exist_ok=True)
        arquivos_baixados = []

        self.log(f"🔎 Verificando {len(self.contracts)} contratos da Claro...", "info")

        for i, (operator_code, contract_number) in enumerate(self.contracts, 1):
            self.log(f"[{i}/{len(self.contracts)}] Consultando {operator_code}/{contract_number}", "sub")

            try:
                invoices = self._listar_faturas(operator_code, contract_number)
                abertas = [inv for inv in invoices if inv.get("status") != 2]  # status 2 = PAGO

                if not abertas:
                    self.log("  Nenhuma fatura em aberto.", "sub")
                    continue

                self.log(f"  Encontradas {len(abertas)} faturas em aberto.", "sub")
                for invoice in abertas:
                    caminho = self._baixar_pdf(invoice, operator_code, contract_number, pasta_destino)
                    if caminho:
                        arquivos_baixados.append(caminho)

            except Exception as e:
                self.log(f"  ❌ Erro ao processar contrato {operator_code}/{contract_number}: {e}", "error")

        self.log(f"🏁 Download da Claro concluído: {len(arquivos_baixados)} faturas salvas.", "ok")
        return arquivos_baixados

    def _listar_faturas(self, operator_code, contract_number):
        """Busca a lista de faturas para um contrato específico."""
        querystring = f"document={self.document}&operatorCode={operator_code}&contractNumber={contract_number}"
        headers = {"Accept": "application/json", "x-querystring": querystring}

        resp = self.session.get(
            "https://api.claro.com.br/residential/v2/customer-bill/invoices",
            headers=headers, timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("data", {}).get("invoices", [])

    def _baixar_pdf(self, invoice, operator_code, contract_number, destino):
        """Baixa o arquivo PDF de uma fatura."""
        invoice_id, valor, vencimento = invoice["invoiceId"], invoice["amount"], invoice["dueDate"]
        nome_arquivo = f"CLARO_{operator_code}-{contract_number}_{vencimento}_R${valor:.2f}_{invoice_id}.pdf"
        caminho = destino / nome_arquivo

        if caminho.exists():
            self.log(f"  ⏭️ Já existe: {nome_arquivo}", "sub")
            return caminho

        self.log(f"    Baixando {invoice_id} (R$ {valor:.2f}) venc. {vencimento}", "sub")
        querystring = f"document={self.document}&operatorCode={operator_code}&contractNumber={contract_number}"
        pdf_headers = {"Accept": "application/pdf", "x-operation-type": "download-invoice", "x-querystring": querystring}
        pdf_url = f"https://api.claro.com.br/residential/v2/customer-bill/bills/{invoice_id}?documentType=INVOICE"
        pdf_resp = self.session.get(pdf_url, headers=pdf_headers, timeout=60)

        if pdf_resp.status_code != 200:
            self.log(f"    ❌ Erro {pdf_resp.status_code} ao baixar fatura {invoice_id}: {pdf_resp.text[:200]}", "error")
            return None

        with open(caminho, "wb") as f:
            f.write(pdf_resp.content)
        self.log(f"    ✅ {caminho.name} ({caminho.stat().st_size / 1024:.1f} KB)", "ok")
        return caminho
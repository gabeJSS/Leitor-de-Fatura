import re
from PyPDF2 import PdfReader

class ExtractorMais:
    """Leitura e parsing de PDFs da Mais Internet."""

    def __init__(self, dados_json, log_fn):
        self.dados_json = dados_json
        self._log = log_fn

    def texto_pdf(self, caminho):
        reader = PdfReader(caminho)
        return re.sub(r"\s+", " ", "".join(p.extract_text() or "" for p in reader.pages))

    def rx(self, texto, pattern):
        try:
            m = re.search(pattern, texto, re.IGNORECASE)
            if m: return m.group(1).strip()
        except Exception: pass
        return None

    def numero_nota(self, texto):
        for p in [r"N[°º]\s*NFCOM[:\s]+(\d{4,8})",
                  r"NFCOM:\s*(\d{4,8})"]:
            v = self.rx(texto, p)
            if v: return v
        return None

    def nf_documento(self, texto):
        _val = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
        # Boleto: "Nº do Documento FAT..." — limita o token a dígitos após FAT
        v = self.rx(texto, r"N[°º]\s*do\s*Documento\s+(FAT\d+)")
        if v: return v
        # Fatura paga: token FAT com dígitos isolado no texto
        v = self.rx(texto, r"\b(FAT\d{10,})\b")
        return v

    def valor(self, texto):
        _val = r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})"
        # Boleto: "Valor Documento R$ 514,01"
        m = re.search(rf"Valor Documento\s*R\$\s*{_val}", texto, re.IGNORECASE)
        if m: return m.group(1)
        # Fatura paga: "VENCIMENTO VALOR dd/mm/aaaa R$ 209,80"
        # (extração linear junta os dois rótulos antes dos valores)
        m = re.search(rf"VENCIMENTO\s+VALOR\s+\d{{2}}/\d{{2}}/\d{{4}}\s+R\$\s*{_val}", texto, re.IGNORECASE)
        if m: return m.group(1)
        # Fallback genérico: "VALOR R$ 209,80"
        m = re.search(rf"VALOR\s+R\$\s*{_val}", texto, re.IGNORECASE)
        if m: return m.group(1)
        return None

    def data_emissao(self, texto):
        # Boleto: "Data do Documento 03/06/2026"
        raw = self.rx(texto, r"Data do Documento\s+(\d{2}/\d{2}/\d{4})")
        if not raw:
            # NFCom: "Emissão: 29/05/2026"
            raw = self.rx(texto, r"Emiss[aã]o:\s*(\d{2}/\d{2}/\d{4})")
        return (raw, raw.replace("/", "")) if raw else (None, None)

    def data_vencimento(self, texto):
        # Fatura paga: "VENCIMENTO VALOR 09/06/2026 R$ ..." — data vem APÓS os dois rótulos
        m = re.search(r"VENCIMENTO\s+VALOR\s+(\d{2}/\d{2}/\d{4})", texto, re.IGNORECASE)
        if m:
            raw = m.group(1)
            return (raw, raw.replace("/", ""))
        # Boleto / cabeçalho normal: "VENCIMENTO 18/06/2026"
        raw = self.rx(texto, r"VENCIMENTO\s+(\d{2}/\d{2}/\d{4})")
        return (raw, raw.replace("/", "")) if raw else (None, None)

    def contrato(self, texto):
        return self.rx(texto, r"Contrato:\s*(\d+)")

    def chave_acesso(self, texto):
        return self.rx(texto, r"Chave de acesso:\s*([\d\s]+)")

    def protocolo(self, texto):
        return self.rx(texto, r"Protocolo de autoriza[cç][aã]o:\s*([\d\s\-]+)")

    def codigo_barras(self, texto):
        texto = re.sub(r'\(cid:\d+\)', ' ', texto).replace('\xa0', ' ')
        texto = re.sub(r'\s+', ' ', texto).strip()
        m = re.search(r'(\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{14})', texto)
        if m: return re.sub(r'\D', '', m.group(1))
        m = re.search(r'\d{44,48}', texto)
        if m: return m.group(0)
        return None

    def buscar_json(self, contrato):
        if not contrato or not self.dados_json: return None, None, None
        for item in self.dados_json:
            if not isinstance(item, dict): continue
            if str(item.get("contrato", "")).strip() == str(contrato).strip():
                return str(contrato), item.get("nome", ""), item
        return None, None, None

    def extrair_completo(self, nome_pdf, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception as e: return self._vazio(nome_pdf, str(e))

        nfcom       = self.numero_nota(texto)
        nf_doc      = self.nf_documento(texto)
        valor_total = self.valor(texto)
        em_raw, _   = self.data_emissao(texto)
        vc_raw, _   = self.data_vencimento(texto)
        contrato    = self.contrato(texto)
        chave       = self.chave_acesso(texto)
        proto       = self.protocolo(texto)

        contrato_json, nome_json, extra_json = self.buscar_json(contrato)
        campos_ok = all([nfcom, valor_total, contrato, vc_raw])
        if not contrato:        status = "❌ Contrato não encontrado"
        elif not nome_json:     status = "⚠️ Sem match no JSON"
        elif not campos_ok:     status = "⚠️ Dados incompletos"
        else:                   status = "✅ OK"

        reg = {
            "Operadora": "Mais Internet", "PDF": nome_pdf, "Status": status,
            "Nota Fiscal (Nº)": nfcom or "", "NFF": nf_doc or "",
            "Fatura Numerada": "", "Série": "0",
            "Data Emissão": em_raw or "", "Vencimento": vc_raw or "",
            "Referência (mês/ano)": "", "Valor Total (R$)": valor_total or "",
            "Itens da Fatura": "", "Código do Cliente": contrato or "",
            "CNPJ/CPF Cliente": "", "IE Cliente": "", "Telefone": "",
            "Município": "Florianópolis/SC", "Endereço": "",
            "Contrato (JSON)": contrato_json or "", "Nome (JSON)": nome_json or "",
            "Chave de Acesso": (chave or "").strip(),
            "Protocolo de Autorização": (proto or "").strip(),
        }
        if extra_json:
            for k, v in extra_json.items():
                if k not in ("contrato", "nome"): reg[f"JSON › {k}"] = str(v)
        return reg

    def extrair_macro(self, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception: return {}
        nfcom         = self.numero_nota(texto)
        _, em_fmt     = self.data_emissao(texto)
        _, vc_fmt     = self.data_vencimento(texto)
        valor         = self.valor(texto)
        contrato      = self.contrato(texto)
        _, nome, _    = self.buscar_json(contrato)
        cod_barras    = self.codigo_barras(texto)
        return {"numero_nota": nfcom, "valor": valor, "data_emissao": em_fmt,
                "data_vencimento": vc_fmt, "numero_contrato": contrato,
                "nome_cliente": nome, "codigo_barras": cod_barras}

    def _vazio(self, nome_pdf, motivo):
        base = {"Operadora": "Mais Internet", "PDF": nome_pdf, "Status": f"❌ Erro: {motivo}"}
        for k in ["Nota Fiscal (Nº)", "NFF", "Fatura Numerada", "Série", "Data Emissão",
                  "Vencimento", "Referência (mês/ano)", "Valor Total (R$)", "Itens da Fatura",
                  "Código do Cliente", "CNPJ/CPF Cliente", "IE Cliente", "Telefone", "Município",
                  "Endereço", "Contrato (JSON)", "Nome (JSON)", "Chave de Acesso",
                  "Protocolo de Autorização"]:
            base[k] = ""
        return base
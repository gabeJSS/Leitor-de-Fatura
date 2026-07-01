import re
from PyPDF2 import PdfReader

class ExtractorVero:
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
        except Exception as e:
            self.log(f"Regex falhou: {e}", "warn")
        return None

    def numero_nota(self, texto): return self.rx(texto, r"Nº:\s*(\d+)")

    def valor(self, texto):
        for p in [r"TOTAL\s+R\$\s*([\d\.\,]+)",
                  r"TOTAL A PAGAR:\s*R\$\s*([\d\.\,]+)",
                  r"R\$\s*([\d\.\,]+)"]:
            v = self.rx(texto, p)
            if v: return v
        return None

    def data_emissao(self, texto):
        raw = self.rx(texto, r"(?:Emiss[aã]o|DATA DE EMISS[AÃ]O):\s*(\d{2}/\d{2}/\d{4})")
        return (raw, raw.replace("/", "")) if raw else (None, None)

    def data_vencimento(self, texto):
        for p in [r"VENCIMENTO:\s*(\d{2}/\d{2}/\d{4})",
                  r"Vencimento[:\s]+(\d{2}/\d{2}/\d{4})"]:
            m = re.search(p, texto, re.IGNORECASE)
            if m: raw = m.group(1); return raw, raw.replace("/", "")
        return None, None

    def cod_cliente(self, texto): return self.rx(texto, r"CÓDIGO DO CLIENTE:\s*(\d+)")

    def buscar_json(self, cod):
        if not cod or not self.dados_json: return None, None, None
        for item in self.dados_json:
            if not isinstance(item, dict): continue
            if str(item.get("contrato","")).strip() == str(cod).strip():
                return str(cod), item.get("nome",""), item
        return None, None, None

    def extrair_completo(self, nome_pdf, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception as e: return self._vazio(nome_pdf, str(e))

        numero_nota     = self.rx(texto, r"Nº:\s*(\d+)")
        nota_fatura_nff = self.rx(texto, r"NOTA FISCAL FATURA N°\s*(\d+)")
        fatura_num      = self.rx(texto, r"Fatura Numerada\s+Nº:\s*(\d+)")
        serie           = self.rx(texto, r"SÉRIE:\s*(\d+)")
        valor_total     = self.valor(texto)
        data_em_raw     = self.rx(texto, r"(?:Emiss[aã]o|DATA DE EMISS[AÃ]O):\s*(\d{2}/\d{2}/\d{4})")
        data_vc_raw     = (self.rx(texto, r"VENCIMENTO:\s*(\d{2}/\d{2}/\d{4})") or
                           self.rx(texto, r"Vencimento[:\s]+(\d{2}/\d{2}/\d{4})"))
        referencia      = self.rx(texto, r"REFERÊNCIA\s*\(MÊS/ANO\):\s*(\d{2}/\d{4})")
        cod             = self.rx(texto, r"CÓDIGO DO CLIENTE:\s*(\d+)")
        cnpj            = self.rx(texto, r"CNPJ/CPF:\s*([\d\.\-/]+)")
        ie              = self.rx(texto, r"INSCRIÇÃO ESTADUAL:\s*(\d+)")
        tel             = self.rx(texto, r"N°\s*TELEFONE:\s*([\(\d\s\)]+)")
        municipio       = self.rx(texto, r"Município:\s*([\w\s]+?)(?:\.|$)")
        chave           = self.rx(texto, r"CHAVE DE ACESSO:\s*([\d\s]+)")
        protocolo       = self.rx(texto, r"Protocolo de Autorização:\s*([\d\s\-]+)")
        endereco = ""
        try:
            m = re.search(r"((?:R\w*|AV\w*|RUA|AVENIDA|TRAVESSA)\s+[\w\s]+,\s*\d+[^•\n]{5,80})", texto, re.IGNORECASE)
            if m: endereco = m.group(1).strip()
        except Exception as e:
            self.log(f"Erro ao extrair endereco: {e}", "warn")
        itens_str = ""
        try:
            itens = re.findall(r"(VERO[\w\s\-]+?|B2B[\w\s\-]+?)\s+UN\s+1\s+R\$\s*([\d\.,]+)", texto, re.IGNORECASE)
            if itens: itens_str = " | ".join(f"{n.strip()} R${v}" for n, v in itens)
        except Exception as e:
            self.log(f"Erro ao extrair itens da fatura: {e}", "warn")

        contrato_json, nome_json, extra_json = self.buscar_json(cod)
        campos_ok = all([numero_nota or nota_fatura_nff, valor_total, cod, data_vc_raw])
        if not cod: status = "❌ Código cliente não encontrado"
        elif not nome_json: status = "⚠️ Sem match no JSON"
        elif not campos_ok: status = "⚠️ Dados incompletos"
        else: status = "✅ OK"

        reg = {
            "Operadora":"Vero","PDF":nome_pdf,"Status":status,
            "Nota Fiscal (Nº)":numero_nota or "","NFF":nota_fatura_nff or "",
            "Fatura Numerada":fatura_num or "","Série":serie or "",
            "Data Emissão":data_em_raw or "","Vencimento":data_vc_raw or "",
            "Referência (mês/ano)":referencia or "","Valor Total (R$)":valor_total or "",
            "Itens da Fatura":itens_str,"Código do Cliente":cod or "",
            "CNPJ/CPF Cliente":cnpj or "","IE Cliente":ie or "",
            "Telefone":(tel or "").strip(),"Município":(municipio or "").strip(),
            "Endereço":endereco,"Contrato (JSON)":contrato_json or "",
            "Nome (JSON)":nome_json or "","Chave de Acesso":(chave or "").strip(),
            "Protocolo de Autorização":(protocolo or "").strip(),
        }
        if extra_json:
            for k, v in extra_json.items():
                if k not in ("contrato","nome"): reg[f"JSON › {k}"] = str(v)
        return reg

    def extrair_macro(self, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception as e:
            self.log(f"Erro ao extrair dados para macro: {e}", "error")
            return {}
        nota = self.numero_nota(texto)
        _, emissao_fmt = self.data_emissao(texto)
        _, venc_fmt    = self.data_vencimento(texto)
        valor = self.valor(texto)
        cod   = self.cod_cliente(texto)
        _, nome, _ = self.buscar_json(cod)
        return {"numero_nota":nota,"valor":valor,"data_emissao":emissao_fmt,
                "data_vencimento":venc_fmt,"numero_contrato":cod,"nome_cliente":nome}

    def _vazio(self, nome_pdf, motivo):
        base = {"Operadora":"Vero","PDF":nome_pdf,"Status":f"❌ Erro: {motivo}"}
        for k in ["Nota Fiscal (Nº)","NFF","Fatura Numerada","Série","Data Emissão",
                  "Vencimento","Referência (mês/ano)","Valor Total (R$)","Itens da Fatura",
                  "Código do Cliente","CNPJ/CPF Cliente","IE Cliente","Telefone","Município",
                  "Endereço","Contrato (JSON)","Nome (JSON)","Chave de Acesso","Protocolo de Autorização"]:
            base[k] = ""
        return base

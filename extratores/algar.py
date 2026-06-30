import re
from PyPDF2 import PdfReader
import pdfplumber

class ExtractorAlgar:
    def __init__(self, dados_json, log_fn):
        self.dados_json = dados_json
        self._log = log_fn

    def texto_pdf(self, caminho):
        with pdfplumber.open(caminho) as pdf:
            partes = [p.extract_text() or "" for p in pdf.pages]
        return re.sub(r"\s+", " ", "\n".join(partes))

    def rx(self, texto, pattern):
        try:
            m = re.search(pattern, texto, re.IGNORECASE)
            if m: return m.group(1).strip()
        except Exception: pass
        return None

    def numero_nota(self, texto):
        for p in [r"N[\u00ba\u00b0]?\s*da\s*fatura\s*[:\-]?\s*(\d{5,})",
                  r"FATURA:\s*(\d{5,})",r"N[\u00ba\u00b0]\s*DA\s*FATURA:\s*(\d{5,})",
                  r"N[\u00ba\u00b0]\s*da\s*fatura\s+(\d{5,})",r"fatura[^\d]*(\d{8,10})"]:
            v = self.rx(texto, p)
            if v: return v
        return None

    def valor(self, texto):
        for p in [r"Valor total da conta\s*R\$\s*([\d\.,]+)",
                  r"TOTAL DA FATURA ALGAR\s*R\$\s*([\d\.,]+)",
                  r"TOTAL\s*A\s*PAGAR\s*R?\$?\s*([0-9.,]{4,12})",
                  r"TOTAL[^R$]{0,15}R\$\s*([0-9.,]{4,12})"]:
            v = self.rx(texto, p)
            if v: return v.replace(".", ",") if "." in v and "," not in v else v
        return None

    def data_emissao(self, texto):
        for p in [r"EMISS[A\u00c3]O DESTA CONTA:\s*(\d{2}/\d{2}/\d{4})",
                  r"EMISS[A\u00c3]O:\s*(\d{2}/\d{2}/\d{4})",
                  r"Emiss[a\u00e3]o:\s*(\d{2}/\d{2}/\d{4})",
                  r"EMISS[A\u00c3]O[\s:]+(\d{2}/\d{2}/\d{4})"]:
            raw = self.rx(texto, p)
            if raw: return raw, raw.replace("/","")
        return None, None

    def data_vencimento(self, texto):
        meses = {"jan":"01","fev":"02","mar":"03","abr":"04","mai":"05","jun":"06",
                 "jul":"07","ago":"08","set":"09","out":"10","nov":"11","dez":"12"}
        m = re.search(r"Data de vencimento\s*(\d{1,2})\s*/\s*([a-z]{3})\s*/\s*(\d{4})", texto, re.IGNORECASE)
        if m:
            mes_n = meses.get(m.group(2).lower(),"00")
            raw = f"{int(m.group(1)):02d}/{mes_n}/{m.group(3)}"
            return raw, raw.replace("/","")
        for p in [r"VENCIMENTO\s*(\d{2}/\d{2}/\d{4})",r"vencimento\s*(\d{2}/\d{2}/\d{4})"]:
            mm = re.search(p, texto, re.IGNORECASE)
            if mm: raw = mm.group(1); return raw, raw.replace("/","")
        return None, None

    def cod_cliente(self, texto):
        for p in [r"N[\u00ba\u00b0]\s*DO\s*CLIENTE:\s*(\d+)",r"IDENTIFICACAO:\s*(\d+)",
                  r"IDENTIFICA[\u00c7][\u00c3]O:\s*(\d+)",r"N[\u00ba\u00b0]\s*DO CLIENTE\s*[:\-]?\s*(\d+)"]:
            v = self.rx(texto, p)
            if v: return v
        return None

    def nome_cliente(self, texto): return self.rx(texto, r"RAZ[AÃ]O SOCIAL:\s*(.+?)(?:CNPJ|CPF|$)")
    def cnpj_cliente(self, texto): return self.rx(texto, r"CNPJ[:/]\s*([\d\.\-/]+)")
    def ie_cliente(self, texto): return self.rx(texto, r"INSCRI[CÇ][AÃ]O ESTADUAL:\s*(\d+)")
    def chave_acesso(self, texto): return self.rx(texto, r"Chave de acesso:\s*([\d\s]+)")
    def protocolo(self, texto): return self.rx(texto, r"Protocolo de autoriza[cç][aã]o:\s*([\d\s\-]+)")
    def numero_nf(self, texto):
        return (self.rx(texto, r"NOTA FISCAL.*?N[°º]\s*(\d+)") or
                self.rx(texto, r"N[°º]\s*(\d{4,6})\s*-\s*S[EÉ]RIE"))
    def serie(self, texto): return self.rx(texto, r"S[EÉ]RIE\s*(\d+)")

    def endereco(self, texto):
        try:
            m = re.search(r"ENDERE[CÇ]O:\s*(.+?)(?:PALHOCA|FLORIANOPOLIS|JOINVILLE|\d{5}-\d{3}|$)", texto, re.IGNORECASE)
            if m: return m.group(1).strip()
        except Exception: pass
        return ""

    def itens_fatura(self, texto):
        try:
            itens = re.findall(r"([\w\s/]+?)\s+(\d+)\s+UN\s+[\d\.,]+\s+[\d\.,]+\s+([\d\.,]+)", texto, re.IGNORECASE)
            if itens: return " | ".join(f"{n.strip()} R${v}" for n,_,v in itens[:8])
        except Exception: pass
        return ""

    def codigo_barras(self, texto):
        m = re.search(r'(\d{11}\s\d(?:\s\d{11}\s\d){2,4})', texto)
        if m: return m.group(1).strip()
        m2 = re.search(r'IDENTIFICA.{0,60}([\d\s]{30,80})', texto, re.IGNORECASE|re.DOTALL)
        if m2:
            trecho = m2.group(1).strip()
            if re.search(r'\d{5,}', trecho): return trecho
        return None

    def buscar_json(self, cod):
        if not cod or not self.dados_json: return None, None, None
        for item in self.dados_json:
            if not isinstance(item, dict): continue
            if str(item.get("contrato","")).strip().lstrip("0") == str(cod).strip().lstrip("0"):
                return str(cod), item.get("nome",""), item
        return None, None, None

    def extrair_completo(self, nome_pdf, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception as e: return self._vazio(nome_pdf, str(e))

        numero_nota = self.numero_nota(texto); nf_num = self.numero_nf(texto)
        serie = self.serie(texto); valor_total = self.valor(texto)
        em_raw,_ = self.data_emissao(texto); vc_raw,_ = self.data_vencimento(texto)
        cod = self.cod_cliente(texto); nome_raw = self.nome_cliente(texto)
        cnpj = self.cnpj_cliente(texto); ie = self.ie_cliente(texto)
        end = self.endereco(texto); chave = self.chave_acesso(texto)
        proto = self.protocolo(texto); itens = self.itens_fatura(texto)

        contrato_json, nome_json, extra_json = self.buscar_json(cod)
        nome_final = nome_json or nome_raw or ""
        campos_ok = all([numero_nota, valor_total, cod, vc_raw])
        if not cod: status = "❌ Código cliente não encontrado"
        elif not nome_json: status = "⚠️ Sem match no JSON"
        elif not campos_ok: status = "⚠️ Dados incompletos"
        else: status = "✅ OK"

        reg = {
            "Operadora":"Algar","PDF":nome_pdf,"Status":status,
            "Nota Fiscal (Nº)":nf_num or "","NFF":numero_nota or "",
            "Fatura Numerada":"","Série":serie or "",
            "Data Emissão":em_raw or "","Vencimento":vc_raw or "",
            "Referência (mês/ano)":"","Valor Total (R$)":valor_total or "",
            "Itens da Fatura":itens,"Código do Cliente":cod or "",
            "CNPJ/CPF Cliente":cnpj or "","IE Cliente":ie or "",
            "Telefone":"","Município":"","Endereço":end,
            "Contrato (JSON)":contrato_json or "","Nome (JSON)":nome_final,
            "Chave de Acesso":(chave or "").strip(),"Protocolo de Autorização":(proto or "").strip(),
        }
        if extra_json:
            for k,v in extra_json.items():
                if k not in ("contrato","nome"): reg[f"JSON › {k}"] = str(v)
        return reg

    def extrair_macro(self, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception: return {}
        nota = self.numero_nota(texto)
        _, em_fmt = self.data_emissao(texto); _, vc_fmt = self.data_vencimento(texto)
        valor = self.valor(texto); cod = self.cod_cliente(texto)
        _, nome, _ = self.buscar_json(cod); cod_barras = self.codigo_barras(texto)
        return {"numero_nota":nota,"valor":valor,"data_emissao":em_fmt,
                "data_vencimento":vc_fmt,"numero_contrato":cod,"nome_cliente":nome,
                "codigo_barras":cod_barras}

    def _vazio(self, nome_pdf, motivo):
        base = {"Operadora":"Algar","PDF":nome_pdf,"Status":f"❌ Erro: {motivo}"}
        for k in ["Nota Fiscal (Nº)","NFF","Fatura Numerada","Série","Data Emissão",
                  "Vencimento","Referência (mês/ano)","Valor Total (R$)","Itens da Fatura",
                  "Código do Cliente","CNPJ/CPF Cliente","IE Cliente","Telefone","Município",
                  "Endereço","Contrato (JSON)","Nome (JSON)","Chave de Acesso","Protocolo de Autorização"]:
            base[k] = ""
        return base

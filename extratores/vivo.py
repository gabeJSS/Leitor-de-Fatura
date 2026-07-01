import re
import pdfplumber

class ExtractorVivo:
    def __init__(self, dados_json, log_fn):
        self.dados_json = dados_json
        self._log = log_fn

    def texto_pdf(self, caminho):
        for senha in [None, "1552"]:
            try:
                kwargs = {"password": senha} if senha else {}
                with pdfplumber.open(caminho, **kwargs) as pdf:
                    partes = [p.extract_text() or "" for p in pdf.pages]
                texto = re.sub(r"\s+", " ", "\n".join(partes))
                if texto.strip(): return texto
            except Exception as e:
                self.log(f"Erro ao ler PDF Vivo: {e}", "warn")
        return ""

    def rx(self, texto, pattern):
        try:
            m = re.search(pattern, texto, re.IGNORECASE)
            if m: return m.group(1).strip()
        except Exception as e:
            self.log(f"Regex falhou: {e}", "warn")
        return None

    def numero_nota(self, texto): return self.rx(texto, r"N[uú]mero da Fatura:\s*(\d+)")
    def numero_nfcom(self, texto): return self.rx(texto, r"N[°º]\s*NFCOM\s+(\d+)")
    def serie(self, texto): return self.rx(texto, r"S[EÉ]RIE\s+(\d+)")
    def referencia(self, texto): return self.rx(texto, r"M[EÊ]S DE REFER[EÊ]NCIA\s+(\d{2}/\d{4})")
    def cnpj_cliente(self, texto): return self.rx(texto, r"CNPJ[:/]\s*([\d\.\-/]+)")
    def ie_cliente(self, texto): return self.rx(texto, r"INSCRI[CÇ][AÃ]O ESTADUAL:\s*(\d+)")
    def chave_acesso(self, texto): return self.rx(texto, r"Chave de acesso:\s*([\d\s]+)")
    def protocolo(self, texto): return self.rx(texto, r"Protocolo de Autoriza[cç][aã]o:\s*([\w\s\-/:.]+?)(?:\s{2}|$)")
    def cod_cliente(self, texto): return self.rx(texto, r"N[uú]mero da Conta:\s*(\d+)")

    def valor(self, texto):
        for p in [r"TOTAL A PAGAR\s*R\$\s*([\d\.,]+)",r"TOTAL A PAGAR\s+([\d\.,]+)"]:
            v = self.rx(texto, p)
            if v: return v
        return None

    def data_emissao(self, texto):
        raw = self.rx(texto, r"DATA DE EMISS[AÃ]O:\s*(\d{2}/\d{2}/\d{4})")
        return (raw, raw.replace("/","")) if raw else (None, None)

    def data_vencimento(self, texto):
        for p in [r"VENCIMENTO[:\s]+(\d{2}/\d{2}/\d{4})",r"Data de Vencimento\s+(\d{2}/\d{2}/\d{4})"]:
            raw = self.rx(texto, p)
            if raw: return raw, raw.replace("/","")
        return None, None

    def itens_fatura(self, texto):
        try:
            itens = re.findall(r"(Mensalidade IP Fixo|VIVO Fibra[\w\s]+?|Ubook[\w\s]+?|Skeelo[\w\s]+?)"
                               r"\s+un\s+1\s+[\d\.,]+\s+[-\d\.,]+\s+([\d\.,]+)", texto, re.IGNORECASE)
            if itens: return " | ".join(f"{n.strip()} R${v}" for n,v in itens)
        except Exception as e:
            self.log(f"Erro ao extrair itens da fatura: {e}", "warn")
        return ""

    def codigo_barras(self, texto):
        texto = re.sub(r'\(cid:\d+\)',' ',texto).replace('\xa0',' ')
        texto = re.sub(r'\s+',' ',texto).strip()
        for pat in [re.compile(r'(?:\d{11}\s\d\s){4}\d{11}\s\d'),
                    re.compile(r'(?:\d{11}\s\d\s){3}\d{11}\s\d'),
                    re.compile(r'(?:\d{11}\s\d\s?){3,6}')]:
            m = pat.search(texto)
            if m:
                cod = re.sub(r'\D','',m.group(0))
                return cod[-55:] if len(cod)>60 else cod
        m = re.search(r'\d{40,120}',texto)
        if m:
            cod = m.group(0)
            return cod[-55:] if len(cod)>60 else cod
        return None

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

        numero_nota = self.numero_nota(texto); nfcom = self.numero_nfcom(texto)
        serie = self.serie(texto); valor_total = self.valor(texto)
        em_raw,_ = self.data_emissao(texto); vc_raw,_ = self.data_vencimento(texto)
        ref = self.referencia(texto); cod = self.cod_cliente(texto)
        cnpj = self.cnpj_cliente(texto); ie = self.ie_cliente(texto)
        chave = self.chave_acesso(texto); proto = self.protocolo(texto)
        itens = self.itens_fatura(texto)
        contrato_json, nome_json, extra_json = self.buscar_json(cod)

        campos_ok = all([numero_nota, valor_total, cod, vc_raw])
        if not cod: status = "❌ Número da conta não encontrado"
        elif not nome_json: status = "⚠️ Sem match no JSON"
        elif not campos_ok: status = "⚠️ Dados incompletos"
        else: status = "✅ OK"

        reg = {
            "Operadora":"Vivo","PDF":nome_pdf,"Status":status,
            "Nota Fiscal (Nº)":numero_nota or "","NFF":nfcom or "",
            "Fatura Numerada":"","Série":serie or "",
            "Data Emissão":em_raw or "","Vencimento":vc_raw or "",
            "Referência (mês/ano)":ref or "","Valor Total (R$)":valor_total or "",
            "Itens da Fatura":itens,"Código do Cliente":cod or "",
            "CNPJ/CPF Cliente":cnpj or "","IE Cliente":ie or "",
            "Telefone":"","Município":"Florianópolis/SC","Endereço":"",
            "Contrato (JSON)":contrato_json or "","Nome (JSON)":nome_json or "",
            "Chave de Acesso":(chave or "").strip(),"Protocolo de Autorização":(proto or "").strip(),
        }
        if extra_json:
            for k,v in extra_json.items():
                if k not in ("contrato","nome"): reg[f"JSON › {k}"] = str(v)
        return reg

    def extrair_macro(self, caminho):
        try: texto = self.texto_pdf(caminho)
        except Exception as e:
            self.log(f"Erro ao extrair dados para macro: {e}", "error")
            return {}
        nota = self.numero_nota(texto)
        _, em_fmt = self.data_emissao(texto); _, vc_fmt = self.data_vencimento(texto)
        valor = self.valor(texto); cod = self.cod_cliente(texto)
        _, nome, _ = self.buscar_json(cod); cod_barras = self.codigo_barras(texto)
        return {"numero_nota":nota,"valor":valor,"data_emissao":em_fmt,
                "data_vencimento":vc_fmt,"numero_contrato":cod,"nome_cliente":nome,
                "codigo_barras":cod_barras}

    def _vazio(self, nome_pdf, motivo):
        base = {"Operadora":"Vivo","PDF":nome_pdf,"Status":f"❌ Erro: {motivo}"}
        for k in ["Nota Fiscal (Nº)","NFF","Fatura Numerada","Série","Data Emissão",
                  "Vencimento","Referência (mês/ano)","Valor Total (R$)","Itens da Fatura",
                  "Código do Cliente","CNPJ/CPF Cliente","IE Cliente","Telefone","Município",
                  "Endereço","Contrato (JSON)","Nome (JSON)","Chave de Acesso","Protocolo de Autorização"]:
            base[k] = ""
        return base

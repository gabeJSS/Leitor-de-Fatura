import re
import pdfplumber


class ExtractorClaro:
    """
    Extrator de faturas Claro/NET — suporta formato antigo e novo (2026+).

    Diferenças do formato novo:
    - Cabeçalho: "Código Vencimento: Valor:" (com dois-pontos) em vez de "Código Vencimento Valor"
    - Código NET no cabeçalho aparece truncado: "Código: 088/6234035"
      → usar linha "NET SERVICOS 0886234035420" para reconstruir o código completo
    - Mês de referência: "Mês: Maio/2026" em vez de "Mês Referência Maio/2026"
    - Vencimento da NF: "Vencimento 15/06/2026" (sem dois-pontos)
    - Número da NF: "Número: 0026949077" (igual nos dois formatos)
    - Emissão: "Emissão: 28/05/2026" (igual nos dois formatos)
    """

    def __init__(self, dados_json, log_fn):
        self.dados_json = dados_json
        self._log = log_fn

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def texto_pdf(self, caminho):
        with pdfplumber.open(caminho) as pdf:
            partes = [p.extract_text() or "" for p in pdf.pages]
        return re.sub(r"\s+", " ", "\n".join(partes))

    def rx(self, texto, pattern):
        try:
            m = re.search(pattern, texto, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Detecção de formato
    # ------------------------------------------------------------------

    def _formato_novo(self, texto):
        """
        Retorna True se for o novo layout (2026+).
        Sinal mais confiável: cabeçalho usa "Vencimento:" com dois-pontos
        e não tem a linha "Mês Referência".
        """
        tem_vc_com_ponto = bool(re.search(r"Vencimento:\s*\d{2}/\d{2}/\d{4}", texto))
        nao_tem_mes_ref  = not bool(re.search(r"M[êe]s\s+Refer[êe]ncia", texto, re.IGNORECASE))
        return tem_vc_com_ponto and nao_tem_mes_ref

    # ------------------------------------------------------------------
    # Extração de campos
    # ------------------------------------------------------------------

    def numero_nota(self, texto):
        # Funciona nos dois formatos
        return self.rx(texto, r"N[úu]mero:\s*(\d{6,12})")

    def referencia(self, texto):
        # Novo: "Mês: Maio/2026"  |  Antigo: "Mês Referência Maio/2026"
        for p in [
            r"M[êe]s:\s+(\w+/\d{4})",
            r"M[êe]s\s+Refer[êe]ncia\s+(\w+/\d{4})",
        ]:
            v = self.rx(texto, p)
            if v:
                return v
        return None

    def valor(self, texto):
        # Ambos os formatos têm "Valor Total\n<valor>" ou "Valor total <valor>"
        for p in [
            r"Valor\s+Total\s*\n\s*([\d\.]+,\d{2})",
            r"Valor\s+total\s+([\d\.]+,\d{2})",
            r"Valor\s+([\d\.]+,\d{2})",
        ]:
            v = self.rx(texto, p)
            if v:
                return v
        return None

    def data_emissao(self, texto):
        raw = self.rx(texto, r"Emiss[aã]o:\s*(\d{2}/\d{2}/\d{4})")
        return (raw, raw.replace("/", "")) if raw else (None, None)

    def data_vencimento(self, texto):
        # Novo: "Vencimento 15/06/2026"  |  Antigo: "Vencimento: 15/05/2026"
        for p in [
            r"Vencimento[:\s]+(\d{2}/\d{2}/\d{4})",
        ]:
            raw = self.rx(texto, p)
            if raw:
                return (raw, raw.replace("/", ""))
        return (None, None)

    def codigo_net(self, texto):
        """
        Estratégia em cascata:
        1. Reconstrução a partir da linha 'NET SERVICOS <13 dígitos>' — mais confiável
           (formato: primeiros 3 = prefixo regional, próximos 9 = contrato, último = dígito verificador)
        2. Linha 'Código: NNN/NNNNNNNNN' do cabeçalho da NF (formato antigo completo)
        3. Linha 'Código NNN/NNN...' (sem dois-pontos, formato antigo)
        4. Padrão genérico com espaço entre grupos
        """
        # 1 — NET SERVICOS (mais confiável para o formato novo)
        m = re.search(r"NET\s+SERVICOS\s+(\d{3})(\d+)", texto, re.IGNORECASE)
        if m:
            prefix = m.group(1)
            resto  = m.group(2)[:-1]   # retira o dígito verificador do final
            return f"{prefix}/{resto}"

        # 2 — Código explícito completo (formato antigo e alguns PDFs novos)
        for p in [
            r"C[óo]digo:\s*(\d{3}/\d{9,12})",
            r"C[óo]digo\s+NET\s*:?\s*(\d{3}/\d{6,12})",
            r"C[óo]digo\s*:?\s*(\d{3}/\d{6,12})",
        ]:
            v = self.rx(texto, p)
            if v:
                return v

        # 3 — Código com espaço entre prefixo e número
        m = re.search(r"C[óo]digo\s*:?\s*(\d{3})\s*/\s*(\d{6,12})", texto, re.IGNORECASE)
        if m:
            return f"{m.group(1)}/{m.group(2)}"

        return None

    def codigo_barras(self, texto):
        texto = re.sub(r"\(cid:\d+\)", " ", texto).replace("\xa0", " ")
        texto = re.sub(r"\s+", " ", texto).strip()
        # Quatro blocos "NNNNNNNNNNN-D"
        m = re.search(
            r"(\d{11}-\d\s+\d{11}-\d\s+\d{11}-\d\s+\d{11}-\d)", texto
        )
        if m:
            return re.sub(r"\D", "", m.group(1))
        # Sequência contínua de 44-48 dígitos
        m = re.search(r"\d{44,48}", texto)
        if m:
            return m.group(0)
        return None

    # ------------------------------------------------------------------
    # Busca no JSON de contratos
    # ------------------------------------------------------------------

    def buscar_json(self, cod_net):
        if not cod_net or not self.dados_json:
            return None, None, None
        digitos_pdf = re.sub(r"\D", "", cod_net)
        match = None
        for item in self.dados_json:
            if not isinstance(item, dict):
                continue
            dig = re.sub(r"\D", "", str(item.get("contrato", "")))
            if dig == digitos_pdf:
                match = item
                break
        if not match:
            for item in self.dados_json:
                if not isinstance(item, dict):
                    continue
                dig = re.sub(r"\D", "", str(item.get("contrato", "")))
                if digitos_pdf.endswith(dig) or dig.endswith(digitos_pdf):
                    match = item
                    break
        if match:
            return str(match.get("contrato", cod_net)), match.get("nome", ""), match
        return cod_net, None, None

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    def extrair_completo(self, nome_pdf, caminho):
        try:
            texto = self.texto_pdf(caminho)
        except Exception as e:
            return self._vazio(nome_pdf, str(e))

        numero_nota  = self.numero_nota(texto)
        valor_total  = self.valor(texto)
        em_raw, _    = self.data_emissao(texto)
        vc_raw, _    = self.data_vencimento(texto)
        ref          = self.referencia(texto)
        cod          = self.codigo_net(texto)
        contrato_json, nome_json, extra_json = self.buscar_json(cod)

        # Diagnóstico de formato (informativo)
        fmt = "novo" if self._formato_novo(texto) else "antigo"

        campos_ok = all([numero_nota, valor_total, cod, vc_raw])
        if not cod:
            status = "❌ Código NET não encontrado"
        elif not nome_json:
            status = f"⚠️ Sem match no JSON [{fmt}]"
        elif not campos_ok:
            status = f"⚠️ Dados incompletos [{fmt}]"
        else:
            status = f"✅ OK [{fmt}]"

        reg = {
            "Operadora": "Claro",
            "PDF": nome_pdf,
            "Status": status,
            "Nota Fiscal (Nº)": numero_nota or "",
            "NFF": "",
            "Fatura Numerada": "",
            "Série": "",
            "Data Emissão": em_raw or "",
            "Vencimento": vc_raw or "",
            "Referência (mês/ano)": ref or "",
            "Valor Total (R$)": valor_total or "",
            "Itens da Fatura": "",
            "Código do Cliente": cod or "",
            "CNPJ/CPF Cliente": "",
            "IE Cliente": "",
            "Telefone": "",
            "Município": "Florianópolis/SC",
            "Endereço": "",
            "Contrato (JSON)": contrato_json or "",
            "Nome (JSON)": nome_json or "",
            "Chave de Acesso": "",
            "Protocolo de Autorização": "",
        }
        if extra_json:
            for k, v in extra_json.items():
                if k not in ("contrato", "nome"):
                    reg[f"JSON › {k}"] = str(v)
        return reg

    def extrair_macro(self, caminho):
        try:
            texto = self.texto_pdf(caminho)
        except Exception:
            return {}
        nota        = self.numero_nota(texto)
        _, em_fmt   = self.data_emissao(texto)
        _, vc_fmt   = self.data_vencimento(texto)
        valor       = self.valor(texto)
        cod         = self.codigo_net(texto)
        _, nome, _  = self.buscar_json(cod)
        cod_barras  = self.codigo_barras(texto)
        return {
            "numero_nota": nota,
            "valor": valor,
            "data_emissao": em_fmt,
            "data_vencimento": vc_fmt,
            "numero_contrato": cod,
            "nome_cliente": nome,
            "codigo_barras": cod_barras,
        }

    def _vazio(self, nome_pdf, motivo):
        base = {"Operadora": "Claro", "PDF": nome_pdf, "Status": f"❌ Erro: {motivo}"}
        for k in [
            "Nota Fiscal (Nº)", "NFF", "Fatura Numerada", "Série",
            "Data Emissão", "Vencimento", "Referência (mês/ano)",
            "Valor Total (R$)", "Itens da Fatura", "Código do Cliente",
            "CNPJ/CPF Cliente", "IE Cliente", "Telefone", "Município",
            "Endereço", "Contrato (JSON)", "Nome (JSON)",
            "Chave de Acesso", "Protocolo de Autorização",
        ]:
            base[k] = ""
        return base
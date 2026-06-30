import re

from .algar import ExtractorAlgar
from .claro import ExtractorClaro
from .mais import ExtractorMais
from .vero import ExtractorVero
from .vivo import ExtractorVivo

EXTRACTOR_CLASSES = {
    "vero": ExtractorVero,
    "algar": ExtractorAlgar,
    "vivo": ExtractorVivo,
    "claro": ExtractorClaro,
    "mais": ExtractorMais,
}


def detectar_operadora(texto: str) -> str:
    t = texto.upper()

    if ("MAIS INTERNET" in t or "MAISINTERNET" in t
            or "11832927000104" in t
            or "COMBO MAIS" in t):
        return "mais"

    if "ALGAR" in t or "71.208.516" in t or "71208516" in t:
        return "algar"

    if ("TELEFÔNICA" in t or "TELEFONICA" in t
            or "VIVO EMPRESAS" in t
            or "02.558.157" in t or "02558157" in t):
        return "vivo"

    if ("CLARO" in t or "NET SERVICOS" in t
            or "NET SERVIÇOS" in t
            or "66.970.229" in t or "66970229" in t):
        return "claro"

    if ("VERO" in t
            or "31.748.174" in t
            or "31748174" in t):
        return "vero"

    return "desconhecida"

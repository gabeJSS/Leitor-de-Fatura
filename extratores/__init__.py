from .algar import ExtractorAlgar
from .claro import ExtractorClaro
from .mais import ExtractorMais
from .vero import ExtractorVero
from .vivo import ExtractorVivo
from .detector import EXTRACTOR_CLASSES, detectar_operadora

__all__ = [
    "ExtractorAlgar",
    "ExtractorClaro",
    "ExtractorMais",
    "ExtractorVero",
    "ExtractorVivo",
    "EXTRACTOR_CLASSES",
    "detectar_operadora",
]

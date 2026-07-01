from typing import Callable, Optional

import pyodbc

from core.settings import load_settings


def _bool_conn_value(valor: bool) -> str:
    return "yes" if valor else "no"


def normalizar_servidor_sql(server: str) -> str:
    return str(server or "").strip().replace("\\\\", "\\")


def _build_conn_str(config: dict) -> str:
    driver = str(config.get("driver") or "").strip()
    server = normalizar_servidor_sql(config.get("server"))
    database = str(config.get("database") or "").strip()
    username = str(config.get("username") or "").strip()
    password = str(config.get("password") or "")
    trust_cert = bool(config.get("trust_server_certificate", True))

    faltando = [
        nome
        for nome, valor in [
            ("driver", driver),
            ("server", server),
            ("database", database),
            ("username", username),
            ("password", password),
        ]
        if not valor
    ]
    if faltando:
        raise ValueError(f"Configuracao do banco incompleta: {', '.join(faltando)}")

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        f"TrustServerCertificate={_bool_conn_value(trust_cert)};"
    )


def conectar_banco(config: Optional[dict] = None, timeout: int = 10):
    db_config = config or load_settings().get("database", {})
    conn_str = _build_conn_str(db_config)
    return pyodbc.connect(conn_str, timeout=timeout)


def testar_conexao(config: Optional[dict] = None):
    conn = conectar_banco(config=config, timeout=5)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
    finally:
        conn.close()


def fornecedor_por_operadora(op: str) -> Optional[str]:
    return {
        "vero": "14818",
        "algar": "12045",
        "vivo": "9690",
        "claro": "14107",
        "mais": "14166",
    }.get(op)


def nota_ja_lancada(numero_nota: str, nff: str, op: str, log_fn: Callable[[str, str], None] = None) -> bool:
    fornecedor = fornecedor_por_operadora(op)
    if not fornecedor:
        if log_fn:
            log_fn(f"Operadora sem fornecedor configurado: {op}", "error")
        return False

    numero_nota = str(numero_nota).strip() if numero_nota else ""
    nff = str(nff).strip() if nff else ""
    nff_numerica = nff if nff.isdigit() else ""
    candidatos = list(dict.fromkeys(v for v in [numero_nota, nff_numerica] if v))

    if not candidatos:
        if log_fn:
            log_fn("Sem numero de nota para consultar no banco", "warn")
        return False

    conn = None
    try:
        conn = conectar_banco()
        cursor = conn.cursor()
        placeholders = ", ".join("?" * len(candidatos))
        query = f"""
            SELECT TOP 1 1
            FROM dbo.ContasPagar
            WHERE Fornecedor = ?
            AND NotaFiscal IN ({placeholders})
        """
        cursor.execute(query, (str(fornecedor), *candidatos))
        resultado = cursor.fetchone()
        cursor.close()
        return resultado is not None
    except Exception as erro:
        if log_fn:
            log_fn(f"Erro ao consultar banco: {erro}", "error")
        raise
    finally:
        if conn is not None:
            conn.close()

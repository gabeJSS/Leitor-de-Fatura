import json
import os

from ui.theme import SETTINGS_FILE


DEFAULT_SETTINGS = {
    "database": {
        "driver": "ODBC Driver 18 for SQL Server",
        "server": "",
        "database": "",
        "username": "",
        "password": "",
        "trust_server_certificate": True,
    },
    "downloaders": {
        "mais": {
            "txid": "",
            "password": ""
        },
        "vero": {
            "username": "",
            "password": ""
        },
        "claro": {
            "document": ""
        },
    }
}


def load_settings():
    config = DEFAULT_SETTINGS.copy()
    if not os.path.exists(SETTINGS_FILE):
        return config

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except Exception:
        return config

    if isinstance(dados, dict):
        # Merge de forma aninhada para não perder chaves
        if "database" in dados and isinstance(dados["database"], dict):
            config["database"].update(dados["database"])
        if "downloaders" in dados and isinstance(dados["downloaders"], dict):
            for op_key, op_creds in dados["downloaders"].items():
                if op_key in config["downloaders"] and isinstance(op_creds, dict):
                    config["downloaders"][op_key].update(op_creds)
                else:
                    config["downloaders"][op_key] = op_creds
    return config


def save_settings(dados):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=2, ensure_ascii=False)
    return SETTINGS_FILE

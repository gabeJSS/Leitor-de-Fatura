import json
import os
import stat
import subprocess

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

ENV_OVERRIDES = {
    ("database", "password"): "MACRONOTAS_DB_PASSWORD",
    ("downloaders", "mais", "password"): "MACRONOTAS_MAIS_PASSWORD",
    ("downloaders", "vero", "password"): "MACRONOTAS_VERO_PASSWORD",
}


def _deepcopy_defaults():
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def _apply_env_overrides(config):
    for keys, env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        target = config
        for key in keys[:-1]:
            target = target.setdefault(key, {})
        target[keys[-1]] = value


def _restrict_file_permissions(path):
    """Restringe o settings.json ao usuario atual quando possivel."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass

    if os.name != "nt":
        return

    user = os.environ.get("USERNAME")
    if not user:
        return

    try:
        subprocess.run(
            ["icacls", path, "/inheritance:r", "/grant:r", f"{user}:F"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


def load_settings(log_fn=None):
    config = _deepcopy_defaults()
    if not os.path.exists(SETTINGS_FILE):
        _apply_env_overrides(config)
        return config

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except Exception as erro:
        if log_fn:
            log_fn(f"Erro ao carregar configuracoes: {erro}", "error")
        _apply_env_overrides(config)
        return config

    if isinstance(dados, dict):
        # Merge de forma aninhada para nao perder chaves novas.
        if "database" in dados and isinstance(dados["database"], dict):
            config["database"].update(dados["database"])
        if "downloaders" in dados and isinstance(dados["downloaders"], dict):
            for op_key, op_creds in dados["downloaders"].items():
                if op_key in config["downloaders"] and isinstance(op_creds, dict):
                    config["downloaders"][op_key].update(op_creds)
                else:
                    config["downloaders"][op_key] = op_creds

    _apply_env_overrides(config)
    return config


def save_settings(dados):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, indent=2, ensure_ascii=False)
    _restrict_file_permissions(SETTINGS_FILE)
    return SETTINGS_FILE

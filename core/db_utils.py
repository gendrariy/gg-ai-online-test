import os
import re
import json
import io
import gzip
import hashlib
from pathlib import Path

import pandas as pd
import requests

# ===== ONLINE (Google Drive public links for test) =====
# Для теста файлы в Drive должны быть "Anyone with the link → Viewer".
def _get_secret(name: str, default: str) -> str:
    # Streamlit Cloud Secrets
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    # fallback: env
    return os.getenv(name, default).strip()

GDRIVE_MANIFEST_ID = _get_secret("GDRIVE_MANIFEST_ID", "1Re07GsnBCgIf38g-sHj6PwHhN86STu5s")
GDRIVE_SNAPSHOT_ID = _get_secret("GDRIVE_SNAPSHOT_ID", "1iuDizQY5PldxlksmN_5f-kTEzTWKSoOg")


# ===== LOCAL (Access path) =====
ACCESS_DB_PATH = os.getenv("ACCESS_DB_PATH", r"J:\02.Productions\GG\Ai\MainBaseAi.accdb")

# Куда складывать скачанный snapshot в Streamlit Cloud
CACHE_DIR = Path(os.getenv("SNAPSHOT_CACHE_DIR", Path(__file__).resolve().parent.parent / ".cache_snapshot"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _gdrive_download_public(file_id: str, timeout: int = 120) -> bytes:
    """Скачивание из Google Drive для режима 'Anyone with the link'."""
    url = "https://drive.google.com/uc?export=download"
    s = requests.Session()

    r = s.get(url, params={"id": file_id}, stream=True, timeout=timeout)
    r.raise_for_status()

    confirm = None
    for k, v in r.cookies.items():
        if k.startswith("download_warning"):
            confirm = v
            break

    if confirm:
        r = s.get(url, params={"id": file_id, "confirm": confirm}, stream=True, timeout=timeout)
        r.raise_for_status()

    data = io.BytesIO()
    for chunk in r.iter_content(chunk_size=1024 * 256):
        if chunk:
            data.write(chunk)
    return data.getvalue()


def _load_manifest() -> dict:
    raw = _gdrive_download_public(GDRIVE_MANIFEST_ID)
    return json.loads(raw.decode("utf-8"))


def _ensure_snapshot_file() -> Path:
    """
    Скачивает snapshot.csv.gz, если:
      - его нет в кэше
      - или sha256 из manifest изменился
    """
    manifest = _load_manifest()
    sha = (manifest.get("snapshot") or {}).get("sha256")

    if not sha:
        target = CACHE_DIR / "snapshot.csv.gz"
        if target.exists():
            return target
        raw = _gdrive_download_public(GDRIVE_SNAPSHOT_ID)
        target.write_bytes(raw)
        return target

    target = CACHE_DIR / f"snapshot_{sha}.csv.gz"
    if target.exists():
        return target

    raw = _gdrive_download_public(GDRIVE_SNAPSHOT_ID)
    got_sha = _sha256_bytes(raw)
    if got_sha != sha:
        target = CACHE_DIR / f"snapshot_{got_sha}.csv.gz"

    target.write_bytes(raw)
    return target


_date_pat = re.compile(r"#(\d{1,2})/(\d{1,2})/(\d{4})#")


def _access_sql_to_duckdb(sql: str) -> str:
    """
    Минимальная "переводилка" Access SQL -> DuckDB SQL для ваших шаблонов.
    """
    s = sql

    s = s.replace("SELECT * FROM [T_Local_Snapshot] WHERE 1=1", "SELECT * FROM T_Local_Snapshot WHERE 1=1")

    s = re.sub(
        r"UCase\s*\(\s*LTrim\s*\(\s*RTrim\s*\(\s*\[([^\]]+)\]\s*\)\s*\)\s*\)",
        r"upper(trim([\1]))",
        s,
        flags=re.IGNORECASE,
    )

    s = re.sub(
        r"LTrim\s*\(\s*RTrim\s*\(\s*\[([^\]]+)\]\s*\)\s*\)",
        r"trim([\1])",
        s,
        flags=re.IGNORECASE,
    )

    s = re.sub(r"\bUCase\s*\(", "upper(", s, flags=re.IGNORECASE)

    def repl_date(m):
        mm = int(m.group(1)); dd = int(m.group(2)); yy = int(m.group(3))
        return f"DATE '{yy:04d}-{mm:02d}-{dd:02d}'"
    s = _date_pat.sub(repl_date, s)

    s = re.sub(r"\[([^\]]+)\]", r'"\1"', s)

    return s


def _execute_duckdb_on_snapshot(sql: str) -> pd.DataFrame:
    import duckdb

    snapshot_path = _ensure_snapshot_file()
    duck_sql = _access_sql_to_duckdb(sql)

    con = duckdb.connect(database=":memory:")
    path_str = str(snapshot_path).replace("'", "''")
    con.execute(f"CREATE OR REPLACE VIEW T_Local_Snapshot AS SELECT * FROM read_csv_auto('{path_str}', compression='gzip');")
    try:
        return con.execute(duck_sql).df()
    finally:
        con.close()


def execute_access_query(sql: str) -> pd.DataFrame:
    """
    ЕДИНАЯ точка для main_app.py:
      - локально можно выполнять Access
      - онлайн (Streamlit Cloud) работает по snapshot.csv.gz из Google Drive
    """
    if os.getenv("DATA_SOURCE", "SNAPSHOT").upper() == "ACCESS":
        try:
            import pyodbc
            conn_str = (
                r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
                rf"DBQ={ACCESS_DB_PATH};"
            )
            with pyodbc.connect(conn_str) as conn:
                return pd.read_sql(sql, conn)
        except Exception:
            pass

    return _execute_duckdb_on_snapshot(sql)


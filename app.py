import io
import json
import gzip
import time
from typing import Tuple, Dict, Any

import pandas as pd
import requests
import streamlit as st


# Твои два ID (можно оставить как есть)
DEFAULT_ID_1 = "1Re07GsnBCgIf38g-sHj6PwHhN86STu5s"
DEFAULT_ID_2 = "1iuDizQY5PldxlksmN_5f-kTEzTWKSoOg"


def gdrive_download_public(file_id: str, timeout: int = 120) -> bytes:
    """
    Скачивание из Google Drive для режима "Anyone with the link".
    Умеет проходить confirm cookie (иногда Google просит подтверждение).
    """
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

    # Считываем поток в bytes
    data = io.BytesIO()
    for chunk in r.iter_content(chunk_size=1024 * 256):
        if chunk:
            data.write(chunk)
    return data.getvalue()


def try_parse_manifest(raw: bytes) -> Tuple[bool, Dict[str, Any] | None, str | None]:
    # Пытаемся распарсить как JSON-манифест
    try:
        text = raw.decode("utf-8")
        obj = json.loads(text)
        # Простая проверка "похоже ли на наш manifest"
        if isinstance(obj, dict) and ("snapshot" in obj or "updated_at_local" in obj or "rows" in obj):
            return True, obj, None
        # Иногда JSON может быть не тем — всё равно вернём как JSON, но пометим
        return True, obj, "JSON распарсился, но структура не похожа на manifest."
    except Exception as e:
        return False, None, str(e)


def try_parse_snapshot_gz(raw: bytes) -> Tuple[bool, pd.DataFrame | None, str | None]:
    # Пытаемся распарсить как gzip CSV
    try:
        # Быстрая проверка gzip
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
            sample = gz.read(1024)  # читаем чуть-чуть
            if not sample:
                return False, None, "GZIP пустой."
        # Если gzip ок — читаем полностью pandas
        df = pd.read_csv(io.BytesIO(raw), compression="gzip", low_memory=False)
        return True, df, None
    except Exception as e:
        return False, None, str(e)


@st.cache_data(ttl=120)
def load_two_files(id1: str, id2: str) -> Tuple[bytes, bytes]:
    raw1 = gdrive_download_public(id1)
    raw2 = gdrive_download_public(id2)
    return raw1, raw2


def identify_files(raw1: bytes, raw2: bytes) -> Tuple[Dict[str, Any], pd.DataFrame]:
    """
    Определяем, где manifest, где snapshot.
    Если оба подходят/оба не подходят — выдаём понятную ошибку.
    """
    m1_ok, m1, m1_err = try_parse_manifest(raw1)
    m2_ok, m2, m2_err = try_parse_manifest(raw2)

    s1_ok, df1, s1_err = try_parse_snapshot_gz(raw1)
    s2_ok, df2, s2_err = try_parse_snapshot_gz(raw2)

    # Идеальный случай: один JSON-манифест + один gzip CSV
    if m1_ok and s2_ok and (df2 is not None):
        return m1 or {}, df2
    if m2_ok and s1_ok and (df1 is not None):
        return m2 or {}, df1

    # Если оба распарсились как JSON (например, случайно оба json)
    if m1_ok and m2_ok and not (s1_ok or s2_ok):
        raise RuntimeError(
            "Оба файла читаются как JSON, но ни один не читается как snapshot.csv.gz.\n"
            f"ID1 JSON-ошибка: {m1_err}\n"
            f"ID2 JSON-ошибка: {m2_err}"
        )

    # Если оба читаются как gzip CSV (редко)
    if s1_ok and s2_ok and (df1 is not None) and (df2 is not None) and not (m1_ok or m2_ok):
        raise RuntimeError("Оба файла читаются как snapshot.csv.gz, но manifest.json не найден.")

    # Иначе — покажем диагностику
    raise RuntimeError(
        "Не удалось однозначно определить manifest и snapshot.\n\n"
        f"ID1: manifest_ok={m1_ok} (err={m1_err}); snapshot_ok={s1_ok} (err={s1_err})\n"
        f"ID2: manifest_ok={m2_ok} (err={m2_err}); snapshot_ok={s2_ok} (err={s2_err})\n\n"
        "Проверь, что оба файла в Drive стоят как: Anyone with the link → Viewer (для теста)."
    )


st.set_page_config(page_title="GG AI Online Test", layout="wide")

st.title("GG AI Online — Тест чтения из Google Drive")

with st.sidebar:
    st.subheader("Google Drive File IDs (публичный доступ для теста)")
    id1 = st.text_input("File ID #1", value=DEFAULT_ID_1)
    id2 = st.text_input("File ID #2", value=DEFAULT_ID_2)

    colA, colB = st.columns(2)
    with colA:
        run = st.button("Загрузить", type="primary")
    with colB:
        if st.button("Очистить кэш"):
            st.cache_data.clear()
            st.success("Кэш очищен.")

if run:
    with st.spinner("Скачиваю 2 файла из Google Drive..."):
        raw1, raw2 = load_two_files(id1.strip(), id2.strip())

    with st.spinner("Определяю manifest / snapshot и читаю данные..."):
        manifest, df = identify_files(raw1, raw2)

    # Верхняя инфа
    updated_local = manifest.get("updated_at_local", "?")
    updated_utc = manifest.get("updated_at_utc", "?")
    rows = manifest.get("rows", df.shape[0])
    cols = manifest.get("cols", df.shape[1])

    st.success("Готово. Данные загружены.")
    st.write(f"Обновлено (local): **{updated_local}**")
    st.write(f"Обновлено (utc): **{updated_utc}**")
    st.write(f"Строк: **{rows}**, Колонок: **{cols}**")

    st.divider()

    # Быстрый просмотр
    st.subheader("Предпросмотр")
    st.dataframe(df.head(200), use_container_width=True, height=520)

    st.subheader("Колонки")
    st.code(", ".join(list(df.columns)))

else:
    st.info("Нажми **Загрузить**. Для теста оба файла должны быть в Drive с доступом: Anyone with the link → Viewer.")

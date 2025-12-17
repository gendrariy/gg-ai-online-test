import re
import pyodbc
import pandas as pd

# --- Общие шаблоны и утилиты ---

# Регулярное выражение для "not" фильтров (например: not gold)
NOT_PATTERN = r"\b(?:not|exclude|without)\s+"

def norm(field: str) -> str:
    """Возвращает имя поля в квадратных скобках, если оно не содержит спецсимволов."""
    if not field.startswith("["):
        return f"[{field}]"
    return field


def execute_access_query(sql: str) -> pd.DataFrame:
    """
    Выполняет SQL-запрос в базе Access и возвращает DataFrame.
    Требуется установленный ODBC-драйвер для Access.
    """
    try:
        conn_str = (
            r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
            r"DBQ=J:\02.Productions\GG\Ai\MainBaseAi.accdb;"
        )
        with pyodbc.connect(conn_str) as conn:
            df = pd.read_sql(sql, conn)
        return df
    except Exception as e:
        print("Ошибка при выполнении запроса:", e)
        return pd.DataFrame()

import requests
import re
import json
import logging
import argparse
from typing import Dict, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style

# Constants
THUNDERSTORE_API_URL = "https://thunderstore.io/api/experimental/package/{owner}/{package}/"
DEFAULT_CHANNEL = "repo"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Colorama
init(autoreset=True)

def parse_mod_url(url: str) -> Dict[str, str]:
    """
    Разбирает URL мода Thunderstore и извлекает канал, владельца и имя пакета.
    """
    pattern = r'https?://thunderstore\.io/c/(?P<channel>[^/]+)/p/(?P<owner>[^/]+)/(?P<package>[^/]+)/?'
    match = re.match(pattern, url)
    if not match:
        raise ValueError(f"Invalid mod URL: {url}")
    channel = match.group('channel') or DEFAULT_CHANNEL
    owner = match.group('owner')
    package = match.group('package')
    return {"channel": channel, "owner": owner, "package": package}


def get_latest_mod_info(channel: str, owner: str, package: str) -> Dict:
    """
    Возвращает версию и дату последнего обновления мода через экспериментальный API,
    а также корректный URL для скачивания.
    """
    # Запрос данных о пакете
    api_url = THUNDERSTORE_API_URL.format(owner=owner, package=package)
    resp = requests.get(api_url)
    resp.raise_for_status()
    data = resp.json()

    latest = data.get("latest", {})
    version = latest.get("version_number")
    raw_date = data.get("date_updated")
    # Преобразуем ISO-строку в формат "YYYY-MM-DD, HH:MM:SS"
    try:
        dt = datetime.fromisoformat(raw_date.rstrip('Z'))
        formatted_date = dt.strftime("%Y-%m-%d, %H:%M:%S")
    except Exception:
        formatted_date = raw_date

    # Корректная ссылка на мод
    download_url = f"https://thunderstore.io/c/{channel}/p/{owner}/{package}/"

    return {
        "version": version,
        "date_updated": formatted_date,
        "raw_date": raw_date,
        "url": download_url
    }


def fetch_all_updates(mods_url: str, max_workers: int = 5) -> List[Dict]:
    """
    Загружает список модов из JSON и получает данные о последнем обновлении каждого.
    Результат сортируется по дате обновления (свежие первыми).
    """
    resp = requests.get(mods_url)
    resp.raise_for_status()
    data = resp.json()

    mods = data.get("repo_mods", [])
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for mod in mods:
            try:
                parsed = parse_mod_url(mod.get("url", ""))
            except ValueError as e:
                logger.warning(f"Skipping invalid URL {mod.get('url')}: {e}")
                continue
            future = executor.submit(
                get_latest_mod_info,
                parsed["channel"], parsed["owner"], parsed["package"]
            )
            futures[future] = mod.get("name")

        for future in as_completed(futures):
            mod_name = futures[future]
            try:
                info = future.result()
                results.append({"name": mod_name, **info})
            except Exception as e:
                logger.error(f"Error fetching {mod_name}: {e}")

    # Сортируем по ISO-датe raw_date (лексикографически) в обратном порядке
    results.sort(key=lambda x: x.get("raw_date", ""), reverse=True)
    return results


def print_table(updates: List[Dict]):
    """
    Печатает обновления в виде таблицы с раскраской заголовков.
    """
    if not updates:
        print(Fore.RED + "No updates found.")
        return

    headers = ["Name", "Version", "Date Updated", "Download URL"]
    rows = [[u["name"], u["version"], u["date_updated"], u["url"]] for u in updates]

    # Вычисление ширины колонок
    col_widths = [max(len(headers[i]), max(len(row[i]) for row in rows)) for i in range(len(headers))]

    border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

    # Шапка таблицы
    print(border)
    header_line = (
        "| " + 
        " | ".join(Fore.CYAN + headers[i].ljust(col_widths[i]) + Style.RESET_ALL for i in range(len(headers))) +
        " |"
    )
    print(header_line)
    print(border)

    # Строки данных
    for row in rows:
        line = "| " + " | ".join(row[i].ljust(col_widths[i]) for i in range(len(row))) + " |"
        print(line)
    print(border)


def main():
    parser = argparse.ArgumentParser(description="Получить версию и дату обновления Thunderstore модов.")
    parser.add_argument(
        "--mods-url", 
        default="https://mods-guerra.netlify.app/mods.json",
        help="URL к JSON файлу со списком модов"
    )
    parser.add_argument(
        "--output", "-o",
        help="Путь к файлу для сохранения результата в формате JSON"
    )
    args = parser.parse_args()

    updates = fetch_all_updates(args.mods_url)

    # Вывод в виде таблицы
    print_table(updates)

    # Сохранение JSON при указании опции
    if args.output:
        out = [{k: v for k, v in u.items() if k != "raw_date"} for u in updates]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {args.output}")


if __name__ == "__main__":
    main()
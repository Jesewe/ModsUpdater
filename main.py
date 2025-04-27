import os
import requests
import re
import json
import logging
import argparse
import time
from typing import Dict, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Constants
THUNDERSTORE_API_URL = "https://thunderstore.io/api/experimental/package/{owner}/{package}/"
DEFAULT_CHANNEL = "repo"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Colorama
init(autoreset=True)

def parse_mod_url(url: str) -> Dict[str, str]:
    pattern = r'https?://thunderstore\.io/c/(?P<channel>[^/]+)/p/(?P<owner>[^/]+)/(?P<package>[^/]+)/?'
    match = re.match(pattern, url)
    if not match:
        raise ValueError(f"Invalid mod URL: {url}")
    channel = match.group('channel') or DEFAULT_CHANNEL
    owner = match.group('owner')
    package = match.group('package')
    return {"channel": channel, "owner": owner, "package": package}

def get_latest_mod_info(channel: str, owner: str, package: str) -> Dict:
    api_url = THUNDERSTORE_API_URL.format(owner=owner, package=package)
    resp = requests.get(api_url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    latest = data.get("latest", {})
    version = latest.get("version_number")
    raw_date = data.get("date_updated")
    try:
        dt = datetime.fromisoformat(raw_date.rstrip('Z'))
        formatted_date = dt.strftime("%Y-%m-%d, %H:%M:%S")
    except Exception:
        formatted_date = raw_date

    download_url = f"https://thunderstore.io/c/{channel}/p/{owner}/{package}/"
    return {"version": version, "date_updated": formatted_date, "raw_date": raw_date, "url": download_url}

def fetch_all_updates(mods_url: str, max_workers: int = 5) -> List[Dict]:
    resp = requests.get(mods_url, timeout=10)
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
            futures[executor.submit(get_latest_mod_info, parsed["channel"], parsed["owner"], parsed["package"])] = mod.get("name")
        for future in as_completed(futures):
            mod_name = futures[future]
            try:
                info = future.result()
                results.append({"name": mod_name, **info})
            except Exception as e:
                logger.error(f"Error fetching {mod_name}: {e}")
    results.sort(key=lambda x: x.get("raw_date", ""), reverse=True)
    return results

def print_table(updates: List[Dict]):
    if not updates:
        print(Fore.RED + "No updates found.")
        return
    headers = ["Name", "Version", "Date Updated", "Download URL"]
    rows = [[u["name"], u["version"], u["date_updated"], u["url"]] for u in updates]
    col_widths = [max(len(headers[i]), max(len(row[i]) for row in rows)) for i in range(len(headers))]
    border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(border)
    header_line = (
        "| " +
        " | ".join(Fore.CYAN + headers[i].ljust(col_widths[i]) + Style.RESET_ALL for i in range(len(headers))) +
        " |"
    )
    print(header_line)
    print(border)
    for row in rows:
        line = "| " + " | ".join(row[i].ljust(col_widths[i]) for i in range(len(row))) + " |"
        print(line)
    print(border)

def send_telegram(updates: List[Dict]):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        logger.error("Telegram token or chat_id not set in environment")
        return
    base_url = f"https://api.telegram.org/bot{token}/sendMessage"
    for u in updates:
        text = (f"Название мода: {u['name']}\n"
                f"Последнее обновление: {u['date_updated']}\n"
                f"Ссылка: {u['url']}")
        payload = {
            'chat_id': chat_id,
            'text': text,
            'disable_web_page_preview': True
        }
        try:
            resp = requests.post(base_url, json=payload, timeout=10)
            if not resp.ok:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
            else:
                logger.info(f"Sent Telegram message for {u['name']}")
        except Exception as e:
            logger.error(f"Error sending Telegram message for {u['name']}: {e}")
        time.sleep(1)

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
    parser.add_argument(
        "--send-telegram", action='store_true',
        help="Отправить результаты в Telegram бот"
    )
    args = parser.parse_args()

    updates = fetch_all_updates(args.mods_url)
    print_table(updates)

    if args.output:
        out = [{k: v for k, v in u.items() if k != 'raw_date'} for u in updates]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {args.output}")

    if args.send_telegram:
        send_telegram(updates)

if __name__ == "__main__":
    main()
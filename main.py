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

    # Extract latest release data
    latest = data.get("latest", {})
    version = latest.get("version_number")
    raw_date = data.get("date_updated")
    try:
        dt = datetime.fromisoformat(raw_date.rstrip('Z'))
        formatted_date = dt.strftime("%Y-%m-%d, %H:%M:%S")
    except Exception:
        formatted_date = raw_date

    # Additional fields for full output
    description = latest.get("description", "")
    icon_url = latest.get("icon", "")
    full_name = latest.get("full_name", "")

    # Correct download URL from API
    download_url = latest.get("download_url")
    # Package page URL from API data or fallback
    page_url = f"https://thunderstore.io/c/{channel}/p/{owner}/{package}/"

    return {
        "name": full_name or f"{owner}/{package}",
        "description": description,
        "url": page_url,
        "download_url": download_url,
        "icon_url": icon_url,
        "channel": channel,
        "owner": owner,
        "package": package,
        "version": version,
        "date_updated": formatted_date,
        "full_name": full_name,
        "raw_date": raw_date
    }

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
                results.append(info)
            except Exception as e:
                logger.error(f"Error fetching {mod_name}: {e}")
    results.sort(key=lambda x: x.get("raw_date", ""), reverse=True)
    return results

def print_table(updates: List[Dict], full: bool = False):
    if not updates:
        print(Fore.RED + "No updates found.")
        return

    if full:
        headers = [
            "Name", "Description", "URL", "Download URL", "Icon URL", "Channel",
            "Owner", "Package", "Version", "Date Updated", "Full Name"
        ]
        rows = [[
            u.get("name", ""),
            u.get("description", ""),
            u.get("url", ""),
            u.get("download_url", ""),
            u.get("icon_url", ""),
            u.get("channel", ""),
            u.get("owner", ""),
            u.get("package", ""),
            u.get("version", ""),
            u.get("date_updated", ""),
            u.get("full_name", "")
        ] for u in updates]
    else:
        headers = ["Name", "Version", "Date Updated", "URL"]
        rows = [[
            u.get("name", ""),
            u.get("version", ""),
            u.get("date_updated", ""),
            u.get("url", "")
        ] for u in updates]

    col_widths = [max(len(headers[i]), max(len(str(row[i])) for row in rows)) for i in range(len(headers))]
    border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(border)
    header_line = (
        "| " + " | ".join(Fore.CYAN + headers[i].ljust(col_widths[i]) + Style.RESET_ALL for i in range(len(headers))) + " |"
    )
    print(header_line)
    print(border)
    for row in rows:
        line = "| " + " | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(row))) + " |"
        print(line)
    print(border)

def send_telegram(received: int, total: int):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        logger.error("Telegram token or chat_id not set in environment")
        return
    base_url = f"https://api.telegram.org/bot{token}/sendMessage"
    text = f"Здравствуйте, guerra. Информация о модах для R.E.P.O загружена на GitHub. \nПолучено {received} из {total} модов на Thunderstore."
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
            logger.info("Sent Telegram summary message")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

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
        help="Отправить сводку в Telegram о количестве полученных модов"
    )
    parser.add_argument(
        "--full-output", action='store_true',
        help="Выводить всю информацию о модах (name, description, url, download_url, icon_url, channel, owner, package, version, date_updated, full_name)"
    )
    args = parser.parse_args()

    # Fetch initial mod list to count total
    try:
        mods_resp = requests.get(args.mods_url, timeout=10)
        mods_resp.raise_for_status()
        mods_data = mods_resp.json()
        total_mods = len(mods_data.get("repo_mods", []))
    except Exception as e:
        logger.error(f"Error fetching mod list: {e}")
        total_mods = 0

    updates = fetch_all_updates(args.mods_url)
    print_table(updates, full=args.full_output)

    if args.output:
        if args.full_output:
            out = [{k: v for k, v in u.items() if k != 'raw_date'} for u in updates]
        else:
            out = [{
                'name': u['name'],
                'version': u['version'],
                'date_updated': u['date_updated'],
                'url': u['url']
            } for u in updates]
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {args.output}")

    if args.send_telegram:
        send_telegram(len(updates), total_mods)

if __name__ == "__main__":
    main()
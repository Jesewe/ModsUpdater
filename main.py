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
PREVIOUS_OUTPUT_URL = (
    "https://raw.githubusercontent.com/Jesewe/ModsUpdater/"
    "main/.github/output.json"
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Colorama for colored terminal output
init(autoreset=True)

def parse_mod_url(url: str) -> Dict[str, str]:
    """
    Parse a Thunderstore mod URL and extract channel, owner, and package.
    """
    pattern = (
        r'https?://thunderstore\.io/c/(?P<channel>[^/]+)/'
        r'p/(?P<owner>[^/]+)/(?P<package>[^/]+)/?'
    )
    match = re.match(pattern, url)
    if not match:
        raise ValueError(f"Invalid mod URL: {url}")
    channel = match.group('channel') or DEFAULT_CHANNEL
    owner = match.group('owner')
    package = match.group('package')
    return {"channel": channel, "owner": owner, "package": package}


def get_latest_mod_info(channel: str, owner: str, package: str) -> Dict:
    """
    Retrieve the latest version information for a given mod from Thunderstore API.
    """
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

    return {
        "name": latest.get("full_name") or f"{owner}/{package}",
        "version": version,
        "date_updated": formatted_date,
        "url": (
            f"https://thunderstore.io/c/{channel}/p/{owner}/{package}/"
        ),
        "raw_date": raw_date,
    }


def fetch_all_updates(mods_url: str, max_workers: int = 5) -> List[Dict]:
    """
    Fetch update information for all mods listed in the given JSON URL.
    """
    resp = requests.get(mods_url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    mods = data.get("repo_mods", [])
    results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for mod in mods:
            try:
                parsed = parse_mod_url(mod.get("url", ""))
            except ValueError as e:
                logger.warning(f"Skipping invalid URL {mod.get('url')}: {e}")
                continue
            futures[executor.submit(
                get_latest_mod_info,
                parsed["channel"], parsed["owner"], parsed["package"]
            )] = mod.get("name")

        for future in as_completed(futures):
            mod_name = futures[future]
            try:
                info = future.result()
                results.append(info)
            except Exception as e:
                logger.error(f"Error fetching {mod_name}: {e}")

    results.sort(key=lambda x: x.get("raw_date", ""), reverse=True)
    return results


def load_previous_output() -> Dict[str, str]:
    """
    Download the previous output JSON from GitHub and return a dict mapping name to version.
    """
    try:
        resp = requests.get(PREVIOUS_OUTPUT_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {item['name']: item.get('version') for item in data}
    except Exception as e:
        logger.warning(f"Failed to load previous output: {e}")
        return {}


def compute_updates(new_data: List[Dict], prev_versions: Dict[str, str]) -> List[str]:
    """
    Compare new data with previous versions and return a list of updated mod names.
    """
    updates = []
    for mod in new_data:
        name = mod.get('name')
        version = mod.get('version')
        if not name or not version:
            continue
        prev = prev_versions.get(name)
        if prev is None or prev != version:
            updates.append(name)
    return updates


def print_table(updates: List[Dict], full: bool = False):
    """
    Print a formatted table of mod updates. Use full=True for detailed output.
    """
    if not updates:
        print(Fore.RED + "No updates found.")
        return

    if full:
        headers = ["Name", "Version", "Date Updated", "URL"]
        rows = [[u.get("name"), u.get("version"), u.get("date_updated"), u.get("url")] for u in updates]
    else:
        headers = ["Name", "Version", "Date Updated", "URL"]
        rows = [[u.get("name"), u.get("version"), u.get("date_updated"), u.get("url")] for u in updates]

    col_widths = [max(len(str(h)), *(len(str(row[i])) for row in rows)) for i, h in enumerate(headers)]
    border = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    print(border)
    header_line = (
        "| " + " | ".join(
            Fore.CYAN + headers[i].ljust(col_widths[i]) + Style.RESET_ALL
            for i in range(len(headers))
        ) + " |"
    )
    print(header_line)
    print(border)
    for row in rows:
        print("| " + " | ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(headers))) + " |")
    print(border)


def send_telegram(updated: List[str]):
    """
    Send a Telegram message listing updated mods, or notify if no updates.
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        logger.error("Telegram token or chat_id not set in environment variables.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    if updated:
        message = "The following Thunderstore mods have been updated:\n" + "\n".join(f"- {name}" for name in updated)
    else:
        message = "No mod updates detected."

    payload = {'chat_id': chat_id, 'text': message, 'disable_web_page_preview': True}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
        else:
            logger.info("Telegram notification sent successfully.")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Thunderstore mod versions, detect changes, and optionally notify via Telegram."
    )
    parser.add_argument(
        "--mods-url",
        default="https://mods-guerra.netlify.app/mods.json",
        help="URL to the JSON file containing the list of mods."
    )
    parser.add_argument(
        "--output", "-o",
        help="File path to save the result in JSON format."
    )
    parser.add_argument(
        "--send-telegram", action='store_true',
        help="Send a Telegram notification with the list of updated mods."
    )
    parser.add_argument(
        "--full-output", action='store_true',
        help="Include detailed mod information in the output."
    )
    args = parser.parse_args()

    # Load previous versions
    previous_versions = load_previous_output()

    # Fetch latest mod data
    latest_mods = fetch_all_updates(args.mods_url)

    # Determine which mods were updated
    updated_mods = compute_updates(latest_mods, previous_versions)

    # Print table of latest mods
    print_table(latest_mods, full=args.full_output)

    # Save current output if requested
    if args.output:
        output_data = latest_mods
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Results saved to {args.output}")

    # Send Telegram notification if requested
    if args.send_telegram:
        send_telegram(updated_mods)

if __name__ == '__main__':
    main()
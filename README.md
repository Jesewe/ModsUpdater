## Overview

This Python script automatically retrieves information about the latest versions of mods (modifications) from Thunderstore.io, formats the results, and displays them in the console. It can also save the data to a JSON file and send a summary to Telegram.

## Installation

1. Clone the repository.
2. Ensure you have Python 3.7 or newer installed.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   The `requirements.txt` should contain:
   ```text
   requests
   colorama
   python-dotenv
   ```

## Environment Variables

Use a `.env` file (loaded via `python-dotenv`) to configure:

- `TELEGRAM_BOT_TOKEN` — Telegram bot token for sending messages.
- `TELEGRAM_CHAT_ID` — Chat ID where the summary will be sent.

Example `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHijklmnOPQRSTuvWxYZ
TELEGRAM_CHAT_ID=987654321
```

## Command-Line Usage

```bash
python main.py [--mods-url URL] [--output OUTPUT_FILE] [--full-output] [--send-telegram]
```

### Options

- `--mods-url` — URL of the JSON file containing the list of mods (default: `https://mods-guerra.netlify.app/mods.json`).
- `--output`, `-o` — Path to save the result in JSON format.
- `--full-output` — Display all available fields for each mod (name, description, URL, download URL, icon URL, channel, owner, package, version, date updated, full name).
- `--send-telegram` — Send a summary message to Telegram.

## Core Components

### Functions

#### `parse_mod_url(url: str) -> Dict[str, str]`

Parses a Thunderstore mod URL and extracts:

- `channel` (e.g., `c/repo`),
- `owner` (repository owner),
- `package` (package name).

Raises `ValueError` if the URL does not match the expected pattern.

```python
parsed = parse_mod_url("https://thunderstore.io/c/repo/p/owner/package/")
# {'channel': 'repo', 'owner': 'owner', 'package': 'package'}
```

#### `get_latest_mod_info(channel: str, owner: str, package: str) -> Dict`

Requests `https://thunderstore.io/api/experimental/package/{owner}/{package}/` and returns detailed information about the latest release, including:

- `name`, `description`, `version`, `date_updated`,
- `url`, `download_url`, `icon_url`,
- internal fields `channel`, `owner`, `package`.

#### `fetch_all_updates(mods_url: str, max_workers: int = 5) -> List[Dict]`

1. Downloads a JSON file from `mods_url` containing a list of mods.
2. Uses a `ThreadPoolExecutor` to fetch latest release info for each mod in parallel.
3. Sorts the resulting list by update date in descending order.

Returns a list of dictionaries with the fields returned by `get_latest_mod_info`.

#### `print_table(updates: List[Dict], full: bool = False)`

Prints the update information in a console table:

- Summary mode (`full=False`): `Name`, `Version`, `Date Updated`, `URL`.
- Full mode (`full=True`): all available fields.

Uses `colorama` to highlight the headers.

#### `send_telegram(received: int, total: int)`

Sends a Telegram message summarizing the number of mods processed:

```
Received {received} out of {total} mods from Thunderstore.
```

Relies on `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables.

## Usage Examples

1. **Print a summary to the console**:

   ```bash
   python main.py
   ```

2. **Save summary to a file**:

   ```bash
   python main.py --output mods_summary.json
   ```

3. **Full output and send summary to Telegram**:

   ```bash
   python main.py --full-output --send-telegram
   ```

## Logging

Uses Python's standard `logging` module:

- Default level: `INFO`.
- Warnings for URL parsing errors and HTTP request failures are logged.

## Error Handling

- **HTTP**: raises `HTTPError` on request failures.
- **URL Parsing**: invalid URLs are skipped with a logged `warning`.

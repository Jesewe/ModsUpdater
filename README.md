This Python script automatically retrieves information about the latest versions of mods (modifications) from Thunderstore.io, detects which mods have been updated since the last run, formats the results, and displays them in the console. It can also save the data to a JSON file and send detailed notifications to Telegram.

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

Configure a `.env` file (loaded via `python-dotenv`) with the following variables:

- `TELEGRAM_BOT_TOKEN` — Telegram bot token for sending messages.
- `TELEGRAM_CHAT_ID` — Chat ID where the notifications will be sent.

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
- `--full-output` — Include all available fields for each mod in the console output.
- `--send-telegram` — Send a Telegram notification listing updated mods.

## Core Components

### `load_previous_output() -> Dict[str, str]`

Downloads the previous run's output JSON from the GitHub repository and returns a mapping of `mod_name -> version`. If the file cannot be fetched, an empty map is returned.

### `fetch_all_updates(mods_url: str, max_workers: int = 5) -> List[Dict]`

1. Downloads the JSON file at `mods_url`, which contains an array of mods with their Thunderstore URLs.
2. Parses each URL to extract `channel`, `owner`, and `package`.
3. Queries the Thunderstore API in parallel to retrieve the latest version info for each mod.
4. Sorts the results by update date in descending order.

Returns a list of dictionaries each containing:

- `name`: Full mod name.
- `version`: Latest version string.
- `date_updated`: Formatted timestamp of last update.
- `url`: Direct link to the mod page.

### `compute_updates(new_data: List[Dict], prev_versions: Dict[str, str]) -> List[str]`

Compares the newly fetched data with the previously stored versions and returns a list of mod names that have changed (i.e., new or updated mods).

### `print_table(updates: List[Dict], full: bool = False)`

Prints a formatted console table of mod data.

- **Summary mode** (`full=False`): Columns: `Name`, `Version`, `Date Updated`, `URL`.
- **Full mode** (`full=True`): Same columns, but designed to expand if more fields are added.

Uses `colorama` to colorize headers and highlight missing updates.

### `send_telegram(updated: List[str])`

Sends a Telegram message:

- If `updated` is non-empty, lists each updated mod on a separate line.
- If empty, sends "No mod updates detected."

Relies on `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables.

## Usage Examples

1. **Display summary in console**:

   ```bash
   python main.py
   ```

2. **Save summary to JSON file**:

   ```bash
   python main.py --output mods_summary.json
   ```

3. **Detect changes and send Telegram notification**:

   ```bash
   python main.py --send-telegram
   ```

4. **Full output with detailed fields and notification**:

   ```bash
   python main.py --full-output --send-telegram
   ```

## Logging

The script uses Python's built-in `logging` module:

- **Level**: `INFO` by default.
- **Warnings**: Invalid URLs or failed HTTP requests.
- **Errors**: Failed API calls or missing environment variables.

## Error Handling

- **HTTP Errors**: Raises `HTTPError` on non-successful responses.
- **URL Parsing**: Invalid mod URLs are skipped with a logged warning.

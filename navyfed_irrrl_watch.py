#!/usr/bin/env python3
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import re, json
from datetime import datetime

load_dotenv()

TARGET_RATE  = float(os.environ["TARGET_RATE"])
NTFY_TOPIC   = os.environ["NTFY_TOPIC"]
NTFY_SERVER  = os.environ["NTFY_SERVER"].rstrip("/")
NTFY_TOKEN   = os.environ.get("NTFY_TOKEN", "").strip()
STATE_FILE   = os.environ["STATE_FILE"]

RATES_URL = "https://web.navyfederal.org/assets/rates/printMortRatesAll.php"

def fetch_rates():
    """Returns (rate_30yr, rate_15yr) as floats. Raises on any failure."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; rate-monitor/1.0)"}
    resp = requests.get(RATES_URL, headers=headers, timeout=15)
    resp.raise_for_status()  # Raises HTTPError on 4xx/5xx

    lines = [l.strip() for l in BeautifulSoup(resp.text, "html.parser").get_text().splitlines()]

    # Anchor to the VA Loan Rates section so we don't pick up other 30/15-Year rows
    va_start = next((i for i, l in enumerate(lines) if "VA Loan Rates" in l), None)
    if va_start is None:
        raise ValueError("Could not find 'VA Loan Rates' section on page")

    va_section = lines[va_start : va_start + 60]

    rates = {}
    for term, label in (("30", "30 Year"), ("15", "15 Year")):
        try:
            idx = next(i for i, l in enumerate(va_section) if l == label)
            rate_str = next(
                l for l in va_section[idx + 1 : idx + 6]
                if re.match(r'^\d+\.\d+%$', l)
            )
            rates[term] = float(rate_str.rstrip("%"))
        except StopIteration:
            raise ValueError(f"Could not find VA {term}-yr rate in VA Loan Rates section")

    return rates["30"], rates["15"]

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(data: dict):
    with open(STATE_FILE, "w") as f:
        json.dump({**data, "checked": datetime.now().isoformat()}, f)

def send_ntfy(title, message, priority="default", tags="") -> bool:
    try:
        headers = {
            "Title": title,
            "Priority": priority,
            "Tags": tags,
        }
        if NTFY_TOKEN:
            headers["Authorization"] = f"Bearer {NTFY_TOKEN}"
        resp = requests.post(
            f"{NTFY_SERVER}/{NTFY_TOPIC}",
            data=message,
            headers=headers,
            timeout=10,
        )
        if not resp.ok:
            print(f"[{datetime.now()}] WARNING: ntfy returned {resp.status_code}: {resp.text.strip()}")
            return False
        return True
    except Exception as e:
        print(f"[{datetime.now()}] WARNING: ntfy send failed: {e}")
        return False

def main():
    state = load_state()

    # --- Fetch rates ---
    try:
        rate_30, rate_15 = fetch_rates()
    except requests.exceptions.ConnectionError as e:
        msg = f"Could not reach Navy Federal rates page.\n\nURL: {RATES_URL}\nError: {e}"
        send_ntfy("IRRRL Watch: Connection Failed", msg, priority="high", tags="warning")
        print(f"[{datetime.now()}] ERROR: Connection failed — {e}")
        return
    except requests.exceptions.HTTPError as e:
        msg = f"Navy Federal rates page returned an error.\n\nStatus: {e.response.status_code}\nURL: {RATES_URL}"
        send_ntfy("IRRRL Watch: Page Error", msg, priority="high", tags="warning")
        print(f"[{datetime.now()}] ERROR: HTTP {e.response.status_code}")
        return
    except requests.exceptions.Timeout:
        msg = f"Request to Navy Federal rates page timed out after 15s.\n\nURL: {RATES_URL}"
        send_ntfy("IRRRL Watch: Timeout", msg, priority="default", tags="warning")
        print(f"[{datetime.now()}] ERROR: Request timed out")
        return
    except ValueError as e:
        msg = (
            f"The rates page loaded but the VA IRRRL rate couldn't be parsed.\n\n"
            f"Navy Federal may have changed their page layout.\n\nDetail: {e}"
        )
        send_ntfy("IRRRL Watch: Parse Failed", msg, priority="high", tags="warning,mag")
        print(f"[{datetime.now()}] ERROR: Parse failed — {e}")
        return

    print(f"[{datetime.now()}] VA IRRRL — 30yr: {rate_30}%  |  15yr: {rate_15}%")

    # --- Check against target ---
    last_30 = state.get("rate_30")

    if rate_30 < TARGET_RATE:
        if rate_30 != last_30:  # Only notify on change to avoid spam
            msg = (
                f"VA IRRRL 30-yr rate is now {rate_30}% — below your {TARGET_RATE}% target!\n\n"
                f"30-yr: {rate_30}%\n"
                f"15-yr: {rate_15}%\n\n"
                f"Check Navy Federal now: navyfederal.org"
            )
            sent = send_ntfy(
                f"VA IRRRL Alert: {rate_30}% (30-yr)",
                msg,
                priority="high",
                tags="moneybag,house"
            )
            if sent:
                print(f"[{datetime.now()}] ALERT SENT")
                save_state({"rate_30": rate_30, "rate_15": rate_15})
            # If send failed, don't update state so we retry next run
        else:
            print(f"  Rate unchanged at {rate_30}%, no alert.")
            save_state({"rate_30": rate_30, "rate_15": rate_15})
    else:
        print(f"  30-yr rate above target ({TARGET_RATE}%), no alert.")
        save_state({"rate_30": rate_30, "rate_15": rate_15})

if __name__ == "__main__":
    main()
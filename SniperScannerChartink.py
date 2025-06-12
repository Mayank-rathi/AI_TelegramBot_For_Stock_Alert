import pandas as pd
import requests
from bs4 import BeautifulSoup as bs
import time
import logging
import datetime
import sys
import os
import psutil
import signal
import atexit
from functools import wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from config import *
import pytz

# === Timezone Setup ===
IST = pytz.timezone('Asia/Kolkata')
UTC = pytz.UTC

def get_ist_time():
    """Get current time in IST"""
    return datetime.datetime.now(IST)

def convert_to_ist(utc_time):
    """Convert UTC time to IST"""
    if utc_time.tzinfo is None:
        utc_time = UTC.localize(utc_time)
    return utc_time.astimezone(IST)

# === Logging Setup ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("chartink_bot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# === Retry Decorator ===
def retry_on_failure(max_retries=MAX_RETRIES, backoff=RETRY_BACKOFF):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = backoff * (2 ** attempt)
                    logging.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time:.2f}s...")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

# === Process Management ===
def create_pid_file():
    """Create a PID file to track the process"""
    pid = str(os.getpid())
    with open("chartink_bot.pid", "w") as f:
        f.write(pid)
    return pid

def remove_pid_file():
    """Remove the PID file when the script exits"""
    try:
        os.remove("chartink_bot.pid")
    except:
        pass

def check_if_already_running():
    """Check if another instance is already running"""
    try:
        with open("chartink_bot.pid", "r") as f:
            pid = int(f.read().strip())
        try:
            process = psutil.Process(pid)
            if process.name().lower().startswith("python"):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    except:
        pass
    return False

# === Session Setup with Retry ===
def create_session_with_retry():
    session = requests.Session()
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=RETRY_STATUS_FORCELIST
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# === Start Sessions ===
chartink_session = create_session_with_retry()
telegram_session = create_session_with_retry()

@retry_on_failure()
def fetch_chartink_data():
    try:
        r = chartink_session.get(CHARTINK_URL)
        soup = bs(r.content, "html.parser")
        token = soup.find("meta", {"name": "csrf-token"})["content"]
        headers = {"x-csrf-token": token}

        res = chartink_session.post(CHARTINK_URL, headers=headers, data=SCAN_CLAUSE)
        res.raise_for_status()

        data = res.json()
        if not data.get("data"):
            logging.warning("No data received from Chartink")
            return pd.DataFrame()
        return pd.DataFrame(data["data"])
    except Exception as e:
        logging.error(f"Chartink fetch failed: {e}")
        raise

@retry_on_failure()
def send_to_telegram(df):
    try:
        if df.empty:
            message = "No stocks matched the condition."
        else:
            message = "Chartink Signal Results:\n\n"
            message += "Sr | NSE Code | Close | Volume | Change%\n"
            message += "---|----------|--------|---------|--------\n"
            for _, row in df.iterrows():
                change_pct = row.get('per_chg', 0)
                message += f"{row['sr']:>2} | {row['nsecode']} | {row['close']:.2f} | {row['volume']:,} | {change_pct:+.2f}%\n"

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        response = telegram_session.post(url, data=payload, timeout=10)
        response.raise_for_status()
        logging.info("Telegram message sent successfully")
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")
        raise

def job():
    logging.info("Checking for signals...")
    df = fetch_chartink_data()
    send_to_telegram(df)

def is_trading_day():
    """Check if current day is a trading day (Monday to Friday)"""
    return get_ist_time().weekday() < 5

def get_next_run_time(now):
    """
    Returns the next datetime object at which the job should run.
    Trading time window: 09:15 to 15:15 IST
    Run every 15 minutes within this window.
    """
    # Convert input time to IST if it's not already
    if now.tzinfo is None:
        now = IST.localize(now)
    elif now.tzinfo != IST:
        now = now.astimezone(IST)

    # Define trading start and end time today in IST
    trading_start = now.replace(
        hour=TRADING_START_HOUR,
        minute=TRADING_START_MINUTE,
        second=0,
        microsecond=0
    )
    trading_end = now.replace(
        hour=TRADING_END_HOUR,
        minute=TRADING_END_MINUTE,
        second=0,
        microsecond=0
    )

    # If current time is before trading start today
    if now < trading_start:
        return trading_start

    # If current time is after trading end today
    if now > trading_end:
        # Schedule for next trading day at 9:15 IST
        next_day = now + datetime.timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip Sat(5) and Sun(6)
            next_day += datetime.timedelta(days=1)
        return next_day.replace(
            hour=TRADING_START_HOUR,
            minute=TRADING_START_MINUTE,
            second=0,
            microsecond=0
        )

    # If within trading hours, find next interval
    minutes = (now.minute // SCAN_INTERVAL_MINUTES + 1) * SCAN_INTERVAL_MINUTES
    hour = now.hour
    if minutes == 60:
        minutes = 0
        hour += 1

    candidate = now.replace(hour=hour, minute=minutes, second=0, microsecond=0)
    if candidate > trading_end:
        # Next run is next trading day
        next_day = now + datetime.timedelta(days=1)
        while next_day.weekday() >= 5:
            next_day += datetime.timedelta(days=1)
        return next_day.replace(
            hour=TRADING_START_HOUR,
            minute=TRADING_START_MINUTE,
            second=0,
            microsecond=0
        )

    return candidate

def main_loop():
    while True:
        try:
            now = get_ist_time()
            
            # If it's a weekend, wait until next Monday
            if not is_trading_day():
                next_day = now + datetime.timedelta(days=(7 - now.weekday()))  # Next Monday
                next_run = next_day.replace(
                    hour=TRADING_START_HOUR,
                    minute=TRADING_START_MINUTE,
                    second=0,
                    microsecond=0
                )
                wait_seconds = (next_run - now).total_seconds()
                logging.info(f"Weekend detected. Sleeping until next Monday {TRADING_START_HOUR:02d}:{TRADING_START_MINUTE:02d} IST")
                time.sleep(wait_seconds)
                continue

            # Get next run time
            next_run = get_next_run_time(now)
            wait_seconds = (next_run - now).total_seconds()
            
            # If we're past trading hours, wait until next trading day
            if wait_seconds > 24 * 3600:  # More than 24 hours
                logging.info(f"Past trading hours. Sleeping until next trading day at {TRADING_START_HOUR:02d}:{TRADING_START_MINUTE:02d} IST")
                time.sleep(wait_seconds)
                continue

            # Normal case - wait until next interval
            if wait_seconds > 0:
                logging.info(f"Sleeping for {int(wait_seconds)} seconds until next run at {next_run.strftime('%H:%M:%S')} IST")
                time.sleep(wait_seconds)
            else:
                # Just in case (very rare)
                time.sleep(1)

            # Run the job exactly at the scheduled time
            job()
            
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            time.sleep(60)  # Wait a minute before retrying
            continue

def signal_handler(signum, frame):
    """Handle termination signals gracefully"""
    logging.info("Received termination signal. Cleaning up...")
    remove_pid_file()
    sys.exit(0)

if __name__ == "__main__":
    # Check if already running
    if check_if_already_running():
        logging.error("Another instance is already running. Exiting.")
        sys.exit(1)

    # Create PID file
    create_pid_file()
    atexit.register(remove_pid_file)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        logging.info("Starting Chartink Bot...")
        main_loop()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
    finally:
        remove_pid_file()

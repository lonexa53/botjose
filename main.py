import requests
import time
import json
from datetime import datetime
import logging
from typing import Dict, Tuple, Optional
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('odds_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
ODDS_API = os.getenv("ODDS_API", "https://feeds.sportbet.com/odds/live")
CHECK_INTERVAL = float(os.getenv("CHECK_INTERVAL", "0.5"))
SHIFT_THRESHOLD = float(os.getenv("SHIFT_THRESHOLD", "0.15"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

last_odds: Dict = {}
error_count = 0

def fetch_odds(match_id: str) -> Optional[Dict]:
    """
    Fetch current odds from the API.
    
    Args:
        match_id: The match identifier
        
    Returns:
        Dictionary of odds or None if failed
    """
    try:
        headers = {
            'User-Agent': 'BotJose/1.0',
            'Authorization': f"Bearer {os.getenv('API_KEY', '')}"
        }
        response = requests.get(
            f"{ODDS_API}/{match_id}",
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None

def detect_shift(new_odds: Dict, old_odds: Dict, threshold: float = SHIFT_THRESHOLD) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Detect if any market moved more than the threshold.
    
    Args:
        new_odds: Current odds dictionary
        old_odds: Previous odds dictionary
        threshold: Change threshold percentage
        
    Returns:
        Tuple of (changed: bool, market: str, change_amount: float)
    """
    markets = ['over_0.5', 'next_goal', 'match_odds']
    
    for market in markets:
        new_val = new_odds.get(market, 0)
        old_val = old_odds.get(market, 0)
        
        if old_val > 0:
            change = abs(new_val - old_val) / old_val
            if change > threshold:
                return True, market, new_val - old_val
    
    return False, None, None

def send_notification(title: str, message: str) -> bool:
    """
    Send notification via configured service (Pushover, Telegram, etc).
    
    Args:
        title: Notification title
        message: Notification message
        
    Returns:
        Success status
    """
    notification_service = os.getenv("NOTIFICATION_SERVICE", "console")
    
    if notification_service == "pushover":
        return send_pushover(title, message)
    elif notification_service == "telegram":
        return send_telegram(title, message)
    else:
        logger.info(f"[NOTIFICATION] {title}: {message}")
        return True

def send_pushover(title: str, message: str) -> bool:
    """Send notification via Pushover."""
    try:
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": os.getenv("PUSHOVER_APP_TOKEN"),
                "user": os.getenv("PUSHOVER_USER_KEY"),
                "title": title,
                "message": message,
                "priority": 1
            },
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Pushover notification failed: {e}")
        return False

def send_telegram(title: str, message: str) -> bool:
    """Send notification via Telegram."""
    try:
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={
                "chat_id": chat_id,
                "text": f"*{title}*\n{message}",
                "parse_mode": "Markdown"
            },
            timeout=5
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Telegram notification failed: {e}")
        return False

def main():
    """Main monitoring loop."""
    global last_odds, error_count
    
    logger.info("Starting BotJose odds monitor...")
    match_id = os.getenv("MATCH_ID", "12345")
    
    while True:
        try:
            current = fetch_odds(match_id)
            
            if current is None:
                error_count += 1
                if error_count >= MAX_RETRIES:
                    logger.error("Max retries reached, restarting...")
                    error_count = 0
                time.sleep(CHECK_INTERVAL * 2)
                continue
            
            error_count = 0
            
            if last_odds:
                changed, market, change_amount = detect_shift(current, last_odds)
                if changed:
                    old_value = last_odds.get(market, 0)
                    new_value = current.get(market, 0)
                    message = f"Market shift detected!\n{market}: {old_value:.3f} → {new_value:.3f} (Δ {change_amount:+.3f})"
                    logger.warning(message)
                    send_notification("Odds Shift Alert", message)
            
            last_odds = current
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            error_count += 1
            time.sleep(1)

if __name__ == "__main__":
    main()
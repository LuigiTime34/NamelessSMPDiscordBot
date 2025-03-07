import datetime
import os

# Log directory on disk
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# File logger that everyone can use
def log(message):
    """Log a message to a file and console - can be called from anywhere"""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    formatted_message = f"[{timestamp}] {message}"
    
    # Print to console
    print(formatted_message)
    
    # Log to file
    try:
        log_file = os.path.join(LOG_DIR, f"{datetime.date.today().strftime('%Y-%m-%d')}.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(formatted_message + "\n")
    except Exception as e:
        print(f"Error writing to log file: {e}")

# Discord channel logger - only call from async functions with bot
async def log_to_discord(bot, message):
    """Send a log message to Discord - only call from async context with bot"""
    from const import LOG_CHANNEL_ID
    
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        try:
            await channel.send(message)
        except Exception as e:
            print(f"Error sending log to Discord: {e}")
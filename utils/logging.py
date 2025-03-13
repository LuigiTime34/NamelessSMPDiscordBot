# discord_logging.py
import discord
import logging
import sys
import datetime
import asyncio


class DiscordHandler(logging.Handler):
    """Custom logging handler that sends logs to a Discord channel in real-time"""
    def __init__(self, bot, channel_id):
        logging.Handler.__init__(self)
        self.bot = bot
        self.channel_id = channel_id
        self.ready = False

    async def send_log(self, record):
        """Sends a log message to the Discord channel immediately"""
        if not self.ready:
            return
            
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            print(f"WARNING: Could not find logging channel with ID {self.channel_id}")
            return
            
        try:
            # Create more compact embed
            embed = discord.Embed(
                description=f"**{record.levelname}**: {record.getMessage()}",
                color=self._get_color(record.levelname),
                timestamp=datetime.datetime.now()
            )
            embed.set_footer(text=f"{record.module}.{record.funcName}:{record.lineno}")
            
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Error sending log to Discord: {e}")

    def _get_color(self, level_name):
        """Returns color based on log level"""
        colors = {
            'DEBUG': discord.Color.light_grey(),
            'INFO': discord.Color.green(),
            'WARNING': discord.Color.gold(),
            'ERROR': discord.Color.red(),
            'CRITICAL': discord.Color.dark_red()
        }
        return colors.get(level_name, discord.Color.default())

    def emit(self, record):
        """Immediately sends log records to Discord"""
        if self.ready and self.bot.is_ready():
            # Create a task to send the log right away
            asyncio.create_task(self.send_log(record))

    def set_ready(self, ready):
        """Sets the ready state of the handler"""
        self.ready = ready


def setup_logging(bot, logging_channel_id, level=logging.INFO):
    """Set up logging to console and Discord channel"""
    # Create logger
    logger = logging.getLogger('nameless_bot')
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Create Discord handler
    discord_handler = DiscordHandler(bot, logging_channel_id)
    discord_handler.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Add formatter to handlers
    console_handler.setFormatter(formatter)
    discord_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(discord_handler)
    
    return logger, discord_handler
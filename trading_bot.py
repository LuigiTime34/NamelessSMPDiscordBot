import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
import trading_db.trading_bot_const
from typing import Optional
from trading_db.trading_database import Database
import logging
import sys
from utils.logging import setup_logging, DiscordHandler
import os
from dotenv import load_dotenv

load_dotenv()

# Set up intents
intents = discord.Intents.all()
intents.reactions = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
db = Database()
active_trades = {}

# Setup logger (but don't initialize it fully yet)
logger = None
discord_handler = None

# Rest of your TradeModal class remains the same
class TradeModal(discord.ui.Modal):
    def __init__(self, duration_value):
        super().__init__(title="Create a Trade")
        self.duration = duration_value
        
        self.offering = discord.ui.TextInput(
            label="What are you offering?",
            placeholder="Items, services, or resources you're offering...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        
        self.looking_for = discord.ui.TextInput(
            label="What are you looking for?",
            placeholder="Items, services, or resources you want...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        
        self.additional_details = discord.ui.TextInput(
            label="Additional Details (Optional)",
            placeholder="Time, location, or other details...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )
        
        self.add_item(self.offering)
        self.add_item(self.looking_for)
        self.add_item(self.additional_details)

    async def on_submit(self, interaction: discord.Interaction):
        # Calculate end time
        end_time = datetime.datetime.now() + self.duration
        
        # Create embed
        embed = discord.Embed(
            title="New Trade",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        embed.add_field(name="Offering", value=self.offering.value, inline=False)
        embed.add_field(name="Looking For", value=self.looking_for.value, inline=False)
        
        if self.additional_details.value:
            embed.add_field(name="Additional Details", value=self.additional_details.value, inline=False)
        
        embed.add_field(name="Trade Ends", value=f"<t:{int(end_time.timestamp())}:R>", inline=False)
        embed.set_footer(text=f"Trade ID: {interaction.user.id}-{int(datetime.datetime.now().timestamp())}")
        
        # Get user's highest role for ping
        top_role = interaction.user.top_role.mention if interaction.user.top_role.name != "@everyone" else ""
        
        # Send the trade message
        trade_message = await interaction.channel.send(
            f"{trading_db.trading_bot_const.TRADER_ROLE_MENTION} {interaction.user.mention} ({top_role}) is looking to trade!",
            embed=embed
        )
        
        # Create thread
        thread = await trade_message.create_thread(
            name=f"{interaction.user.display_name}'s Trade",
            auto_archive_duration=60
        )
        
        await thread.send(f"{interaction.user.mention} Use this thread for trade updates. Use `!endtrade` to close the trade early.")
        
        # Store trade info
        trade_id = f"{interaction.user.id}-{int(datetime.datetime.now().timestamp())}"
        active_trades[trade_id] = {
            "user_id": interaction.user.id,
            "message_id": trade_message.id,
            "thread_id": thread.id,
            "channel_id": interaction.channel_id,
            "end_time": end_time,
            "offering": self.offering.value,
            "looking_for": self.looking_for.value,
            "additional_details": self.additional_details.value
        }
        
        # Save to database
        db.add_trade(
            trade_id, 
            interaction.user.id, 
            trade_message.id, 
            thread.id, 
            interaction.channel_id, 
            end_time, 
            self.offering.value, 
            self.looking_for.value, 
            self.additional_details.value
        )
        
        # Log the new trade
        logger.info(f"New trade created by {interaction.user.display_name} (ID: {trade_id})")
        
        await interaction.response.send_message("Your trade has been posted!", ephemeral=True)


# Rest of your DurationSelect and TradeButton classes remain the same
class DurationSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 hour", value="1h"),
            discord.SelectOption(label="3 hours", value="3h"),
            discord.SelectOption(label="6 hours", value="6h"),
            discord.SelectOption(label="12 hours", value="12h"),
            discord.SelectOption(label="1 day", value="1d"),
            discord.SelectOption(label="3 days", value="3d"),
            discord.SelectOption(label="1 week", value="1w")
        ]
        super().__init__(placeholder="Select trade duration...", options=options)

    async def callback(self, interaction: discord.Interaction):
        # Convert selection to timedelta
        duration_map = {
            "1h": datetime.timedelta(hours=1),
            "3h": datetime.timedelta(hours=3),
            "6h": datetime.timedelta(hours=6),
            "12h": datetime.timedelta(hours=12),
            "1d": datetime.timedelta(days=1),
            "3d": datetime.timedelta(days=3),
            "1w": datetime.timedelta(days=7)
        }
        
        duration = duration_map[self.values[0]]
        modal = TradeModal(duration)
        await interaction.response.send_modal(modal)


class TradeButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Post a Trade", style=discord.ButtonStyle.primary, custom_id="trade_button")
    async def trade_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Add duration selector
        view = discord.ui.View(timeout=300)
        view.add_item(DurationSelect())
        await interaction.response.send_message("How long should your trade stay active?", view=view, ephemeral=True)


@bot.event
async def on_ready():
    global logger, discord_handler
    
    # Initialize the logger now that the bot is ready
    logger, discord_handler = setup_logging(bot, trading_db.trading_bot_const.LOGGING_CHANNEL_ID)
    discord_handler.set_ready(True)
    
    logger.info(f"Bot started: {bot.user}")
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
    
    # Load active trades from database
    global active_trades
    active_trades = db.get_all_active_trades()
    logger.info(f"Loaded {len(active_trades)} active trades from database")
    
    # Add the trade button view to the bot
    bot.add_view(TradeButton())
    
    # Start the task to check for expired trades
    check_expired_trades.start()
    
    # Send the welcome message
    await send_welcome_message()


async def send_welcome_message():
    channel = bot.get_channel(trading_db.trading_bot_const.WELCOME_CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find welcome channel with ID {trading_db.trading_bot_const.WELCOME_CHANNEL_ID}")
        return
    
    # Check if welcome message ID exists in database
    message_id = db.get_welcome_message(trading_db.trading_bot_const.WELCOME_CHANNEL_ID)
    if message_id:
        try:
            # Try to fetch the message
            message = await channel.fetch_message(message_id)
            logger.info("Welcome message already exists")
            return
        except discord.NotFound:
            # Message was deleted, we'll create a new one
            logger.info("Welcome message not found, creating a new one")
            pass
    
    # Create embed
    embed = discord.Embed(
        title="Trading Hall",
        description=f"Welcome to the trading hall! React with {trading_db.trading_bot_const.TRADE_EMOJI} for trade updates and click the button below to post a trade.",
        color=discord.Color.gold()
    )
    
    # Send message with button
    view = TradeButton()
    welcome_message = await channel.send(embed=embed, view=view)
    
    # Add reaction
    await welcome_message.add_reaction(trading_db.trading_bot_const.TRADE_EMOJI)
    
    # Save welcome message ID to database
    db.save_welcome_message(trading_db.trading_bot_const.WELCOME_CHANNEL_ID, welcome_message.id)
    logger.info(f"Created new welcome message (ID: {welcome_message.id})")


@bot.event
async def on_raw_reaction_add(payload):
    # Ignore bot's own reactions
    if payload.user_id == bot.user.id:
        return
    
    channel = bot.get_channel(payload.channel_id)
    if channel.id != trading_db.trading_bot_const.WELCOME_CHANNEL_ID:
        return
    
    # Check if the reaction is on the welcome message and is the trade emoji
    if str(payload.emoji) == trading_db.trading_bot_const.TRADE_EMOJI:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        trader_role = guild.get_role(trading_db.trading_bot_const.TRADER_ROLE_ID)
        
        if trader_role:
            await member.add_roles(trader_role)
            logger.info(f"Added trader role to {member.display_name} (ID: {member.id})")


@bot.event
async def on_raw_reaction_remove(payload):
    channel = bot.get_channel(payload.channel_id)
    if channel.id != trading_db.trading_bot_const.WELCOME_CHANNEL_ID:
        return
    
    # Check if the reaction removed is the trade emoji
    if str(payload.emoji) == trading_db.trading_bot_const.TRADE_EMOJI:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        trader_role = guild.get_role(trading_db.trading_bot_const.TRADER_ROLE_ID)
        
        if trader_role and trader_role in member.roles:
            await member.remove_roles(trader_role)
            logger.info(f"Removed trader role from {member.display_name} (ID: {member.id})")


@bot.command()
async def endtrade(ctx):
    # Check if the command is in a thread
    if not isinstance(ctx.channel, discord.Thread):
        return
    
    # Find the trade associated with this thread
    trade_id = None
    for tid, trade in active_trades.items():
        if trade["thread_id"] == ctx.channel.id:
            trade_id = tid
            break
    
    if not trade_id:
        await ctx.send("Could not find an active trade associated with this thread.")
        logger.warning(f"User {ctx.author.display_name} attempted to end non-existent trade in thread {ctx.channel.id}")
        return
    
    # Check if the user is authorized to end the trade
    trade = active_trades[trade_id]
    guild = ctx.guild
    admin_role = guild.get_role(trading_db.trading_bot_const.ADMIN_ROLE_ID)
    
    if not (ctx.author.id == trade["user_id"] or (admin_role and admin_role in ctx.author.roles)):
        await ctx.send("Only the trade creator or an admin can end this trade.")
        logger.warning(f"Unauthorized user {ctx.author.display_name} attempted to end trade {trade_id}")
        return
    
    # End the trade
    is_admin = admin_role and admin_role in ctx.author.roles
    reason = "User requested trade closure" if ctx.author.id == trade["user_id"] else f"Admin {ctx.author.display_name} closed the trade"
    
    logger.info(f"Trade {trade_id} ending: {reason}")
    await end_trade(trade_id, reason)
    await ctx.send("Trade has been closed.")


async def end_trade(trade_id, reason):
    trade = active_trades.pop(trade_id, None)
    if not trade:
        logger.warning(f"Attempted to end non-existent trade {trade_id}")
        return
    
    # Remove from database
    db.remove_trade(trade_id)
    
    # Get the original message and update it
    channel = bot.get_channel(trade["channel_id"])
    try:
        message = await channel.fetch_message(trade["message_id"])
        
        # Update the embed to show it's closed
        embed = message.embeds[0]
        embed.color = discord.Color.red()
        embed.add_field(name="Status", value=f"Closed: {reason}", inline=False)
        
        # First update the message so users can see it's closed
        await message.edit(embed=embed)
        
        # Then delete the message
        await message.delete()
        
        # Archive the thread
        thread = bot.get_channel(trade["thread_id"])
        if thread:
            await thread.send(f"This trade has been closed. Reason: {reason}")
            await thread.edit(archived=True, locked=True)
        
        # Forward to archive channel
        archive_channel = bot.get_channel(trading_db.trading_bot_const.ARCHIVE_CHANNEL_ID)
        if archive_channel:
            archive_embed = discord.Embed(
                title="Trade Archived",
                color=discord.Color.dark_gray(),
                timestamp=datetime.datetime.now()
            )
            
            user = bot.get_user(trade["user_id"])
            archive_embed.add_field(name="Trader", value=f"{user.mention if user else 'Unknown'}", inline=True)
            archive_embed.add_field(name="Reason", value=reason, inline=True)
            archive_embed.add_field(name="Offering", value=trade["offering"], inline=False)
            archive_embed.add_field(name="Looking For", value=trade["looking_for"], inline=False)
            
            if trade["additional_details"]:
                archive_embed.add_field(name="Additional Details", value=trade["additional_details"], inline=False)
            
            archive_embed.set_footer(text=f"Trade ID: {trade_id}")
            
            await archive_channel.send(embed=archive_embed)
            
        logger.info(f"Successfully closed trade {trade_id}: {reason}")
    
    except discord.NotFound:
        logger.error(f"Could not find message for trade {trade_id}")
    except Exception as e:
        logger.error(f"Error ending trade {trade_id}: {e}")


@tasks.loop(minutes=1)
async def check_expired_trades():
    now = datetime.datetime.now()
    expired_trades = []
    
    for trade_id, trade in active_trades.items():
        if trade["end_time"] <= now:
            expired_trades.append(trade_id)
    
    if expired_trades:
        logger.info(f"Found {len(expired_trades)} expired trades to close")
        
    for trade_id in expired_trades:
        await end_trade(trade_id, "Trade duration expired")


@check_expired_trades.before_loop
async def before_check_expired_trades():
    await bot.wait_until_ready()


# Add error handlers for better logging
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    
    logger.error(f"Command error in {ctx.command}: {error}")


@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Error in event {event}: {sys.exc_info()[1]}")


def run_bot():
    # Initialize a basic logger for startup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    temp_logger = logging.getLogger('startup')
    
    TOKEN = os.getenv("DISCORD_TOKEN_TRADE")
    if not TOKEN:
        print("Error: DISCORD_TOKEN_TRADE not found in .env file!")
        exit(1)
    
    temp_logger.info("Starting Discord Trading Bot")
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        temp_logger.critical(f"Failed to start bot: {e}")
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        if bot:
            # Close the bot's session
            try:
                bot.loop.run_until_complete(bot.close())
            except:
                pass
        exit(0)
    finally:
        # Close the database connection when the bot shuts down
        db.close()
        temp_logger.info("Bot shutdown complete")


if __name__ == "__main__":
    run_bot()
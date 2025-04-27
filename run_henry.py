import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="?", intents=intents)

@bot.event
async def on_message(message):
    # Don't respond to messages from the bot itself
    if message.author == bot.user:
        return

    # Check if the bot was mentioned in the message
    if bot.user.mentioned_in(message):
        await message.channel.send("I just [REDACTED] your mom!")
    
    # Process other commands
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(bot, f"{bot.user} is online!")

TOKEN = os.getenv("DISCORD_TOKEN_HENRY")
if not TOKEN:
    print("Error: DISCORD_TOKEN_HENRY not found in .env file!")
    exit(1)
bot.run(TOKEN)
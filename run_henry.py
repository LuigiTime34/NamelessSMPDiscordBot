import discord
from discord.ext import commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="?", intents=intents)

@bot.event
async def on_ready():
    print(bot, f"{bot.user} is online!")

with open('henry_token.txt', 'r') as f:
        TOKEN = f.readline().strip()
bot.run(TOKEN)
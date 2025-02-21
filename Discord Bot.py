import discord
from discord.ext import commands
from collections import defaultdict
import json
import os

# Initialize bot with required intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configuration
ONLINE_ROLE_NAME = "🎮 Online"
WEBHOOK_CHANNEL_ID = 1291111515977551892
MOD_ROLE_ID = 1222930361848303736

# Role IDs for achievements and deaths
MOST_DEATHS_ROLE = "💀 Skill Issue"
LEAST_DEATHS_ROLE = "🎮 Pro gamer"
MOST_ADVANCEMENTS_ROLE = "👑 Overachiever"
LEAST_ADVANCEMENTS_ROLE = "🌱 Beginner"

# Minecraft to Discord username mapping
MINECRAFT_TO_DISCORD = {
    "LuigiTime34": "luigi_is_better",
    "_gingercat_": "sblujay",
    "KerDreigerTiger": ".kaiserleopold",
    "Block_Builder": "kazzpyr",
    "AmbiguouSaurus": "bobbilby",
    "wwffd": "wizardcat1000",
    "BurgersAreYumYum": "ih8tk",
    "Dinnerbone5117": "salmon5117_73205",
    "Frogloverender": "frogloverender",
    "Sweatshirtboi16": "sweatshirtboi16",
    "MindJames": "mindjames_93738",
    "therealgoos": "therealgoos",
    "BigSharkyBRo": "car248.",
    "Brandonslay": "ctslayer.",
    "ItzT1g3r": "greattigergaming",
    "the_rock_gaming": "the_rock_gaming",
    "THERYZEN7": "asillygooberguy",
    "spleeftrappedlol": "neoptolemus_"
}

# Special characters for detecting death and advancement messages
DEATH_MARKER = "⚰️"
ADVANCEMENT_MARKER = "⭐"

# Store user statistics
class Stats:
    def __init__(self):
        self.deaths = defaultdict(int)
        self.advancements = defaultdict(int)
        self.load_stats()

    def load_stats(self):
        if os.path.exists('stats.json'):
            with open('stats.json', 'r') as f:
                data = json.load(f)
                self.deaths = defaultdict(int, data.get('deaths', {}))
                self.advancements = defaultdict(int, data.get('advancements', {}))

    def save_stats(self):
        with open('stats.json', 'w') as f:
            json.dump({
                'deaths': dict(self.deaths),
                'advancements': dict(self.advancements)
            }, f)

stats = Stats()

async def update_ranking_roles(guild):
    """Update the roles for most/least deaths and advancements"""
    if not stats.deaths and not stats.advancements:
        return

    # Get or create roles
    most_deaths_role = discord.utils.get(guild.roles, name=MOST_DEATHS_ROLE)
    least_deaths_role = discord.utils.get(guild.roles, name=LEAST_DEATHS_ROLE)
    most_adv_role = discord.utils.get(guild.roles, name=MOST_ADVANCEMENTS_ROLE)
    least_adv_role = discord.utils.get(guild.roles, name=LEAST_ADVANCEMENTS_ROLE)

    # Find highest and lowest values
    if stats.deaths:
        max_deaths = max(stats.deaths.values())
        min_deaths = min(stats.deaths.values())
        most_deaths_users = [u for u, d in stats.deaths.items() if d == max_deaths]
        least_deaths_users = [u for u, d in stats.deaths.items() if d == min_deaths]

    if stats.advancements:
        max_adv = max(stats.advancements.values())
        min_adv = min(stats.advancements.values())
        most_adv_users = [u for u, a in stats.advancements.items() if a == max_adv]
        least_adv_users = [u for u, a in stats.advancements.items() if a == min_adv]

    # Update roles for all members
    for member in guild.members:
        username = member.name

        # Deaths roles
        if username in most_deaths_users and most_deaths_role:
            await member.add_roles(most_deaths_role)
        elif most_deaths_role in member.roles:
            await member.remove_roles(most_deaths_role)

        if username in least_deaths_users and least_deaths_role:
            await member.add_roles(least_deaths_role)
        elif least_deaths_role in member.roles:
            await member.remove_roles(least_deaths_role)

        # Advancement roles
        if username in most_adv_users and most_adv_role:
            await member.add_roles(most_adv_role)
        elif most_adv_role in member.roles:
            await member.remove_roles(most_adv_role)

        if username in least_adv_users and least_adv_role:
            await member.add_roles(least_adv_role)
        elif least_adv_role in member.roles:
            await member.remove_roles(least_adv_role)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')

@bot.event
async def on_message(message):
    if message.channel.id != WEBHOOK_CHANNEL_ID:
        await bot.process_commands(message)
        return

    content = message.content
    
    # Handle join/leave messages
    if " joined the server" in content:
        minecraft_name = content.split(" joined the server")[0]
        if minecraft_name in MINECRAFT_TO_DISCORD:
            discord_name = MINECRAFT_TO_DISCORD[minecraft_name]
            member = discord.utils.get(message.guild.members, name=discord_name)
            if member:
                role = discord.utils.get(message.guild.roles, name=ONLINE_ROLE_NAME)
                if role:
                    await member.add_roles(role)
                await message.add_reaction('✅')
            else:
                await message.add_reaction('❓')
        else:
            await message.add_reaction('❓')

    elif " left the server" in content:
        minecraft_name = content.split(" left the server")[0]
        if minecraft_name in MINECRAFT_TO_DISCORD:
            discord_name = MINECRAFT_TO_DISCORD[minecraft_name]
            member = discord.utils.get(message.guild.members, name=discord_name)
            if member:
                role = discord.utils.get(message.guild.roles, name=ONLINE_ROLE_NAME)
                if role and role in member.roles:
                    await member.remove_roles(role)
                await message.add_reaction('👋')
            else:
                await message.add_reaction('❓')
        else:
            await message.add_reaction('❓')

    # Handle death messages
    elif content.startswith(DEATH_MARKER):
        for minecraft_name in MINECRAFT_TO_DISCORD:
            if minecraft_name in content:
                discord_name = MINECRAFT_TO_DISCORD[minecraft_name]
                stats.deaths[discord_name] += 1
                stats.save_stats()
                await update_ranking_roles(message.guild)
                break

    # Handle advancement messages
    elif content.startswith(ADVANCEMENT_MARKER):
        for minecraft_name in MINECRAFT_TO_DISCORD:
            if minecraft_name in content:
                discord_name = MINECRAFT_TO_DISCORD[minecraft_name]
                stats.advancements[discord_name] += 1
                stats.save_stats()
                await update_ranking_roles(message.guild)
                break

    await bot.process_commands(message)

@bot.command(name='deaths')
async def deaths(ctx, user: discord.Member = None):
    user = user or ctx.author
    count = stats.deaths.get(user.name, 0)
    await ctx.send(f"{user.name} has died {count} times")

@bot.command(name='advancements')
async def advancements(ctx, user: discord.Member = None):
    user = user or ctx.author
    count = stats.advancements.get(user.name, 0)
    await ctx.send(f"{user.name} has completed {count} advancements")

def is_mod(ctx):
    return discord.utils.get(ctx.author.roles, id=MOD_ROLE_ID) is not None

@bot.command(name='addhistory')
@commands.check(is_mod)
async def add_history(ctx, user: discord.Member, stat_type: str, count: int):
    if stat_type.lower() == 'deaths':
        stats.deaths[user.name] = count
    elif stat_type.lower() == 'advancements':
        stats.advancements[user.name] = count
    else:
        await ctx.send("Invalid stat type. Use 'deaths' or 'advancements'")
        return
    
    stats.save_stats()
    await update_ranking_roles(ctx.guild)
    await ctx.send(f"Updated {stat_type} count for {user.name} to {count}")

@bot.command(name='deathlist')
@commands.check(is_mod)
async def death_list(ctx):
    if not stats.deaths:
        await ctx.send("No death statistics recorded yet.")
        return
    
    sorted_deaths = sorted(stats.deaths.items(), key=lambda x: x[1], reverse=True)
    message = "**Death Rankings:**\n" + "\n".join(f"{name}: {count}" for name, count in sorted_deaths)
    await ctx.send(message)

@bot.command(name='advancementlist')
@commands.check(is_mod)
async def advancement_list(ctx):
    if not stats.advancements:
        await ctx.send("No advancement statistics recorded yet.")
        return
    
    sorted_adv = sorted(stats.advancements.items(), key=lambda x: x[1], reverse=True)
    message = "**Advancement Rankings:**\n" + "\n".join(f"{name}: {count}" for name, count in sorted_adv)
    await ctx.send(message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing required argument. Please check the command usage.")
    else:
        print(f'Error: {error}')

# Run the bot
bot.run('TOKEN')
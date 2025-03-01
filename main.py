import discord
from discord.ext import commands
import re
import subprocess

# Import from our modules
from const import (
    DATABASE_PATH, ROLES, ONLINE_ROLE_NAME, WEBHOOK_CHANNEL_ID, MOD_ROLE_ID,
    SCOREBOARD_CHANNEL_ID, MINECRAFT_TO_DISCORD, DEATH_MARKER, ADVANCEMENT_MARKER
)
from database.queries import (
    initialize_database, record_death, record_advancement, record_login,
    record_logout, get_player_stats, clear_online_players
)
from utils.discord_helpers import get_discord_user, get_player_display_names, get_minecraft_from_discord
from commands.player_stats import (
    deaths_command, advancements_command, playtime_command,
    deathlist_command, advancementlist_command, playtimelist_command
)
from commands.admin import updateroles_command, addhistory_command
from tasks.leaderboard import leaderboard_update_task
from tasks.roles import (
    add_online_role, remove_online_role, clear_all_online_roles, role_update_task
)

# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True  # For reading message content
intents.members = True  # For accessing member info
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables
server_online = False
online_players = []

# Dead bots for henry and bear
def run_idle_bots():
    subprocess.Popen(["python", "run_bear.py"])
    subprocess.Popen(["python", "run_henry.py"])

# Bot event handlers
@bot.event
async def on_ready():
    """When bot is ready, initialize everything."""
    print(f'Bot is ready! Logged in as {bot.user}')
    run_idle_bots()
    
    # Initialize database
    initialize_database()
    
    # Set initial status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is currently offline."))
    
    # Start background tasks
    bot.loop.create_task(leaderboard_update_task(bot))
    bot.loop.create_task(role_update_task(bot))
    
    print("Bot initialization complete!")

@bot.event
async def on_message(message):
    """Handle incoming messages."""
    global server_online, online_players
    
    # Ignore own messages
    if message.author == bot.user:
        return
    
    # Debug logging for webhook messages
    if message.channel.id == WEBHOOK_CHANNEL_ID:
        print(f"Webhook message received: {message.content}")
    
    # Check if it's in the webhook channel
    if message.channel.id == WEBHOOK_CHANNEL_ID:
        # Server status messages
        if ":white_check_mark: **Server has started**" in message.content:
            server_online = True
            await message.add_reaction('✅')
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is online! (0 players)"))
            print("Server has started!")
            
        elif ":octagonal_sign: **Server has stopped**" in message.content:
            server_online = False
            await message.add_reaction('🛑')
            
            # Update playtime for all online players
            clear_online_players()
            online_players = []
            
            # Clear online roles
            for guild in bot.guilds:
                await clear_all_online_roles(guild)
            
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is currently offline."))
            print("Server has stopped!")
            
        # Player join - check for both bold and plain text formats
        elif " joined the server" in message.content:
            print(f"Join message detected: {message.content}")

            match = re.search(r"\*\*(.*?)\*\* joined the server", message.content)
            if not match:
                match = re.search(r"(.*?) joined the server", message.content)

            if match:
                # Properly clean the extracted username
                minecraft_username = re.sub(r"\\(.)", r"\1", match.group(1))
                await message.add_reaction('✅')

                print(f"Extracted username: {minecraft_username}")

                
                if minecraft_username in MINECRAFT_TO_DISCORD:
                    discord_username = MINECRAFT_TO_DISCORD[minecraft_username]
                    
                    # Record login
                    record_login(minecraft_username)
                    online_players.append(minecraft_username)
                    
                    # Add online role
                    for guild in bot.guilds:
                        member = get_discord_user(bot, discord_username)
                        if member:
                            await add_online_role(member)
                    
                    # Update bot status
                    discord_display_names = get_player_display_names(online_players, message.guild)
                    status_text = f" {len(discord_display_names)} player(s) online: {', '.join(discord_display_names)}"
                    if len(status_text) > 100:  # If too long, simplify
                        status_text = f"Online: {len(discord_display_names)} players"

                    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
                    print(f"{minecraft_username} joined the server")
                else:
                    await message.add_reaction('❓')
                    print(f"Unknown player joined: {minecraft_username}")
            else:
                print("Could not extract username from join message")
        
        # Player leave - check for both bold and plain text formats
        elif " left the server" in message.content:
            print(f"Leave message detected: {message.content}")
            
            # Try bold format first (from markdown)
            match = re.search(r"\*\*(.*?)\*\* left the server", message.content)
            if not match:
                # Try plain text format
                match = re.search(r"(.*?) left the server", message.content)
            
            if match:
                minecraft_username = match.group(1).replace("\\", "")  # Remove escape chars
                await message.add_reaction('👋')
                
                print(f"Extracted username: {minecraft_username}")
                
                if minecraft_username in MINECRAFT_TO_DISCORD:
                    discord_username = MINECRAFT_TO_DISCORD[minecraft_username]
                    
                    # Record logout
                    record_logout(minecraft_username)
                    if minecraft_username in online_players:
                        online_players.remove(minecraft_username)
                    
                    # Remove online role
                    for guild in bot.guilds:
                        member = get_discord_user(bot, discord_username)
                        if member:
                            await remove_online_role(member)
                    
                    # Update bot status
                    discord_display_names = get_player_display_names(online_players, message.guild)
                    if discord_display_names:
                        status_text = f" {len(discord_display_names)} player(s) online: {', '.join(discord_display_names)}"
                        if len(status_text) > 100:
                            status_text = f"Online: {len(discord_display_names)} players"
                        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
                        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
                    else:
                        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is online. Join now!"))
                    
                    print(f"{minecraft_username} left the server")
                else:
                    await message.add_reaction('❓')
                    print(f"Unknown player left: {minecraft_username}")
            else:
                print("Could not extract username from leave message")
        
        # Death messages - also check for both formats
        elif message.content.startswith(DEATH_MARKER) or DEATH_MARKER in message.content:
            match = re.search(f"{DEATH_MARKER} \*\*(.*?)\*\*", message.content)
            if not match:
                match = re.search(f"{DEATH_MARKER} (.*?)[^\w]", message.content)
            
            if match:
                minecraft_username = match.group(1).replace("\\", "")
                await message.add_reaction(DEATH_MARKER)
                
                if minecraft_username in MINECRAFT_TO_DISCORD:
                    record_death(minecraft_username)
                    print(f"{minecraft_username} died")
                else:
                    await message.add_reaction('❓')
                    print(f"Unknown player died: {minecraft_username}")
        
        # Advancement messages - also check for both formats
        elif message.content.startswith(ADVANCEMENT_MARKER) or ADVANCEMENT_MARKER in message.content:
            match = re.search(f"{ADVANCEMENT_MARKER} \*\*(.*?)\*\*", message.content)
            if not match:
                match = re.search(f"{ADVANCEMENT_MARKER} (.*?)[^\w]", message.content)
            
            if match:
                minecraft_username = match.group(1).replace("\\", "")
                await message.add_reaction(ADVANCEMENT_MARKER)
                
                if minecraft_username in MINECRAFT_TO_DISCORD:
                    record_advancement(minecraft_username)
                    print(f"{minecraft_username} got an advancement")
                else:
                    await message.add_reaction('❓')
                    print(f"Unknown player got advancement: {minecraft_username}")
    
    # Handle playerlist command when server is offline
    if not server_online and message.content.strip() == "playerlist":
        await message.add_reaction('❌')
        await message.channel.send("You can't use this command right now, the server is down.")
    
    # Process commands
    await bot.process_commands(message)

# Set up commands
@bot.command(name="deaths")
async def deaths_cmd(ctx, username=None):
    await deaths_command(ctx, bot, username)

@bot.command(name="advancements")
async def advancements_cmd(ctx, username=None):
    await advancements_command(ctx, bot, username)

@bot.command(name="playtime")
async def playtime_cmd(ctx, username=None):
    await playtime_command(ctx, bot, username)

@bot.command(name="deathlist")
async def deathlist_cmd(ctx):
    await deathlist_command(ctx, bot)

@bot.command(name="advancementlist")
async def advancementlist_cmd(ctx):
    await advancementlist_command(ctx, bot)

@bot.command(name="playtimelist")
async def playtimelist_cmd(ctx):
    await playtimelist_command(ctx, bot)

@bot.command(name="updateroles")
async def updateroles_cmd(ctx):
    await updateroles_command(ctx, bot)

@bot.command(name="addhistory")
async def addhistory_cmd(ctx):
    await addhistory_command(ctx, bot)

# Run the bot
if __name__ == "__main__":
    with open('token.txt', 'r') as f:
        TOKEN = f.readline().strip()
    bot.run(TOKEN)
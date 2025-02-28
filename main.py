import discord
from discord.ext import commands
import sqlite3
import os
import re
import asyncio
import datetime
from const import (
    DATABASE_PATH, ROLES, ONLINE_ROLE_NAME, WEBHOOK_CHANNEL_ID, MOD_ROLE_ID,
    SCOREBOARD_CHANNEL_ID, MOST_DEATHS_ROLE, LEAST_DEATHS_ROLE,
    MOST_ADVANCEMENTS_ROLE, LEAST_ADVANCEMENTS_ROLE, MOST_PLAYTIME_ROLE,
    LEAST_PLAYTIME_ROLE, MINECRAFT_TO_DISCORD, DEATH_MARKER, ADVANCEMENT_MARKER
)

# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True  # For reading message content
intents.members = True  # For accessing member info
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables
server_online = False
online_players = []
leaderboard_messages = {'deaths': None, 'advancements': None, 'playtime': None}

# Database functions
def initialize_database():
    """Create database tables if they don't exist."""
    print(f"Initializing database at {DATABASE_PATH}")
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Main stats table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS player_stats (
        minecraft_username TEXT PRIMARY KEY,
        discord_username TEXT,
        deaths INTEGER DEFAULT 0,
        advancements INTEGER DEFAULT 0,
        playtime_seconds INTEGER DEFAULT 0
    )
    ''')
    
    # Tracking table for online players
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS online_players (
        minecraft_username TEXT PRIMARY KEY,
        login_time INTEGER
    )
    ''')
    
    # Initialize all players from the mapping with default values
    for mc_username, disc_username in MINECRAFT_TO_DISCORD.items():
        cursor.execute('''
        INSERT OR IGNORE INTO player_stats 
        (minecraft_username, discord_username, deaths, advancements, playtime_seconds) 
        VALUES (?, ?, 0, 0, 0)
        ''', (mc_username, disc_username))
    
    conn.commit()
    conn.close()
    print("Database initialized!")

def record_death(minecraft_username):
    """Increment death count for a player."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE player_stats SET deaths = deaths + 1 WHERE minecraft_username = ?", 
            (minecraft_username,)
        )
        conn.commit()
        conn.close()
        print(f"Recorded death for {minecraft_username}")
    except Exception as e:
        print(f"Error recording death: {e}")

def record_advancement(minecraft_username):
    """Increment advancement count for a player."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE player_stats SET advancements = advancements + 1 WHERE minecraft_username = ?", 
            (minecraft_username,)
        )
        conn.commit()
        conn.close()
        print(f"Recorded advancement for {minecraft_username}")
    except Exception as e:
        print(f"Error recording advancement: {e}")

def record_login(minecraft_username):
    """Record when a player logs in."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        current_time = int(datetime.datetime.now().timestamp())
        cursor.execute(
            "INSERT OR REPLACE INTO online_players (minecraft_username, login_time) VALUES (?, ?)",
            (minecraft_username, current_time)
        )
        conn.commit()
        conn.close()
        print(f"Recorded login for {minecraft_username} at {current_time}")
    except Exception as e:
        print(f"Error recording login: {e}")

def record_logout(minecraft_username):
    """Record when a player logs out and update playtime."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Get login time
        cursor.execute(
            "SELECT login_time FROM online_players WHERE minecraft_username = ?",
            (minecraft_username,)
        )
        result = cursor.fetchone()
        
        if result:
            login_time = result[0]
            current_time = int(datetime.datetime.now().timestamp())
            playtime = current_time - login_time
            
            # Update total playtime
            cursor.execute(
                "UPDATE player_stats SET playtime_seconds = playtime_seconds + ? WHERE minecraft_username = ?",
                (playtime, minecraft_username)
            )
            
            # Remove from online players
            cursor.execute(
                "DELETE FROM online_players WHERE minecraft_username = ?",
                (minecraft_username,)
            )
            
            conn.commit()
            print(f"Recorded logout for {minecraft_username}, added {playtime} seconds")
        else:
            print(f"No login record found for {minecraft_username}")
        
        conn.close()
        return playtime if result else 0
    except Exception as e:
        print(f"Error recording logout: {e}")
        return 0

def get_player_stats(minecraft_username=None, discord_username=None):
    """Get stats for a player by minecraft or discord username."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        if minecraft_username:
            cursor.execute(
                "SELECT * FROM player_stats WHERE minecraft_username = ?",
                (minecraft_username,)
            )
        elif discord_username:
            cursor.execute(
                "SELECT * FROM player_stats WHERE discord_username = ?",
                (discord_username,)
            )
        else:
            return None
        
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        print(f"Error getting player stats: {e}")
        return None

def get_all_players():
    """Get stats for all players."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM player_stats")
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Error getting all players: {e}")
        return []

def get_all_deaths():
    """Get all player death counts sorted from lowest to highest."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT minecraft_username, discord_username, deaths FROM player_stats ORDER BY deaths ASC"
        )
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Error getting death counts: {e}")
        return []

def get_all_advancements():
    """Get all player advancement counts sorted from highest to lowest."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT minecraft_username, discord_username, advancements FROM player_stats ORDER BY advancements DESC"
        )
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Error getting advancement counts: {e}")
        return []

def get_all_playtimes():
    """Get all player playtimes sorted from highest to lowest."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT minecraft_username, discord_username, playtime_seconds FROM player_stats ORDER BY playtime_seconds DESC"
        )
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        print(f"Error getting playtimes: {e}")
        return []

def get_online_players_db():
    """Get list of currently online players from the database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT minecraft_username FROM online_players")
        result = cursor.fetchall()
        conn.close()
        return [player[0] for player in result]
    except Exception as e:
        print(f"Error getting online players: {e}")
        return []

def clear_online_players():
    """Clear all online players and update playtimes."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Get all online players
        cursor.execute("SELECT minecraft_username, login_time FROM online_players")
        players = cursor.fetchall()
        
        current_time = int(datetime.datetime.now().timestamp())
        
        # Update playtime for each player
        for player in players:
            minecraft_username, login_time = player
            playtime = current_time - login_time
            
            cursor.execute(
                "UPDATE player_stats SET playtime_seconds = playtime_seconds + ? WHERE minecraft_username = ?",
                (playtime, minecraft_username)
            )
            
            print(f"Added {playtime} seconds to {minecraft_username}")
        
        # Clear the online players table
        cursor.execute("DELETE FROM online_players")
        
        conn.commit()
        conn.close()
        print(f"Cleared {len(players)} online players")
    except Exception as e:
        print(f"Error clearing online players: {e}")

def bulk_update_history(updates):
    """Update player stats in bulk from provided dictionary."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        for minecraft_username, stats in updates.items():
            if 'deaths' in stats:
                cursor.execute(
                    "UPDATE player_stats SET deaths = ? WHERE minecraft_username = ?",
                    (stats['deaths'], minecraft_username)
                )
            
            if 'advancements' in stats:
                cursor.execute(
                    "UPDATE player_stats SET advancements = ? WHERE minecraft_username = ?",
                    (stats['advancements'], minecraft_username)
                )
            
            if 'playtime' in stats:
                cursor.execute(
                    "UPDATE player_stats SET playtime_seconds = ? WHERE minecraft_username = ?",
                    (stats['playtime'], minecraft_username)
                )
        
        conn.commit()
        conn.close()
        print(f"Bulk updated history for {len(updates)} players")
        return True
    except Exception as e:
        print(f"Error updating history: {e}")
        return False

# Helper functions
def format_playtime(seconds):
    """Format seconds into a readable time string."""
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    result = ""
    if hours > 0:
        result += f"{hours}h "
    result += f"{minutes}m"
    
    return result.strip()

def get_minecraft_from_discord(discord_name):
    """Get Minecraft username from Discord username."""
    for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
        if disc_name.lower() == discord_name.lower():
            return mc_name
    return None

def get_discord_user(bot, discord_name):
    """Get Discord user object from username."""
    for guild in bot.guilds:
        for member in guild.members:
            if member.name.lower() == discord_name.lower() or str(member).lower() == discord_name.lower():
                return member
    return None

def get_player_display_names(minecraft_usernames, guild):
    """Get display names for a list of Minecraft usernames"""
    display_names = []
    
    for mc_name in minecraft_usernames:
        if mc_name in MINECRAFT_TO_DISCORD:
            discord_name = MINECRAFT_TO_DISCORD[mc_name]
            for member in guild.members:
                if member.name.lower() == discord_name.lower() or str(member).lower() == discord_name.lower():
                    # Use display name (nickname) if available, otherwise fall back to username
                    display_names.append(member.display_name)
                    break
    
    return display_names


# Role management functions
async def add_online_role(member):
    """Add the online role to a Discord member."""
    if member:
        role = discord.utils.get(member.guild.roles, name=ONLINE_ROLE_NAME)
        if role and role not in member.roles:
            await member.add_roles(role)
            print(f"Added {ONLINE_ROLE_NAME} role to {member.name}")

async def remove_online_role(member):
    """Remove the online role from a Discord member."""
    if member:
        role = discord.utils.get(member.guild.roles, name=ONLINE_ROLE_NAME)
        if role and role in member.roles:
            await member.remove_roles(role)
            print(f"Removed {ONLINE_ROLE_NAME} role from {member.name}")

async def clear_all_online_roles(guild):
    """Remove online role from all members in the guild."""
    role = discord.utils.get(guild.roles, name=ONLINE_ROLE_NAME)
    if role:
        members_with_role = [member for member in guild.members if role in member.roles]
        for member in members_with_role:
            await member.remove_roles(role)
        print(f"Cleared {ONLINE_ROLE_NAME} role from {len(members_with_role)} members")

async def update_achievement_roles(guild):
    """Update all achievement roles based on current stats."""
    print("Updating achievement roles...")
    
    # Get data
    deaths_data = get_all_deaths()
    advancements_data = get_all_advancements()
    playtimes_data = get_all_playtimes()
    
    # Define roles
    most_deaths_role = discord.utils.get(guild.roles, name=MOST_DEATHS_ROLE)
    least_deaths_role = discord.utils.get(guild.roles, name=LEAST_DEATHS_ROLE)
    most_adv_role = discord.utils.get(guild.roles, name=MOST_ADVANCEMENTS_ROLE)
    least_adv_role = discord.utils.get(guild.roles, name=LEAST_ADVANCEMENTS_ROLE)
    most_playtime_role = discord.utils.get(guild.roles, name=MOST_PLAYTIME_ROLE)
    least_playtime_role = discord.utils.get(guild.roles, name=LEAST_PLAYTIME_ROLE)
    
    # Track current and new role holders
    current_role_holders = {
        most_deaths_role: set(member for member in guild.members if most_deaths_role in member.roles),
        least_deaths_role: set(member for member in guild.members if least_deaths_role in member.roles),
        most_adv_role: set(member for member in guild.members if most_adv_role in member.roles),
        least_adv_role: set(member for member in guild.members if least_adv_role in member.roles),
        most_playtime_role: set(member for member in guild.members if most_playtime_role in member.roles),
        least_playtime_role: set(member for member in guild.members if least_playtime_role in member.roles)
    }
    
    new_role_holders = {
        most_deaths_role: set(),
        least_deaths_role: set(),
        most_adv_role: set(),
        least_adv_role: set(),
        most_playtime_role: set(),
        least_playtime_role: set()
    }
    
    # Handle most deaths
    if deaths_data and most_deaths_role:
        most_deaths = max(deaths_data, key=lambda x: x[2])
        most_deaths_players = [p for p in deaths_data if p[2] == most_deaths[2]]
        for player in most_deaths_players:
            discord_member = get_discord_user(bot, player[1])
            if discord_member:
                new_role_holders[most_deaths_role].add(discord_member)
    
    # Handle least deaths (need at least 5 hours playtime)
    if deaths_data and least_deaths_role:
        eligible_players = []
        for player in deaths_data:
            mc_name, _, deaths = player
            stats = get_player_stats(minecraft_username=mc_name)
            if stats and stats[4] >= 18000:  # 5 hours in seconds
                eligible_players.append(player)
        
        if eligible_players:
            min_deaths = min([p[2] for p in eligible_players if p[2] > 0], default=float('inf'))
            least_deaths_players = [p for p in eligible_players if p[2] == min_deaths]
            for player in least_deaths_players:
                discord_member = get_discord_user(bot, player[1])
                if discord_member:
                    new_role_holders[least_deaths_role].add(discord_member)
    
    # Handle most advancements
    if advancements_data and most_adv_role:
        max_adv = max(advancements_data, key=lambda x: x[2])[2]
        most_adv_players = [p for p in advancements_data if p[2] == max_adv]
        for player in most_adv_players:
            discord_member = get_discord_user(bot, player[1])
            if discord_member:
                new_role_holders[most_adv_role].add(discord_member)
    
    # Handle least advancements (need at least 5 minutes playtime)
    if advancements_data and least_adv_role:
        eligible_players = []
        for player in advancements_data:
            mc_name, _, advancements = player
            stats = get_player_stats(minecraft_username=mc_name)
            if stats and stats[4] >= 300:  # 5 minutes in seconds
                eligible_players.append(player)
        
        if eligible_players:
            min_adv = min([p[2] for p in eligible_players], default=float('inf'))
            least_adv_players = [p for p in eligible_players if p[2] == min_adv]
            for player in least_adv_players:
                discord_member = get_discord_user(bot, player[1])
                if discord_member:
                    new_role_holders[least_adv_role].add(discord_member)
    
    # Handle most playtime
    if playtimes_data and most_playtime_role:
        max_playtime = max(playtimes_data, key=lambda x: x[2])[2]
        most_playtime_players = [p for p in playtimes_data if p[2] == max_playtime]
        for player in most_playtime_players:
            discord_member = get_discord_user(bot, player[1])
            if discord_member:
                new_role_holders[most_playtime_role].add(discord_member)
    
    # Handle least playtime (need at least 5 minutes)
    if playtimes_data and least_playtime_role:
        eligible_players = [p for p in playtimes_data if p[2] >= 300]  # 5 minutes
        if eligible_players:
            min_playtime = min(eligible_players, key=lambda x: x[2])[2]
            least_playtime_players = [p for p in eligible_players if p[2] == min_playtime]
            for player in least_playtime_players:
                discord_member = get_discord_user(bot, player[1])
                if discord_member:
                    new_role_holders[least_playtime_role].add(discord_member)
    
    # Apply role changes (only where needed)
    for role, new_members in new_role_holders.items():
        if role:
            # Remove role from members who should no longer have it
            members_to_remove = current_role_holders[role] - new_members
            for member in members_to_remove:
                await member.remove_roles(role)
                print(f"Removed {role.name} from {member.name}")
            
            # Add role to members who should now have it
            members_to_add = new_members - current_role_holders[role]
            for member in members_to_add:
                await member.add_roles(role)
                print(f"Added {role.name} to {member.name}")

# Leaderboard functions
async def update_leaderboards(channel):
    """Update the leaderboard messages in the designated channel."""
    global leaderboard_messages
    
    # Create embeds
    
    # Playtime leaderboard
    playtime_data = get_all_playtimes()
    playtime_embed = discord.Embed(
        title="🕒 Playtime Leaderboard",
        description="Who's spending their life on the server?",
        color=discord.Color.green()
    )
    
    if playtime_data:
        value = ""
        for i, (mc_name, _, seconds) in enumerate(playtime_data):  # Top 10
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {format_playtime(seconds)}\n"
        playtime_embed.add_field(name="Most Playtime", value=value, inline=False)
        playtime_embed.set_footer(text="Updated: " + datetime.datetime.now().strftime("%H:%M:%S"))
    
    # Advancements leaderboard
    adv_data = get_all_advancements()
    adv_embed = discord.Embed(
        title="⭐ Advancements Leaderboard",
        description="Who's been busy progressing?",
        color=discord.Color.gold()
    )
    
    if adv_data:
        value = ""
        for i, (mc_name, _, advancements) in enumerate(adv_data):  # Top 10
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {advancements} advancements\n"
        adv_embed.add_field(name="Most Advancements", value=value, inline=False)
        adv_embed.set_footer(text="Updated: " + datetime.datetime.now().strftime("%H:%M:%S"))
    
    # Deaths leaderboard
    deaths_data = get_all_deaths()
    deaths_embed = discord.Embed(
        title="💀 Deaths Leaderboard",
        description="Who's been playing it safe?",
        color=discord.Color.red()
    )
    
    if deaths_data:
        value = ""
        for i, (mc_name, _, deaths) in enumerate(deaths_data):  # Top 10
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {deaths} deaths\n"
        deaths_embed.add_field(name="Least Deaths", value=value, inline=False)
        deaths_embed.set_footer(text="Updated: " + datetime.datetime.now().strftime("%H:%M:%S"))
    
    # Initialize or update leaderboard messages
    try:
        # First time setup - if no messages exist, create them
        if not all(leaderboard_messages.values()):
            # Check if there are existing messages we can use
            existing_messages = []
            async for message in channel.history(limit=10):
                if message.author == bot.user:
                    existing_messages.append(message)
            
            # Use existing messages if available (newest first)
            if len(existing_messages) >= 3:
                leaderboard_messages['deaths'] = existing_messages[0]
                leaderboard_messages['advancements'] = existing_messages[1]
                leaderboard_messages['playtime'] = existing_messages[2]
            else:
                # Create new messages if needed
                if not leaderboard_messages['playtime']:
                    leaderboard_messages['playtime'] = await channel.send(embed=playtime_embed)
                if not leaderboard_messages['advancements']:
                    leaderboard_messages['advancements'] = await channel.send(embed=adv_embed)
                if not leaderboard_messages['deaths']:
                    leaderboard_messages['deaths'] = await channel.send(embed=deaths_embed)
        
        # Update existing messages
        if leaderboard_messages['playtime']:
            await leaderboard_messages['playtime'].edit(embed=playtime_embed)
        if leaderboard_messages['advancements']:
            await leaderboard_messages['advancements'].edit(embed=adv_embed)
        if leaderboard_messages['deaths']:
            await leaderboard_messages['deaths'].edit(embed=deaths_embed)
        
        print("Updated leaderboards successfully")
    except Exception as e:
        print(f"Error updating leaderboards: {e}")
        # If editing failed, try to send new messages
        try:
            if leaderboard_messages['playtime']:
                leaderboard_messages['playtime'] = await channel.send(embed=playtime_embed)
            if leaderboard_messages['advancements']:
                leaderboard_messages['advancements'] = await channel.send(embed=adv_embed)
            if leaderboard_messages['deaths']:
                leaderboard_messages['deaths'] = await channel.send(embed=deaths_embed)
        except Exception as e2:
            print(f"Failed to recover from leaderboard update error: {e2}")

# Bot event handlers
@bot.event
async def on_ready():
    """When bot is ready, initialize everything."""
    print(f'Bot is ready! Logged in as {bot.user}')
    
    # Initialize database
    initialize_database()
    
    # Set initial status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is currently offline."))
    
    # Start background tasks
    bot.loop.create_task(leaderboard_update_task())
    bot.loop.create_task(role_update_task())
    
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
            # await message.add_reaction('✅')
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is online! (0 players)"))
            print("Server has started!")
            
        elif ":octagonal_sign: **Server has stopped**" in message.content:
            server_online = False
            # await message.add_reaction('✅')
            
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


# Background tasks
async def leaderboard_update_task():
    """Update leaderboards every minute."""
    await bot.wait_until_ready()
    channel = bot.get_channel(SCOREBOARD_CHANNEL_ID)
    
    if not channel:
        print(f"Could not find channel with ID {SCOREBOARD_CHANNEL_ID}")
        return
    
    while not bot.is_closed():
        try:
            await update_leaderboards(channel)
        except Exception as e:
            print(f"Error in leaderboard update task: {e}")
        
        await asyncio.sleep(60)  # Update every minute

async def role_update_task():
    """Update achievement roles every minute."""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                await update_achievement_roles(guild)
        except Exception as e:
            print(f"Error in role update task: {e}")
        
        await asyncio.sleep(60)  # Update every minute

# Commands
@bot.command(name="deaths")
async def deaths_command(ctx, username=None):
    """Show death count for a player."""
    
    # Determine which player to show
    minecraft_username = None
    
    if username:
        # Check if direct Minecraft username
        if username in MINECRAFT_TO_DISCORD:
            minecraft_username = username
        else:
            # Try to find by Discord name
            for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                if disc_name.lower() == username.lower():
                    minecraft_username = mc_name
                    break
    else:
        # Use command author
        author_name = ctx.author.name
        minecraft_username = get_minecraft_from_discord(author_name)
    
    if not minecraft_username:
        await ctx.send("Could not find a matching player. Please specify a valid username.")
        return
    
    # Get stats
    stats = get_player_stats(minecraft_username=minecraft_username)
    
    if stats:
        embed = discord.Embed(
            title=f"Death Count for {minecraft_username}",
            description=f"💀 **{minecraft_username}** has died **{stats[2]}** times.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}")

@bot.command(name="advancements")
async def advancements_command(ctx, username=None):
    """Show advancement count for a player."""
    
    # Determine which player to show
    minecraft_username = None
    
    if username:
        # Check if direct Minecraft username
        if username in MINECRAFT_TO_DISCORD:
            minecraft_username = username
        else:
            # Try to find by Discord name
            for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                if disc_name.lower() == username.lower():
                    minecraft_username = mc_name
                    break
    else:
        # Use command author
        author_name = ctx.author.name
        minecraft_username = get_minecraft_from_discord(author_name)
    
    if not minecraft_username:
        await ctx.send("Could not find a matching player. Please specify a valid username.")
        return
    
    # Get stats
    stats = get_player_stats(minecraft_username=minecraft_username)
    
    if stats:
        embed = discord.Embed(
            title=f"Advancement Count for {minecraft_username}",
            description=f"⭐ **{minecraft_username}** has earned **{stats[3]}** advancements.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}")

@bot.command(name="playtime")
async def playtime_command(ctx, username=None):
    """Show playtime for a player."""
    # await ctx.message.add_reaction('✅')
    
    # Determine which player to show
    minecraft_username = None
    
    if username:
        # Check if direct Minecraft username
        if username in MINECRAFT_TO_DISCORD:
            minecraft_username = username
        else:
            # Try to find by Discord name
            for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                if disc_name.lower() == username.lower():
                    minecraft_username = mc_name
                    break
    else:
        # Use command author
        author_name = ctx.author.name
        minecraft_username = get_minecraft_from_discord(author_name)
    
    if not minecraft_username:
        await ctx.send("Could not find a matching player. Please specify a valid username.")
        return
    
    # Get stats
    stats = get_player_stats(minecraft_username=minecraft_username)
    
    if stats:
        formatted_time = format_playtime(stats[4])
        embed = discord.Embed(
            title=f"Playtime for {minecraft_username}",
            description=f"🕒 **{minecraft_username}** has played for **{formatted_time}**!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}")

@bot.command(name="deathlist")
async def deathlist_command(ctx):
    """Show death counts for all players."""
    # await ctx.message.add_reaction('✅')
    
    deaths_data = get_all_deaths()
    
    if deaths_data:
        embed = discord.Embed(
            title="Death Counts",
            description="All player death counts (lowest to highest)",
            color=discord.Color.red()
        )
        
        value = "```\n"
        for mc_name, _, deaths in deaths_data:
            value += f"{mc_name}: {deaths}\n"
        value += "```"
        
        embed.add_field(name="Deaths", value=value, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No death data available.")

@bot.command(name="advancementlist")
async def advancementlist_command(ctx):
    """Show advancement counts for all players."""
    # await ctx.message.add_reaction('✅')
    
    adv_data = get_all_advancements()
    
    if adv_data:
        embed = discord.Embed(
            title="Advancement Counts",
            description="All player advancement counts (highest to lowest)",
            color=discord.Color.gold()
        )
        
        value = "```\n"
        for mc_name, _, advancements in adv_data:
            value += f"{mc_name}: {advancements}\n"
        value += "```"
        
        embed.add_field(name="Advancements", value=value, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No advancement data available.")

@bot.command(name="playtimelist")
async def playtimelist_command(ctx):
    """Show playtimes for all players."""
    # await ctx.message.add_reaction('✅')
    
    playtime_data = get_all_playtimes()
    
    if playtime_data:
        embed = discord.Embed(
            title="Playtime Counts",
            description="All player playtimes (highest to lowest)",
            color=discord.Color.green()
        )
        
        value = "```\n"
        for mc_name, _, seconds in playtime_data:
            value += f"{mc_name}: {format_playtime(seconds)}\n"
        value += "```"
        
        embed.add_field(name="Playtime", value=value, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No playtime data available.")

@bot.command(name="updateroles")
async def updateroles_command(ctx):
    """Update achievement roles manually."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await ctx.message.add_reaction('✅')
    
    await update_achievement_roles(ctx.guild)
    await ctx.send("Roles have been updated!")

@bot.command(name="addhistory")
async def addhistory_command(ctx):
    """Add or update player history."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await ctx.message.add_reaction('✅')
    
    # Get current stats
    players = get_all_players()
    
    embed = discord.Embed(
        title="Player History",
        description="Current values for all players. Reply with changes to update.",
        color=discord.Color.blue()
    )
    
    # Format instructions
    instructions = """
To update values, reply with a message in this format:
```
username1: deaths=5, advancements=10, playtime=3600
username2: deaths=2, advancements=15, playtime=7200
```
- You can update one or more values for one or more players
- 'username' should be the Minecraft username
- 'playtime' is in seconds
"""
    embed.add_field(name="Instructions", value=instructions, inline=False)
    
    # Format current values
    current_values = "```\n"
    for mc_username, disc_username, deaths, advancements, playtime in players:
        current_values += f"{mc_username}: deaths={deaths}, advancements={advancements}, playtime={playtime}\n"
    current_values += "```"
    
    # Split long content into multiple fields if needed
    def add_embed_fields(embed, name, content):
        chunks = [content[i:i + 1000] for i in range(0, len(content), 1000)]
        for index, chunk in enumerate(chunks):
            embed.add_field(name=f"{name} (Part {index + 1})" if len(chunks) > 1 else name, value=f"```{chunk}```", inline=False)

    # Format current values and split if too long
    current_values = "\n".join(f"{mc_username}: deaths={deaths}, advancements={advancements}, playtime={playtime}"
                            for mc_username, _, deaths, advancements, playtime in players)

    add_embed_fields(embed, "Current Values", current_values)

    
    await ctx.send(embed=embed)
    
    # Wait for response
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        response = await bot.wait_for('message', check=check, timeout=300)  # 5 minute timeout
        
        # Parse response
        updates = {}
        lines = response.content.strip().split('\n')
        
        for line in lines:
            if ':' not in line:
                continue
                
            username, data_str = line.split(':', 1)
            username = username.strip()
            
            if username not in MINECRAFT_TO_DISCORD:
                await ctx.send(f"Unknown username: {username}")
                continue
                
            updates[username] = {}
            
            data_parts = data_str.strip().split(',')
            for part in data_parts:
                part = part.strip()
                if '=' not in part:
                    continue
                
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                try:
                    value = int(value)
                    updates[username][key] = value
                except ValueError:
                    await ctx.send(f"Invalid value for {key}: {value}")
        
        # Apply updates
        success = bulk_update_history(updates)
        
        if success:
            await ctx.send(f"Successfully updated history for {len(updates)} players!")
        else:
            await ctx.send("Error updating history. Check logs for details.")
            
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for response.")

# Run the bot
if __name__ == "__main__":
    with open('token.txt', 'r') as f:
        TOKEN = f.readline().strip()
    bot.run(TOKEN)

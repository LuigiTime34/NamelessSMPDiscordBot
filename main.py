import discord
from discord.ext import commands
import sqlite3
import time
import asyncio

from helperFunctions.database import initializeDatabase, addMinecraftToDiscordToDatabase
from const import *

# Initialize bot with required intents
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

# Add a semaphore to control database access
db_semaphore = asyncio.Semaphore(1)

async def db_connect():
    """Connect to the database with async access control"""
    await db_semaphore.acquire()
    try:
        return sqlite3.connect(DATABASE_PATH)
    except Exception as e:
        db_semaphore.release()
        raise e

def db_close(conn):
    """Close the database connection and release the semaphore"""
    try:
        conn.close()
    finally:
        db_semaphore.release()

@bot.event
async def on_ready():
    startDatabasetime = time.time()
    initializeDatabase()
    print(f"Database initialized in {round(time.time() - startDatabasetime, 2)} seconds")
    
    addMinecraftToDiscordToDatabase(MINECRAFT_TO_DISCORD, bot, DATABASE_PATH)

    # Create roles if they don't exist
    for roleName in ROLES:
        if not discord.utils.get(bot.guilds[0].roles, name=roleName):
            print(f"Warning: Role '{roleName}' not found in server")
            await bot.guilds[0].create_role(name=roleName)
    
    print(f'{bot.user.name} has connected to Discord!')

async def updateRanksRoles(guild):
    """Update the roles for most/least deaths and advancements"""
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        
        # Only get users with deaths > 0
        cursor.execute("SELECT * FROM users WHERE deathCount > 0 ORDER BY deathCount DESC LIMIT 1")
        userWithMostDeaths = cursor.fetchone()
        
        cursor.execute("SELECT * FROM users WHERE deathCount > 0 ORDER BY deathCount ASC LIMIT 1")
        userWithLeastDeaths = cursor.fetchone()
        
        # Only get users with advancements > 0
        cursor.execute("SELECT * FROM users WHERE advancementCount > 0 ORDER BY advancementCount DESC LIMIT 1")
        userWithMostAdvancements = cursor.fetchone()
        
        cursor.execute("SELECT * FROM users WHERE advancementCount > 0 ORDER BY advancementCount ASC LIMIT 1")
        userWithLeastAdvancements = cursor.fetchone()

        # Only get users with playtime > 0
        cursor.execute("SELECT * FROM users WHERE playtimeSeconds > 0 ORDER BY playtimeSeconds DESC LIMIT 1")
        userWithMostPlaytime = cursor.fetchone()

        cursor.execute("SELECT * FROM users WHERE playtimeSeconds > 0 ORDER BY playtimeSeconds ASC LIMIT 1")
        userWithLowestPlaytime = cursor.fetchone()

        # Get roles
        mostDeathsRole = discord.utils.get(guild.roles, name=MOST_DEATHS_ROLE)
        leastDeathsRole = discord.utils.get(guild.roles, name=LEAST_DEATHS_ROLE)
        
        mostAdvancementsRole = discord.utils.get(guild.roles, name=MOST_ADVANCEMENTS_ROLE)
        leastAdvancementsRole = discord.utils.get(guild.roles, name=LEAST_ADVANCEMENTS_ROLE)
        
        mostPlaytimeRole = discord.utils.get(guild.roles, name=MOST_PLAYTIME_ROLE)
        leastPlaytimeRole = discord.utils.get(guild.roles, name=LEAST_PLAYTIME_ROLE)

        # Update roles for all members
        for member in guild.members:
            if member.bot:
                continue
                
            username = member.name

            # Deaths roles
            if userWithMostDeaths and username == userWithMostDeaths[0] and mostDeathsRole:
                await member.add_roles(mostDeathsRole)
            elif mostDeathsRole in member.roles:
                await member.remove_roles(mostDeathsRole)

            if userWithLeastDeaths and username == userWithLeastDeaths[0] and leastDeathsRole:
                await member.add_roles(leastDeathsRole)
            elif leastDeathsRole in member.roles:
                await member.remove_roles(leastDeathsRole)

            # Advancement roles
            if userWithMostAdvancements and username == userWithMostAdvancements[0] and mostAdvancementsRole:
                await member.add_roles(mostAdvancementsRole)
            elif mostAdvancementsRole in member.roles:
                await member.remove_roles(mostAdvancementsRole)

            if userWithLeastAdvancements and username == userWithLeastAdvancements[0] and leastAdvancementsRole:
                await member.add_roles(leastAdvancementsRole)
            elif leastAdvancementsRole in member.roles:
                await member.remove_roles(leastAdvancementsRole)

            # Playtime roles
            if userWithMostPlaytime and username == userWithMostPlaytime[0] and mostPlaytimeRole:
                await member.add_roles(mostPlaytimeRole)
            elif mostPlaytimeRole in member.roles:
                await member.remove_roles(mostPlaytimeRole)

            if userWithLowestPlaytime and username == userWithLowestPlaytime[0] and leastPlaytimeRole:
                await member.add_roles(leastPlaytimeRole)
            elif leastPlaytimeRole in member.roles:
                await member.remove_roles(leastPlaytimeRole)
        
        conn.commit()
    finally:
        db_close(conn)

@bot.event
async def on_message(message):
    # Ignore messages from bots
    if message.author.bot:
        return
        
    # First check playerlist command before anything else
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT serverIsOnline FROM server")
        serverIsOnline = cursor.fetchone()[0]
        
        if message.content.lower() == "playerlist" and not serverIsOnline:
            await message.channel.send("Server is offline, unable to perform the command")
            await bot.process_commands(message)
            return  # Return here to prevent further processing
    finally:
        db_close(conn)
    
    if message.channel.id != WEBHOOK_CHANNEL_ID:
        await bot.process_commands(message)
        return

    messageContent = message.content
    
    discordName = message.author.name

    if "### :octagonal_sign: **Server has stopped**" in messageContent:
        conn = await db_connect()
        try:
            cursor = conn.cursor()
            # Update server status
            cursor.execute("UPDATE server SET serverIsOnline = 0")
            
            # Get all online players and update their playtime
            cursor.execute("SELECT discordUsername, joinTime FROM users WHERE joinTime > 0")
            online_players = cursor.fetchall()
            current_time = int(time.time())
            
            for discord_username, join_time in online_players:
                # Update playtime
                cursor.execute("UPDATE users SET playtimeSeconds = playtimeSeconds + ? WHERE discordUsername = ?", 
                            (current_time - join_time, discord_username))
                # Reset join time
                cursor.execute("UPDATE users SET joinTime = 0 WHERE discordUsername = ?", 
                            (discord_username,))
            
            conn.commit()
        finally:
            db_close(conn)

        # Remove online role from all members who have it
        online_role = discord.utils.get(message.guild.roles, name=ONLINE_ROLE_NAME)
        if online_role:
            for member in message.guild.members:
                if online_role in member.roles and not member.bot:
                    await member.remove_roles(online_role)


    if "### :white_check_mark: **Server has started**" in messageContent:
        conn = await db_connect()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE server SET serverIsOnline = 1")
            conn.commit()
        finally:
            db_close(conn)

    # Handle join/leave messages
    if " joined the server" in messageContent:
        minecraftName = messageContent.split(" joined the server")[0]
        conn = await db_connect()
        try:
            cursor = conn.cursor()
            # First get the Discord username for this Minecraft name
            cursor.execute("SELECT discordUsername FROM users WHERE minecraftName = ?", (minecraftName,))
            result = cursor.fetchone()
            if result:
                discordUsername = result[0]
                # Then get the member using the correct Discord username
                member = discord.utils.get(message.guild.members, name=discordUsername)
                if member and not member.bot:  # Add check for bot
                    cursor.execute("UPDATE users SET joinTime = ? WHERE minecraftName = ?", (int(time.time()), minecraftName))
                    conn.commit()
                    role = discord.utils.get(message.guild.roles, name=ONLINE_ROLE_NAME)
                    if role:
                        await member.add_roles(role)
                    await message.add_reaction('✅')
                else:
                    await message.add_reaction('❓')
        finally:
            db_close(conn)

    elif " left the server" in messageContent:
        minecraftName = messageContent.split(" left the server")[0]
        conn = await db_connect()
        try:
            cursor = conn.cursor()
            # First get the Discord username for this Minecraft name
            cursor.execute("SELECT discordUsername, joinTime FROM users WHERE minecraftName = ?", (minecraftName,))
            result = cursor.fetchone()
            if result:
                discordUsername, joinTime = result
                # Update playtime
                if joinTime > 0:  # Make sure joinTime is valid
                    cursor.execute("UPDATE users SET playtimeSeconds = playtimeSeconds + ? WHERE minecraftName = ?", 
                                (int(time.time()) - joinTime, minecraftName))
                cursor.execute("UPDATE users SET joinTime = 0 WHERE minecraftName = ?", (minecraftName,))
                conn.commit()
                
                # Get the correct member using Discord username
                member = discord.utils.get(message.guild.members, name=discordUsername)
                if member and not member.bot:
                    role = discord.utils.get(message.guild.roles, name=ONLINE_ROLE_NAME)
                    if role and role in member.roles:
                        await member.remove_roles(role)
                    await message.add_reaction('👋')
                else:
                    await message.add_reaction('❓')
        finally:
            db_close(conn)

    # Handle death messages
    elif messageContent.startswith(DEATH_MARKER):
        parts = messageContent.split()
        if len(parts) > 1:
            minecraftName = parts[1]
            conn = await db_connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT discordUsername FROM users WHERE minecraftName = ?", (minecraftName,))
                result = cursor.fetchone()
                if result:
                    discordName = result[0]
                    # Update the users table directly
                    cursor.execute("UPDATE users SET deathCount = deathCount + 1 WHERE discordUsername = ?", (discordName,))
                    conn.commit()
                    await updateRanksRoles(message.guild)
            finally:
                db_close(conn)

    # Handle advancement messages
    elif messageContent.startswith(ADVANCEMENT_MARKER):
        parts = messageContent.split()
        if len(parts) > 1:
            minecraftName = parts[1]
            conn = await db_connect()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT discordUsername FROM users WHERE minecraftName = ?", (minecraftName,))
                result = cursor.fetchone()
                if result:
                    discordName = result[0]
                    # Update the users table directly
                    cursor.execute("UPDATE users SET advancementCount = advancementCount + 1 WHERE discordUsername = ?", (discordName,))
                    conn.commit()
                    await updateRanksRoles(message.guild)
            finally:
                db_close(conn)

    await bot.process_commands(message)

@bot.command(name='deaths')
async def deaths(ctx, user: discord.Member = None):
    user = user or ctx.author
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT deathCount FROM users WHERE discordUsername = ?", (user.name,))
        result = cursor.fetchone()
        deathCount = result[0] if result else 0
    finally:
        db_close(conn)
    await ctx.send(f"{user.display_name} has died {deathCount} times")

@bot.command(name='advancements')
async def advancements(ctx, user: discord.Member = None):
    user = user or ctx.author
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT advancementCount FROM users WHERE discordUsername = ?", (user.name,))
        result = cursor.fetchone()
        advCount = result[0] if result else 0
    finally:
        db_close(conn)
    await ctx.send(f"{user.display_name} has completed {advCount} advancements")

@bot.command(name='playtime')
async def playtime(ctx, user: discord.Member = None):
    user = user or ctx.author
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT playtimeSeconds FROM users WHERE discordUsername = ?", (user.name,))
        result = cursor.fetchone()
        playtime = result[0] if result else 0
    finally:
        db_close(conn)
    
    hours, remainder = divmod(playtime, 3600)
    minutes, _ = divmod(remainder, 60)
    
    if hours > 0:
        await ctx.send(f"{user.display_name} has played for {hours} hour(s) and {minutes} minute(s)")
    elif minutes > 0:
        await ctx.send(f"{user.display_name} has played for {minutes} minute(s)")
    else:
        await ctx.send(f"{user.display_name} hasn't played for any time")

@bot.command(name='addusername')
async def addUsername(ctx, minecraftName: str, discordName: discord.Member = None):
    if not isMod(ctx):
        discordName = None
    
    if discordName is not None:
        discordName = discordName.name
    
    if discordName is None:
        discordName = ctx.author.name
    
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE discordUsername = ?", (discordName,))
        result = cursor.fetchone()
        if result:
            await ctx.send("You have already registered a Minecraft username. Use !addusername to update it.")
            return
        
        cursor.execute("SELECT * FROM users WHERE minecraftName = ?", (minecraftName,))
        result = cursor.fetchone()
        if result:
            await ctx.send("This Minecraft username is already registered.")
            return
        
        cursor.execute(
            """
            INSERT INTO users (discordUsername, discordDisplayName, minecraftName) 
            VALUES (?, ?, ?) 
            ON CONFLICT (discordUsername) 
            DO UPDATE SET minecraftName = excluded.minecraftName
            """, 
            (discordName, ctx.guild.get_member_named(discordName).display_name, minecraftName)
        )
        conn.commit()
    finally:
        db_close(conn)
    
    await ctx.message.add_reaction('✅')

def isMod(ctx) -> bool:
    return discord.utils.get(ctx.author.roles, id=MOD_ROLE_ID) is not None

@bot.command(name='addhistory')
async def addHistory(ctx, user: discord.Member, statType: str, count: int):
    # Check if user has moderator permissions
    if not isMod(ctx):
        await ctx.send("You don't have permission to use this command.")
        return

    # Normalize stat type input
    statType = statType.lower()
    valid_stats = {
        'death': 'deathCount',
        'deaths': 'deathCount',
        'advancement': 'advancementCount',
        'advancements': 'advancementCount',
        'adv': 'advancementCount',
        'playtime': 'playtimeSeconds',
        'play': 'playtimeSeconds'
    }

    # Validate stat type
    if statType not in valid_stats:
        await ctx.send("Invalid stat type. Please use 'death', 'advancement', or 'playtime'")
        return

    column = valid_stats[statType]

    conn = await db_connect()
    try:
        cursor = conn.cursor()
        
        # Check if user exists in database
        cursor.execute(f"""
            SELECT {column}, discordDisplayName, minecraftName 
            FROM users 
            WHERE discordUsername = ?
        """, (user.name,))
        result = cursor.fetchone()

        if result:
            # User exists, update the stat
            current_count = result[0] 
            cursor.execute(f"""
                UPDATE users 
                SET {column} = ? 
                WHERE discordUsername = ?
            """, (current_count + count, user.name))
        else:
            # User doesn't exist, create new entry with default values
            cursor.execute("""
                INSERT INTO users (
                    discordUsername,
                    discordDisplayName,
                    minecraftName,
                    deathCount,
                    advancementCount,
                    playtimeSeconds
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user.name,
                user.display_name,
                user.name,  # Using discord username as default minecraft name
                count if column == 'deathCount' else 0,
                count if column == 'advancementCount' else 0,
                count if column == 'playtimeSeconds' else 0
            ))

        conn.commit()
    finally:
        db_close(conn)
    
    await ctx.message.add_reaction('✅')


@bot.command(name='deathlist')
async def deathList(ctx):
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT discordDisplayName, deathCount FROM users ORDER BY deathCount DESC")
        result = cursor.fetchall()
    finally:
        db_close(conn)
        
    if not result:
        await ctx.send("No death statistics recorded yet.")
        return
    
    message = "**Death Rankings:**\n```\n" + "\n".join(f"{name}: {count}" for name, count in result) + "\n```"
    await ctx.send(message)

@bot.command(name='advancementlist')
async def advancementList(ctx):
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT discordDisplayName, advancementCount FROM users ORDER BY advancementCount DESC")
        result = cursor.fetchall()
    finally:
        db_close(conn)
        
    if not result:
        await ctx.send("No advancement statistics recorded yet.")
        return
    
    message = "**Advancements Rankings:**\n```\n" + "\n".join(f"{name}: {count}" for name, count in result) + "\n```"
    await ctx.send(message)

@bot.command(name='playtimelist')
async def playtimeList(ctx):
    conn = await db_connect()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT discordDisplayName, playtimeSeconds FROM users ORDER BY playtimeSeconds DESC")
        result = cursor.fetchall()
    finally:
        db_close(conn)
        
    if not result:
        await ctx.send("No playtime statistics recorded yet.")
        return
    
    # Build the rankings list with playtime in hours and minutes
    message = "**Playtime Rankings:**\n```\n"
    
    for name, playtime in result:
        hours, remainder = divmod(playtime, 3600)
        minutes, _ = divmod(remainder, 60)
        formatted_playtime = f"{hours}h {minutes}m"
        message += f"{name}: {formatted_playtime}\n"
    
    message += "```"
    await ctx.send(message)

@bot.command(name='updateroles')
async def updateroles(ctx):
    if not isMod(ctx):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await updateRanksRoles(ctx.guild)
    await ctx.message.add_reaction('✅')

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
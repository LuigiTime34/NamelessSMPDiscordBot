import discord
from discord.ext import commands
import sqlite3
import time

from helperFunctions.database import initializeDatabase, addMinecraftToDiscordToDatabase

from const import *

# Initialize bot with required intents
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())

@bot.event
async def on_ready():
    startDatabasetime = time.time()
    initializeDatabase()
    print(f"Database initialized in {round(time.time() - startDatabasetime, 2)} seconds")
    
    addMinecraftToDiscordToDatabase(MINECRAFT_TO_DISCORD)

    # Create roles if they don't exist
    for roleName in ROLES:
        if not discord.utils.get(bot.guilds[0].roles, name=roleName):
            print(f"Warning: Role '{roleName}' not found in server")
            await bot.guilds[0].create_role(name=roleName)
    
    print(f'{bot.user.name} has connected to Discord!')

async def updateRanksRoles(bot):
    """Update the roles for most/least deaths and advancements"""
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deaths")
        deathsData = cursor.fetchall()
        
        cursor.execute("SELECT * FROM advancements")
        advancementsData = cursor.fetchall()

        if not deathsData or not advancementsData:
            return

        # Get or create roles
        mostDeathsRole = discord.utils.get(bot.roles, name=MOST_DEATHS_ROLE)
        leastDeathsRole = discord.utils.get(bot.roles, name=LEAST_DEATHS_ROLE)
        mostAdvancementsRole = discord.utils.get(bot.roles, name=MOST_ADVANCEMENTS_ROLE)
        leastAdvancementsRole = discord.utils.get(bot.roles, name=LEAST_ADVANCEMENTS_ROLE)

        # Find highest and lowest values
        if deathsData:
            maxDeaths = max([death[1] for death in deathsData])
            minDeaths = min([death[1] for death in deathsData])
            usersWithMostDeaths = [death[0] for death in deathsData if death[1] == maxDeaths]
            usersWithLeastDeaths = [death[0] for death in deathsData if death[1] == minDeaths]

        if advancementsData:
            max_adv = max([adv[1] for adv in advancementsData])
            min_adv = min([adv[1] for adv in advancementsData])
            usersWithMostAdvancements = [adv[0] for adv in advancementsData if adv[1] == max_adv]
            usersWithLeastAdvancements = [adv[0] for adv in advancementsData if adv[1] == min_adv]

        # Update roles for all members
        for member in bot.members:
            username = member.name

            # Deaths roles
            if username in usersWithMostDeaths and mostDeathsRole:
                await member.add_roles(mostDeathsRole)
            elif mostDeathsRole in member.roles:
                await member.remove_roles(mostDeathsRole)

            if username in usersWithLeastDeaths and leastDeathsRole:
                await member.add_roles(leastDeathsRole)
            elif leastDeathsRole in member.roles:
                await member.remove_roles(leastDeathsRole)

            # Advancement roles
            if username in usersWithMostAdvancements and mostAdvancementsRole:
                await member.add_roles(mostAdvancementsRole)
            elif mostAdvancementsRole in member.roles:
                await member.remove_roles(mostAdvancementsRole)

            if username in usersWithLeastAdvancements and leastAdvancementsRole:
                await member.add_roles(leastAdvancementsRole)
            elif leastAdvancementsRole in member.roles:
                await member.remove_roles(leastAdvancementsRole)


@bot.event
async def on_message(message):
    if message.channel.id != WEBHOOK_CHANNEL_ID:
        await bot.process_commands(message)
        return

    messageContent = message.content
    
    # Handle join/leave messages
    if " joined the server" in messageContent:
        minecraftName = messageContent.split(" joined the server")[0]
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_name FROM minecraft_to_discord WHERE minecraft_name = ?", (minecraftName,))
            result = cursor.fetchone()
            if result:
                discordName = result[1]
                member = discord.utils.get(message.guild.members, name=discordName)
                if member:
                    role = discord.utils.get(message.guild.roles, name=ONLINE_ROLE_NAME)
                    if role:
                        await member.add_roles(role)
                    await message.add_reaction('✅')
                else:
                    await message.add_reaction('❓')
            else:
                await message.add_reaction('❓')

    elif " left the server" in messageContent:
        minecraftName = messageContent.split(" left the server")[0]
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_name FROM minecraft_to_discord WHERE minecraft_name = ?", (minecraftName,))
            result = cursor.fetchone()
            if result:
                discordName = result[1]
                member = discord.utils.get(message.guild.members, name=discordName)
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
    elif messageContent.startswith(DEATH_MARKER):
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_name FROM minecraft_to_discord WHERE minecraft_name = ?", (minecraftName,))
            result = cursor.fetchone()
            if result:
                discordName = result[1]
                cursor.execute("SELECT death_count FROM deaths WHERE discord_name = ?", (discordName,))
                deathCount = cursor.fetchone()
                if deathCount:
                    cursor.execute("UPDATE deaths SET death_count = ? WHERE discord_name = ?", (deathCount[0] + 1, discordName))
                else:
                    cursor.execute("INSERT INTO deaths (discord_name, death_count) VALUES (?, 1)", (discordName,))
                conn.commit()
            await updateRanksRoles(message.guild)

    # Handle advancement messages
    elif messageContent.startswith(ADVANCEMENT_MARKER):
        with sqlite3.connect(DATABASE_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT discord_name FROM minecraft_to_discord WHERE minecraft_name = ?", (minecraftName,))
            result = cursor.fetchone()
            if result:
                discordName = result[1]
                cursor.execute("SELECT advancement_count FROM advancements WHERE discord_name = ?", (discordName,))
                advCount = cursor.fetchone()
                if advCount:
                    cursor.execute("UPDATE advancements SET advancement_count = ? WHERE discord_name = ?", (advCount[0] + 1, discordName))
                else:
                    cursor.execute("INSERT INTO advancements (discord_name, advancement_count) VALUES (?, 1)", (discordName,))
                conn.commit()
            await updateRanksRoles(message.guild)

    await bot.process_commands(message)

@bot.command(name='deaths')
async def deaths(ctx, user: discord.Member = None):
    user = user or ctx.author
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT death_count FROM deaths WHERE discord_name = ?", (user.name,))
        result = cursor.fetchone()
        deathCount = result[0] if result else 0
    await ctx.send(f"{user.name} has died {deathCount} times")

@bot.command(name='advancements')
async def advancements(ctx, user: discord.Member = None):
    user = user or ctx.author
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT advancement_count FROM advancements WHERE discord_name = ?", (user.name,))
        result = cursor.fetchone()
        advCount = result[0] if result else 0
    await ctx.send(f"{user.name} has completed {advCount} advancements")

@bot.command(name='addusername')
async def addUsername(ctx, minecraftName: str, discordName: discord.Member = None):
    if not isMod(ctx):
        discordName = None
    
    if discordName is not None:
        discordName = discordName.name
    
    if discordName is None:
        discordName = ctx.author.name
    

    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM minecraft_to_discord WHERE discord_name = ?", (discordName,))
        result = cursor.fetchone()
        if result:
            await ctx.send("You have already registered a Minecraft username. Use !addusername to update it.")
            return
        
        cursor.execute("SELECT * FROM minecraft_to_discord WHERE minecraft_name = ?", (minecraftName,))
        result = cursor.fetchone()
        if result:
            await ctx.send("This Minecraft username is already registered.")
            return
        
        cursor.execute(
            """
            INSERT INTO minecraft_to_discord (discord_name, minecraft_name) 
            VALUES (?, ?) 
            ON CONFLICT (discord_name) 
            DO UPDATE SET minecraft_name = excluded.minecraft_name
            """, 
            (discordName, minecraftName)
        )
        conn.commit()

def isMod(ctx) -> bool:
    return discord.utils.get(ctx.author.roles, id=MOD_ROLE_ID) is not None

@bot.command(name='addhistory')
async def addHistory(ctx, user: discord.Member, statType: str, count: int):
    if not isMod(ctx):
        await ctx.send("You don't have permission to use this command.")
        return
    
    if statType.lower() not in ['death', 'deaths', 'advancement', 'advancements', 'adv']:
        await ctx.send("Invalid stat type. Please use 'death' or 'advancement'")
        return
    
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        if statType in ['death', 'deaths']:
            cursor.execute("SELECT death_count FROM deaths WHERE discord_name = ?", (user.name,))
            result = cursor.fetchone()
            deathCount = result[0] if result else 0
            cursor.execute("INSERT INTO deaths (discord_name, death_count) VALUES (?, ?) ON CONFLICT (discord_name) DO UPDATE SET death_count = ?", (user.name, deathCount + count, deathCount + count))
        if statType in ['advancement', 'adv']:
            cursor.execute("SELECT advancement_count FROM advancements WHERE discord_name = ?", (user.name,))
            result = cursor.fetchone()
            advCount = result[0] if result else 0
            cursor.execute("INSERT INTO advancements (discord_name, advancement_count) VALUES (?, ?) ON CONFLICT (discord_name) DO UPDATE SET advancement_count = ?", (user.name, advCount + count, advCount + count))
        else:
            await ctx.send("Invalid stat type. Please use 'death' or 'advancement'")
            return
        conn.commit()
    
    await updateRanksRoles(ctx.guild)
    await ctx.message.add_reaction('✅')

@bot.command(name='deathlist')
async def deathList(ctx):
    if not isMod(ctx):
        await ctx.send("You don't have permission to use this command.")
        return
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM deaths")
        result = cursor.fetchall()
        if not result:
            await ctx.send("No death statistics recorded yet.")
            return
    
    sortedDeaths = sorted(result, key=lambda x: x[1], reverse=True)
    message = "**Death Rankings:**\n" + "\n".join(f"{name}: {count}" for name, count in sortedDeaths)
    await ctx.send(message)

@bot.command(name='advancementlist')
async def advancementList(ctx):
    if not isMod(ctx):
        await ctx.send("You don't have permission to use this command.")
        return
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM advancements")
        result = cursor.fetchall()
        if not result:
            await ctx.send("No advancement statistics recorded yet.")
            return
        
    
    sorted_adv = sorted(result, key=lambda x: x[1], reverse=True)
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
bot.run('')
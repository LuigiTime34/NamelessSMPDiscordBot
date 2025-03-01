import discord
import asyncio
import datetime
from database.queries import get_all_playtimes, get_all_advancements, get_all_deaths
from utils.formatters import format_playtime
from const import SCOREBOARD_CHANNEL_ID

# Global variable
leaderboard_messages = {'deaths': None, 'advancements': None, 'playtime': None}

async def update_leaderboards(bot, channel):
    """Update the leaderboard messages in the designated channel."""
    global leaderboard_messages
    
    # Create embeds
    current_time = int(datetime.datetime.now().timestamp())

    # Playtime leaderboard
    playtime_data = get_all_playtimes()
    playtime_embed = discord.Embed(
        title="🕒 Playtime Leaderboard",
        description=f"Who's spending their life on the server?\nUpdated: <t:{current_time}:T>",
        color=discord.Color.green()
    )
    
    if playtime_data:
        value = ""
        for i, (mc_name, _, seconds) in enumerate(playtime_data):  # Top 10
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {format_playtime(seconds)}\n"
        playtime_embed.add_field(name="Most Playtime", value=value, inline=False)
    
    # Advancements leaderboard
    adv_data = get_all_advancements()
    current_time = int(datetime.datetime.now().timestamp())
    adv_embed = discord.Embed(
        title="⭐ Advancements Leaderboard",
        description=f"Who's been busy progressing?\nUpdated: <t:{current_time}:T>",
        color=discord.Color.gold()
    )
    
    if adv_data:
        value = ""
        for i, (mc_name, _, advancements) in enumerate(adv_data):  # Top 10
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {advancements} advancements\n"
        adv_embed.add_field(name="Most Advancements", value=value, inline=False)
    
    # Deaths leaderboard
    deaths_data = get_all_deaths()
    current_time = int(datetime.datetime.now().timestamp())
    deaths_embed = discord.Embed(
        title="💀 Deaths Leaderboard",
        description=f"Who's been playing it safe?\nUpdated: <t:{current_time}:T>",
        color=discord.Color.red()
    )
    
    if deaths_data:
        value = ""
        for i, (mc_name, _, deaths) in enumerate(deaths_data):  # Top 10
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {deaths} deaths\n"
        deaths_embed.add_field(name="Least Deaths", value=value, inline=False)
    
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

async def leaderboard_update_task(bot):
    """Update leaderboards every minute."""
    await bot.wait_until_ready()
    channel = bot.get_channel(SCOREBOARD_CHANNEL_ID)
    
    if not channel:
        print(f"Could not find channel with ID {SCOREBOARD_CHANNEL_ID}")
        return
    
    while not bot.is_closed():
        try:
            await update_leaderboards(bot, channel)
        except Exception as e:
            print(f"Error in leaderboard update task: {e}")
        
        await asyncio.sleep(60)  # Update every minute
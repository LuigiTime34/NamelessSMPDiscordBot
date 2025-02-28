import discord
import asyncio
import datetime
from database.queries import get_all_deaths, get_all_advancements, get_all_playtimes
from utils.formatters import format_playtime
from const import SCOREBOARD_CHANNEL_ID

# Global variable to store leaderboard messages
leaderboard_messages = {'deaths': None, 'advancements': None, 'playtime': None}

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
        for i, (mc_name, _, seconds) in enumerate(playtime_data):
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
        for i, (mc_name, _, advancements) in enumerate(adv_data):
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
        for i, (mc_name, _, deaths) in enumerate(deaths_data):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            value += f"{medal} **`{mc_name}`**: {deaths} deaths\n"
        deaths_embed.add_field(name="Least Deaths", value=value, inline=False)
        deaths_embed.set_footer(text="Updated: " + datetime.datetime.now().strftime("%H:%M:%S"))
    
    # Update or send new messages
    try:
        # Check if we have existing messages and try to update them
        if leaderboard_messages['playtime'] and isinstance(leaderboard_messages['playtime'], discord.Message):
            try:
                await leaderboard_messages['playtime'].edit(embed=playtime_embed)
            except discord.NotFound:
                # Message was deleted, create a new one
                leaderboard_messages['playtime'] = await channel.send(embed=playtime_embed)
        else:
            # Try to find existing message first
            async for message in channel.history(limit=15):
                if message.author.id == channel.guild.me.id and message.embeds and "Playtime Leaderboard" in message.embeds[0].title:
                    leaderboard_messages['playtime'] = message
                    await message.edit(embed=playtime_embed)
                    break
            else:
                # No existing message found, create a new one
                leaderboard_messages['playtime'] = await channel.send(embed=playtime_embed)
        
        # Similar approach for advancements
        if leaderboard_messages['advancements'] and isinstance(leaderboard_messages['advancements'], discord.Message):
            try:
                await leaderboard_messages['advancements'].edit(embed=adv_embed)
            except discord.NotFound:
                leaderboard_messages['advancements'] = await channel.send(embed=adv_embed)
        else:
            async for message in channel.history(limit=15):
                if message.author.id == channel.guild.me.id and message.embeds and "Advancements Leaderboard" in message.embeds[0].title:
                    leaderboard_messages['advancements'] = message
                    await message.edit(embed=adv_embed)
                    break
            else:
                leaderboard_messages['advancements'] = await channel.send(embed=adv_embed)
        
        # And for deaths
        if leaderboard_messages['deaths'] and isinstance(leaderboard_messages['deaths'], discord.Message):
            try:
                await leaderboard_messages['deaths'].edit(embed=deaths_embed)
            except discord.NotFound:
                leaderboard_messages['deaths'] = await channel.send(embed=deaths_embed)
        else:
            async for message in channel.history(limit=15):
                if message.author.id == channel.guild.me.id and message.embeds and "Deaths Leaderboard" in message.embeds[0].title:
                    leaderboard_messages['deaths'] = message
                    await message.edit(embed=deaths_embed)
                    break
            else:
                leaderboard_messages['deaths'] = await channel.send(embed=deaths_embed)
        
        print("Updated leaderboards successfully")
    except Exception as e:
        print(f"Error updating leaderboards: {e}")

async def leaderboard_update_task(bot):
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
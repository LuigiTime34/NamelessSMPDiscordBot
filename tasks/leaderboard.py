import discord
import asyncio
import datetime
import pytz # Import pytz
import logging
from database.queries import get_all_playtimes, get_all_advancements, get_all_deaths
from utils.formatters import format_playtime
from const import SCOREBOARD_CHANNEL_ID
from utils.logging import setup_logging # Keep if you use setup_logging elsewhere

# Setup logger
logger = logging.getLogger('nameless_bot')

# Global variable to cache message IDs (consider storing in DB or file for persistence)
# For simplicity, we keep it in memory, but it will reset on bot restart.
leaderboard_messages = {'deaths': None, 'advancements': None, 'playtime': None}
leaderboard_message_ids = {'deaths': None, 'advancements': None, 'playtime': None}


async def update_leaderboards(bot, channel):
    """Update the leaderboard messages in the designated channel."""
    global leaderboard_messages, leaderboard_message_ids
    logger.debug(f"Attempting to update leaderboards in channel: {channel.name if channel else 'None'}")

    if not channel:
         logger.error("update_leaderboards called without a valid channel object.")
         # Try to fetch it as a fallback, but this indicates an issue in the calling code
         channel = bot.get_channel(SCOREBOARD_CHANNEL_ID)
         if not channel:
              logger.error(f"Could not find channel with ID {SCOREBOARD_CHANNEL_ID}. Leaderboard update failed.")
              return
         else:
              logger.warning("Fetched channel within update_leaderboards - caller should provide it.")


    # Fetch latest data
    playtime_data = get_all_playtimes()
    adv_data = get_all_advancements()
    deaths_data = get_all_deaths() # Sorted lowest to highest

    # Create embeds
    current_time_est = datetime.datetime.now(pytz.est)
    current_ts = int(current_time_est.timestamp())

    # Playtime leaderboard
    playtime_embed = discord.Embed(
        title="🕒 Playtime Leaderboard",
        description=f"Who's spending their life on the server?\nUpdated: <t:{current_ts}:R>", # Use relative time
        color=discord.Color.green()
    )
    if playtime_data:
        value = ""
        for i, (mc_name, _, seconds) in enumerate(playtime_data[:15]):  # Show top 15
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`{i+1: >2}`." # Pad numbers
            value += f"{medal} **`{mc_name}`**: {format_playtime(seconds)}\n"
        playtime_embed.add_field(name="Most Playtime", value=value or "No playtime recorded.", inline=False)
    else:
        playtime_embed.add_field(name="Most Playtime", value="No playtime recorded.", inline=False)

    # Advancements leaderboard
    adv_embed = discord.Embed(
        title="⭐ Advancements Leaderboard",
        description=f"Who's been busy progressing?\nUpdated: <t:{current_ts}:R>",
        color=discord.Color.gold()
    )
    if adv_data:
        value = ""
        for i, (mc_name, _, advancements) in enumerate(adv_data[:15]):  # Top 15
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`{i+1: >2}`."
            value += f"{medal} **`{mc_name}`**: {advancements} advancements\n"
        adv_embed.add_field(name="Most Advancements", value=value or "No advancements recorded.", inline=False)
    else:
        adv_embed.add_field(name="Most Advancements", value="No advancements recorded.", inline=False)

    # Deaths leaderboard (Least Deaths)
    deaths_embed = discord.Embed(
        title="💀 Deaths Leaderboard",
        description=f"Who's been playing it safe?\nUpdated: <t:{current_ts}:R>",
        color=discord.Color.red()
    )
    if deaths_data:
        value = ""
        # Remember deaths_data is sorted ASCENDING
        for i, (mc_name, _, deaths) in enumerate(deaths_data[:15]):  # Top 15 safest
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`{i+1: >2}`."
            value += f"{medal} **`{mc_name}`**: {deaths} deaths\n"
        deaths_embed.add_field(name="Least Deaths", value=value or "No deaths recorded.", inline=False)
    else:
         deaths_embed.add_field(name="Least Deaths", value="No deaths recorded.", inline=False)


    # --- Update or Create Messages ---
    # Try to fetch messages using cached IDs first, more reliable than history scan
    async def edit_or_send(key, embed):
        global leaderboard_messages, leaderboard_message_ids
        message_obj = leaderboard_messages.get(key)
        message_id = leaderboard_message_ids.get(key)

        # 1. Try editing using cached message object
        if message_obj:
            try:
                await message_obj.edit(embed=embed)
                logger.debug(f"Edited leaderboard message for {key} using cached object.")
                return message_obj # Return updated object
            except (discord.NotFound, discord.HTTPException) as e:
                logger.warning(f"Failed to edit {key} leaderboard using cached object (ID: {message_obj.id}): {e}. Will try fetching by ID.")
                leaderboard_messages[key] = None # Invalidate cache
                message_obj = None # Clear object

        # 2. Try fetching by ID and editing
        if message_id and not message_obj:
             try:
                 message_obj = await channel.fetch_message(message_id)
                 await message_obj.edit(embed=embed)
                 leaderboard_messages[key] = message_obj # Update cache
                 logger.info(f"Fetched and edited leaderboard message for {key} (ID: {message_id}).")
                 return message_obj
             except (discord.NotFound, discord.HTTPException) as e:
                 logger.warning(f"Failed to fetch/edit {key} leaderboard using ID {message_id}: {e}. Will send new message.")
                 leaderboard_message_ids[key] = None # Invalidate ID cache too
                 message_obj = None

        # 3. If editing failed or no ID, send a new message
        if not message_obj:
             try:
                 logger.info(f"Sending new leaderboard message for {key}.")
                 new_msg = await channel.send(embed=embed)
                 leaderboard_messages[key] = new_msg
                 leaderboard_message_ids[key] = new_msg.id # Cache new ID
                 # Optionally: Delete old messages if found in history? More complex.
                 return new_msg
             except discord.HTTPException as e:
                 logger.error(f"Failed to send new leaderboard message for {key}: {e}")
                 return None

    # Call the edit_or_send function for each leaderboard type
    leaderboard_messages['playtime'] = await edit_or_send('playtime', playtime_embed)
    leaderboard_messages['advancements'] = await edit_or_send('advancements', adv_embed)
    leaderboard_messages['deaths'] = await edit_or_send('deaths', deaths_embed)

    logger.info("Finished leaderboard update cycle.")
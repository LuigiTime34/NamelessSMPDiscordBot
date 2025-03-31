import discord
import asyncio
from const import (
    ONLINE_ROLE_NAME, MOST_DEATHS_ROLE, LEAST_DEATHS_ROLE,
    MOST_ADVANCEMENTS_ROLE, LEAST_ADVANCEMENTS_ROLE, MOST_PLAYTIME_ROLE,
    LEAST_PLAYTIME_ROLE
)
from database.queries import get_all_deaths, get_all_advancements, get_all_playtimes, get_player_stats, get_all_players
from utils.discord_helpers import get_discord_user
import logging

# Setup logger
logger = logging.getLogger('nameless_bot')

async def add_online_role(member):
    """Add the online role to a Discord member."""
    if not member: return # Guard clause
    try:
        role = discord.utils.get(member.guild.roles, name=ONLINE_ROLE_NAME)
        if role and role not in member.roles:
            await member.add_roles(role, reason="Player logged into Minecraft server")
            logger.info(f"Added {ONLINE_ROLE_NAME} role to {member.display_name} ({member.id})")
    except discord.HTTPException as e:
         logger.error(f"Failed to add online role to {member.display_name}: {e}")

async def remove_online_role(member):
    """Remove the online role from a Discord member."""
    if not member: return # Guard clause
    try:
        role = discord.utils.get(member.guild.roles, name=ONLINE_ROLE_NAME)
        if role and role in member.roles:
            await member.remove_roles(role, reason="Player logged out of Minecraft server")
            logger.info(f"Removed {ONLINE_ROLE_NAME} role from {member.display_name} ({member.id})")
    except discord.HTTPException as e:
        logger.error(f"Failed to remove online role from {member.display_name}: {e}")


async def clear_all_online_roles(guild):
    """Remove online role from all members in the guild."""
    if not guild: return
    role = discord.utils.get(guild.roles, name=ONLINE_ROLE_NAME)
    if role:
        members_with_role = [member for member in guild.members if role in member.roles]
        cleared_count = 0
        for member in members_with_role:
            try:
                await member.remove_roles(role, reason="Server stopped / Bot clearing roles")
                cleared_count += 1
            except discord.HTTPException as e:
                 logger.warning(f"Failed to remove online role from {member.display_name} during clear: {e}")
        if cleared_count > 0:
            logger.info(f"Cleared {ONLINE_ROLE_NAME} role from {cleared_count} members in guild {guild.name}")
        # else: # Optional: reduce log spam
        #     logger.debug(f"No members had the {ONLINE_ROLE_NAME} role to clear in guild {guild.name}")


async def update_achievement_roles(bot, guild):
    """Update all achievement roles based on current stats."""
    if not guild:
        logger.warning("update_achievement_roles called without a valid guild.")
        return

    logger.info(f"Updating achievement roles in guild {guild.name}...")

    # --- Get Data ---
    try:
        deaths_data = get_all_deaths() # sorted low -> high
        advancements_data = get_all_advancements() # sorted high -> low
        playtimes_data = get_all_playtimes() # sorted high -> low
    except Exception as e:
        logger.error(f"Failed to fetch data for role update: {e}")
        return

    # --- Find Roles ---
    roles_to_find = {
        'most_deaths': MOST_DEATHS_ROLE, 'least_deaths': LEAST_DEATHS_ROLE,
        'most_adv': MOST_ADVANCEMENTS_ROLE, 'least_adv': LEAST_ADVANCEMENTS_ROLE,
        'most_playtime': MOST_PLAYTIME_ROLE, 'least_playtime': LEAST_PLAYTIME_ROLE,
    }
    roles = {}
    missing_roles = []
    for key, name in roles_to_find.items():
        role = discord.utils.get(guild.roles, name=name)
        if role:
            roles[key] = role
        else:
            missing_roles.append(name)

    if missing_roles:
        logger.warning(f"Missing achievement roles in guild {guild.name}: {', '.join(missing_roles)}")

    # --- Determine New Role Holders ---
    new_holders = {role: set() for role in roles.values()} # Map Role Object -> Set[Member Object]

    # Helper to add player to role set if member found
    async def add_holder(role_key, player_data):
        if roles.get(role_key) and player_data:
            mc_username, discord_identifier, _ = player_data[:3] # Use first 3 elements
            # Try fetching by DB discord_username first
            member = get_discord_user(bot, discord_identifier, guild) # Pass guild context
            if member:
                new_holders[roles[role_key]].add(member)
            else:
                logger.debug(f"Could not find Discord member for {mc_username} ({discord_identifier}) for role {roles[role_key].name}")


    # Most Deaths (Skill Issue) - Top player(s) from deaths_data (sorted low->high, so take last)
    if deaths_data and 'most_deaths' in roles:
        max_deaths = deaths_data[-1][2]
        most_deaths_players = [p for p in deaths_data if p[2] == max_deaths]
        for player in most_deaths_players:
            await add_holder('most_deaths', player)

    # Least Deaths (Safety First) - Lowest non-zero deaths with >= 5h playtime
    if deaths_data and 'least_deaths' in roles:
        min_eligible_deaths = float('inf')
        eligible_players_least_deaths = []
        for player in deaths_data:
            mc_name, disc_id, deaths = player
            if deaths > 0: # Must have died at least once
                 stats = get_player_stats(minecraft_username=mc_name)
                 if stats and stats[4] >= 18000: # 5 hours playtime
                     if deaths < min_eligible_deaths:
                          min_eligible_deaths = deaths
                          eligible_players_least_deaths = [player] # Start new list
                     elif deaths == min_eligible_deaths:
                          eligible_players_least_deaths.append(player) # Add ties

        if min_eligible_deaths != float('inf'):
            for player in eligible_players_least_deaths:
                await add_holder('least_deaths', player)

    # Most Advancements (Overachiever) - Top player(s) from advancements_data (already sorted high->low)
    if advancements_data and 'most_adv' in roles:
        max_adv = advancements_data[0][2]
        most_adv_players = [p for p in advancements_data if p[2] == max_adv]
        for player in most_adv_players:
            await add_holder('most_adv', player)

    # Least Advancements (Beginner) - Lowest advancements with >= 5 min playtime
    if advancements_data and 'least_adv' in roles:
        min_eligible_adv = float('inf')
        eligible_players_least_adv = []
        # We need ALL players, not just sorted list, to find minimums correctly with playtime check
        all_players_stats = get_all_players()
        for mc_name, disc_id, _, advancements, playtime in all_players_stats:
            if playtime >= 300: # 5 mins playtime
                if advancements < min_eligible_adv:
                    min_eligible_adv = advancements
                    eligible_players_least_adv = [(mc_name, disc_id, advancements)] # Store tuple needed by add_holder
                elif advancements == min_eligible_adv:
                    eligible_players_least_adv.append((mc_name, disc_id, advancements))

        if min_eligible_adv != float('inf'):
            for player in eligible_players_least_adv:
                 await add_holder('least_adv', player)


    # Most Playtime (No Life) - Top player(s) from playtimes_data (already sorted high->low)
    if playtimes_data and 'most_playtime' in roles:
        max_playtime = playtimes_data[0][2]
        most_playtime_players = [p for p in playtimes_data if p[2] == max_playtime]
        for player in most_playtime_players:
            await add_holder('most_playtime', player)

    # Least Playtime (Sleeping) - Lowest playtime >= 5 min
    if playtimes_data and 'least_playtime' in roles:
        min_eligible_playtime = float('inf')
        eligible_players_least_playtime = []
        # playtimes_data is sorted high->low, iterate backwards for efficiency maybe? Or just filter.
        eligible_for_least = [p for p in playtimes_data if p[2] >= 300] # Filter for 5 min+

        if eligible_for_least:
            min_eligible_playtime = eligible_for_least[-1][2] # Lowest playtime is last in the filtered list
            least_playtime_players = [p for p in eligible_for_least if p[2] == min_eligible_playtime]
            for player in least_playtime_players:
                await add_holder('least_playtime', player)

    # --- Apply Role Changes ---
    logger.debug(f"New role holders calculated: { {r.name: {m.name for m in members} for r, members in new_holders.items()} }")
    tasks = []
    for role, expected_members in new_holders.items():
        if not role: continue # Skip if role wasn't found

        current_members = set(member for member in guild.members if role in member.roles)

        members_to_add = expected_members - current_members
        members_to_remove = current_members - expected_members

        for member in members_to_add:
            tasks.append(member.add_roles(role, reason="Achieved criteria"))
            logger.info(f"Queueing add {role.name} to {member.display_name}")

        for member in members_to_remove:
             tasks.append(member.remove_roles(role, reason="Lost criteria"))
             logger.info(f"Queueing remove {role.name} from {member.display_name}")

    # Run all role changes concurrently
    if tasks:
        logger.info(f"Applying {len(tasks)} role changes...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Find the corresponding task to log which one failed
                # This is a bit tricky as order might not be guaranteed? But likely is.
                # A more robust way would be to wrap each coro in a function that logs on error.
                logger.error(f"Failed to apply role change (task index {i}): {result}")
        logger.info("Finished applying role changes.")
    else:
        logger.info("No achievement role changes needed.")


# REMOVED role_update_task function
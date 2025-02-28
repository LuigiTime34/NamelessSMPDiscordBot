import discord
import asyncio
from database.queries import (
    get_all_deaths, get_player_stats, get_all_advancements, get_all_playtimes
)
from utils.discord_helpers import get_discord_user

async def add_online_role(member, role_name):
    """Add the online role to a Discord member."""
    if member:
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and role not in member.roles:
            await member.add_roles(role)
            print(f"Added {role_name} role to {member.name}")

async def remove_online_role(member, role_name):
    """Remove the online role from a Discord member."""
    if member:
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and role in member.roles:
            await member.remove_roles(role)
            print(f"Removed {role_name} role from {member.name}")

async def clear_all_online_roles(guild, role_name):
    """Remove online role from all members in the guild."""
    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        members_with_role = [member for member in guild.members if role in member.roles]
        for member in members_with_role:
            await member.remove_roles(role)
        print(f"Cleared {role_name} role from {len(members_with_role)} members")

async def update_achievement_roles(guild, bot, role_config):
    """
    Update achievement roles based on current stats without removing roles unnecessarily.
    
    Args:
        guild: Discord guild object
        bot: Discord bot instance
        role_config: Dictionary containing role configuration names
    """
    print("Updating achievement roles...")
    
    # Get data
    deaths_data = get_all_deaths()
    advancements_data = get_all_advancements()
    playtimes_data = get_all_playtimes()
    
    # Define roles
    most_deaths_role = discord.utils.get(guild.roles, name=role_config["MOST_DEATHS_ROLE"])
    least_deaths_role = discord.utils.get(guild.roles, name=role_config["LEAST_DEATHS_ROLE"])
    most_adv_role = discord.utils.get(guild.roles, name=role_config["MOST_ADVANCEMENTS_ROLE"])
    least_adv_role = discord.utils.get(guild.roles, name=role_config["LEAST_ADVANCEMENTS_ROLE"])
    most_playtime_role = discord.utils.get(guild.roles, name=role_config["MOST_PLAYTIME_ROLE"])
    least_playtime_role = discord.utils.get(guild.roles, name=role_config["LEAST_PLAYTIME_ROLE"])
    
    # Track who should have each role
    should_have_most_deaths = []
    should_have_least_deaths = []
    should_have_most_adv = []
    should_have_least_adv = []
    should_have_most_playtime = []
    should_have_least_playtime = []
    
    # Handle most deaths
    if deaths_data and most_deaths_role:
        most_deaths = max(deaths_data, key=lambda x: x[2])
        most_deaths_players = [p for p in deaths_data if p[2] == most_deaths[2]]
        for player in most_deaths_players:
            discord_member = get_discord_user(bot, player[1])
            if discord_member:
                should_have_most_deaths.append(discord_member)
    
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
                    should_have_least_deaths.append(discord_member)
    
    # Handle most advancements
    if advancements_data and most_adv_role:
        max_adv = max(advancements_data, key=lambda x: x[2])[2]
        most_adv_players = [p for p in advancements_data if p[2] == max_adv]
        for player in most_adv_players:
            discord_member = get_discord_user(bot, player[1])
            if discord_member:
                should_have_most_adv.append(discord_member)
    
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
                    should_have_least_adv.append(discord_member)
    
    # Handle most playtime
    if playtimes_data and most_playtime_role:
        max_playtime = max(playtimes_data, key=lambda x: x[2])[2]
        most_playtime_players = [p for p in playtimes_data if p[2] == max_playtime]
        for player in most_playtime_players:
            discord_member = get_discord_user(bot, player[1])
            if discord_member:
                should_have_most_playtime.append(discord_member)
    
    # Handle least playtime (need at least 5 minutes)
    if playtimes_data and least_playtime_role:
        eligible_players = [p for p in playtimes_data if p[2] >= 300]  # 5 minutes
        if eligible_players:
            min_playtime = min(eligible_players, key=lambda x: x[2])[2]
            least_playtime_players = [p for p in eligible_players if p[2] == min_playtime]
            for player in least_playtime_players:
                discord_member = get_discord_user(bot, player[1])
                if discord_member:
                    should_have_least_playtime.append(discord_member)

    # Update roles without removing all roles first
    # Process most deaths role
    await update_specific_role(most_deaths_role, should_have_most_deaths)
    
    # Process least deaths role
    await update_specific_role(least_deaths_role, should_have_least_deaths)
    
    # Process most advancements role
    await update_specific_role(most_adv_role, should_have_most_adv)
    
    # Process least advancements role
    await update_specific_role(least_adv_role, should_have_least_adv)
    
    # Process most playtime role
    await update_specific_role(most_playtime_role, should_have_most_playtime)
    
    # Process least playtime role
    await update_specific_role(least_playtime_role, should_have_least_playtime)

async def update_specific_role(role, should_have_members):
    """
    Update a specific role by adding/removing as needed without clearing all first.
    
    Args:
        role: The Discord role to update
        should_have_members: List of members who should have this role
    """
    if not role:
        return
        
    # Get current members with this role
    current_members = [m for m in role.guild.members if role in m.roles]
    
    # Remove role from members who shouldn't have it
    for member in current_members:
        if member not in should_have_members:
            await member.remove_roles(role)
            print(f"Removed {role.name} from {member.name}")
    
    # Add role to members who should have it but don't
    for member in should_have_members:
        if role not in member.roles:
            await member.add_roles(role)
            print(f"Added {role.name} to {member.name}")

async def role_update_task(bot, role_config):
    """Background task to update achievement roles every minute."""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                await update_achievement_roles(guild, bot, role_config)
        except Exception as e:
            print(f"Error in role update task: {e}")
        
        await asyncio.sleep(60)  # Update every minute
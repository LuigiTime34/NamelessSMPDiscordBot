import discord
import asyncio
from const import (
    ONLINE_ROLE_NAME, MOST_DEATHS_ROLE, LEAST_DEATHS_ROLE,
    MOST_ADVANCEMENTS_ROLE, LEAST_ADVANCEMENTS_ROLE, MOST_PLAYTIME_ROLE,
    LEAST_PLAYTIME_ROLE
)
from database.queries import get_all_deaths, get_all_advancements, get_all_playtimes, get_player_stats
from utils.discord_helpers import get_discord_user

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

async def update_achievement_roles(bot, guild):
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

async def role_update_task(bot):
    """Update achievement roles every minute."""
    await bot.wait_until_ready()
    
    while not bot.is_closed():
        try:
            for guild in bot.guilds:
                await update_achievement_roles(bot, guild)
        except Exception as e:
            print(f"Error in role update task: {e}")
        
        await asyncio.sleep(60)  # Update every minute
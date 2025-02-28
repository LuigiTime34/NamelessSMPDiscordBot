import discord
from const import ONLINE_ROLE_NAME, MINECRAFT_TO_DISCORD

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
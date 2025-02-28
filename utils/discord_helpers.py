from const import MINECRAFT_TO_DISCORD

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
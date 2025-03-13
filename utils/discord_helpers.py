def get_minecraft_from_discord(discord_name):
    """Get Minecraft username from Discord username."""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT minecraft_username FROM player_stats WHERE LOWER(discord_username) = LOWER(?)",
        (discord_name,)
    )
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else None

def get_discord_from_minecraft(minecraft_username):
    """Get Discord username from Minecraft username."""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT discord_username FROM player_stats WHERE minecraft_username = ?",
        (minecraft_username,)
    )
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result else None

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
        discord_name = get_discord_from_minecraft(mc_name)
        if discord_name:
            for member in guild.members:
                if member.name.lower() == discord_name.lower() or str(member).lower() == discord_name.lower():
                    # Use display name (nickname) if available, otherwise fall back to username
                    display_names.append(member.display_name)
                    break
    
    return display_names

def get_minecraft_to_discord_mapping():
    """Get the current mapping of Minecraft usernames to Discord usernames from the database."""
    from database.connection import get_connection
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT minecraft_username, discord_username FROM player_stats")
    mapping = {row[0]: row[1] for row in cursor.fetchall()}
    
    conn.close()
    return mapping

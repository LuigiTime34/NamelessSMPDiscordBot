import discord
from const import MINECRAFT_TO_DISCORD
from database.queries import get_player_stats, get_all_deaths, get_all_advancements, get_all_playtimes
from utils.formatters import format_playtime
from utils.discord_helpers import get_minecraft_from_discord

async def deaths_command(ctx, bot, username=None):
    """Show death count for a player."""
    
    # Determine which player to show
    minecraft_username = None
    
    if username:
        # Check if direct Minecraft username
        if username in MINECRAFT_TO_DISCORD:
            minecraft_username = username
        else:
            # Try to find by Discord name
            for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                if disc_name.lower() == username.lower():
                    minecraft_username = mc_name
                    break
    else:
        # Use command author
        author_name = ctx.author.name
        minecraft_username = get_minecraft_from_discord(author_name)
    
    if not minecraft_username:
        await ctx.send("Could not find a matching player. Please specify a valid username.")
        return
    
    # Get stats
    stats = get_player_stats(minecraft_username=minecraft_username)
    
    if stats:
        embed = discord.Embed(
            title=f"Death Count for {minecraft_username}",
            description=f"💀 **{minecraft_username}** has died **{stats[2]}** times.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}")

async def advancements_command(ctx, bot, username=None):
    """Show advancement count for a player."""
    
    # Determine which player to show
    minecraft_username = None
    
    if username:
        # Check if direct Minecraft username
        if username in MINECRAFT_TO_DISCORD:
            minecraft_username = username
        else:
            # Try to find by Discord name
            for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                if disc_name.lower() == username.lower():
                    minecraft_username = mc_name
                    break
    else:
        # Use command author
        author_name = ctx.author.name
        minecraft_username = get_minecraft_from_discord(author_name)
    
    if not minecraft_username:
        await ctx.send("Could not find a matching player. Please specify a valid username.")
        return
    
    # Get stats
    stats = get_player_stats(minecraft_username=minecraft_username)
    
    if stats:
        embed = discord.Embed(
            title=f"Advancement Count for {minecraft_username}",
            description=f"⭐ **{minecraft_username}** has earned **{stats[3]}** advancements.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}")

async def playtime_command(ctx, bot, username=None):
    """Show playtime for a player."""
    # await ctx.message.add_reaction('✅')
    
    # Determine which player to show
    minecraft_username = None
    
    if username:
        # Check if direct Minecraft username
        if username in MINECRAFT_TO_DISCORD:
            minecraft_username = username
        else:
            # Try to find by Discord name
            for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                if disc_name.lower() == username.lower():
                    minecraft_username = mc_name
                    break
    else:
        # Use command author
        author_name = ctx.author.name
        minecraft_username = get_minecraft_from_discord(author_name)
    
    if not minecraft_username:
        await ctx.send("Could not find a matching player. Please specify a valid username.")
        return
    
    # Get stats
    stats = get_player_stats(minecraft_username=minecraft_username)
    
    if stats:
        formatted_time = format_playtime(stats[4])
        embed = discord.Embed(
            title=f"Playtime for {minecraft_username}",
            description=f"🕒 **{minecraft_username}** has played for **{formatted_time}**!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}")

async def deathlist_command(ctx, bot):
    """Show death counts for all players."""
    # await ctx.message.add_reaction('✅')
    
    deaths_data = get_all_deaths()
    
    if deaths_data:
        embed = discord.Embed(
            title="Death Counts",
            description="All player death counts (lowest to highest)",
            color=discord.Color.red()
        )
        
        value = "```\n"
        for mc_name, _, deaths in deaths_data:
            value += f"{mc_name}: {deaths}\n"
        value += "```"
        
        embed.add_field(name="Deaths", value=value, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No death data available.")

async def advancementlist_command(ctx, bot):
    """Show advancement counts for all players."""
    # await ctx.message.add_reaction('✅')
    
    adv_data = get_all_advancements()
    
    if adv_data:
        embed = discord.Embed(
            title="Advancement Counts",
            description="All player advancement counts (highest to lowest)",
            color=discord.Color.gold()
        )
        
        value = "```\n"
        for mc_name, _, advancements in adv_data:
            value += f"{mc_name}: {advancements}\n"
        value += "```"
        
        embed.add_field(name="Advancements", value=value, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No advancement data available.")

async def playtimelist_command(ctx, bot):
    """Show playtimes for all players."""
    # await ctx.message.add_reaction('✅')
    
    playtime_data = get_all_playtimes()
    
    if playtime_data:
        embed = discord.Embed(
            title="Playtime Counts",
            description="All player playtimes (highest to lowest)",
            color=discord.Color.green()
        )
        
        value = "```\n"
        for mc_name, _, seconds in playtime_data:
            value += f"{mc_name}: {format_playtime(seconds)}\n"
        value += "```"
        
        embed.add_field(name="Playtime", value=value, inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("No playtime data available.")
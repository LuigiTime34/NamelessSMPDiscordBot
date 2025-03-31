import discord
import datetime
import pytz # Import for timezone
from const import MINECRAFT_TO_DISCORD
from database.queries import ( # Ensure all needed functions are imported
    get_player_stats, get_all_deaths, get_all_advancements, get_all_playtimes,
    get_stats_for_period, get_connection
)
from utils.formatters import format_playtime
from utils.discord_helpers import get_minecraft_from_discord
import logging # Import logging

logger = logging.getLogger('nameless_bot') # Setup logger

async def deaths_command(ctx, bot, username=None):
    """Show death count for a player."""
    await ctx.message.add_reaction('💀') # React immediately

    # Determine which player to show
    minecraft_username = None
    target_display = username # For error messages

    if username:
        # Check if direct Minecraft username (case-insensitive check recommended)
        stats_direct = get_player_stats(minecraft_username=username)
        if stats_direct:
            minecraft_username = stats_direct[0] # Use the exact case from DB
        else:
            # Try to find by Discord name (case-insensitive)
            stats_discord = get_player_stats(discord_username=username.lower())
            if stats_discord:
                 minecraft_username = stats_discord[0]
            else: # Also check MINECRAFT_TO_DISCORD as a fallback if needed
                 for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                     if disc_name.lower() == username.lower():
                         minecraft_username = mc_name
                         break
    else:
        # Use command author's Discord name (case-insensitive)
        author_discord_name = str(ctx.author).lower() # Use full "user#discriminator" or "new_username"
        target_display = ctx.author.mention
        stats_author = get_player_stats(discord_username=author_discord_name)
        if stats_author:
            minecraft_username = stats_author[0]
        else: # Fallback using MINECRAFT_TO_DISCORD map if direct lookup fails
             minecraft_username = get_minecraft_from_discord(str(ctx.author)) # Uses the old mapping lookup

    if not minecraft_username:
        await ctx.send(f"Could not find a matching player for '{target_display}'. Please specify a valid Minecraft or Discord username, or ensure you are linked.")
        return

    # Get stats using the determined Minecraft username
    stats = get_player_stats(minecraft_username=minecraft_username)

    if stats:
        embed = discord.Embed(
            title=f"Death Count for {minecraft_username}",
            description=f"💀 **{minecraft_username}** has died **{stats[2]}** times.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        # This case should ideally not happen if minecraft_username was found above
        await ctx.send(f"No stats found for {minecraft_username}, even though the user was identified. Please check the database.")

async def advancements_command(ctx, bot, username=None):
    """Show advancement count for a player."""
    await ctx.message.add_reaction('⭐') # React immediately

    # Determine which player to show (using similar logic as deaths_command)
    minecraft_username = None
    target_display = username

    if username:
        stats_direct = get_player_stats(minecraft_username=username)
        if stats_direct:
            minecraft_username = stats_direct[0]
        else:
            stats_discord = get_player_stats(discord_username=username.lower())
            if stats_discord:
                 minecraft_username = stats_discord[0]
            else:
                 for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                     if disc_name.lower() == username.lower():
                         minecraft_username = mc_name
                         break
    else:
        author_discord_name = str(ctx.author).lower()
        target_display = ctx.author.mention
        stats_author = get_player_stats(discord_username=author_discord_name)
        if stats_author:
            minecraft_username = stats_author[0]
        else:
             minecraft_username = get_minecraft_from_discord(str(ctx.author))

    if not minecraft_username:
        await ctx.send(f"Could not find a matching player for '{target_display}'. Please specify a valid Minecraft or Discord username, or ensure you are linked.")
        return

    stats = get_player_stats(minecraft_username=minecraft_username)

    if stats:
        embed = discord.Embed(
            title=f"Advancement Count for {minecraft_username}",
            description=f"⭐ **{minecraft_username}** has earned **{stats[3]}** advancements.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"No stats found for {minecraft_username}, even though the user was identified. Please check the database.")

async def playtime_command(ctx, bot, username=None):
    """Show playtime for a player."""
    await ctx.message.add_reaction('🕒') # React immediately

    # Determine which player to show (using similar logic as deaths_command)
    minecraft_username = None
    target_display = username

    if username:
        stats_direct = get_player_stats(minecraft_username=username)
        if stats_direct:
            minecraft_username = stats_direct[0]
        else:
            stats_discord = get_player_stats(discord_username=username.lower())
            if stats_discord:
                 minecraft_username = stats_discord[0]
            else:
                 for mc_name, disc_name in MINECRAFT_TO_DISCORD.items():
                     if disc_name.lower() == username.lower():
                         minecraft_username = mc_name
                         break
    else:
        author_discord_name = str(ctx.author).lower()
        target_display = ctx.author.mention
        stats_author = get_player_stats(discord_username=author_discord_name)
        if stats_author:
            minecraft_username = stats_author[0]
        else:
             minecraft_username = get_minecraft_from_discord(str(ctx.author))

    if not minecraft_username:
        await ctx.send(f"Could not find a matching player for '{target_display}'. Please specify a valid Minecraft or Discord username, or ensure you are linked.")
        return

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
        await ctx.send(f"No stats found for {minecraft_username}, even though the user was identified. Please check the database.")

async def deathlist_command(ctx, bot):
    """Show death counts for all players."""
    await ctx.message.add_reaction('💀')

    deaths_data = get_all_deaths() # Already sorted lowest to highest

    if deaths_data:
        embed = discord.Embed(
            title="Death Counts",
            description="All player death counts (lowest to highest)",
            color=discord.Color.red()
        )

        # Paginate if too long
        value_str = ""
        char_count = 0
        page = 1
        total_players = len(deaths_data)
        players_on_page = 0
        max_chars = 1000 # Max chars per field value

        for mc_name, _, deaths in deaths_data:
            line = f"{mc_name}: {deaths}\n"
            if char_count + len(line) > max_chars and players_on_page > 0:
                embed.add_field(name=f"Deaths (Page {page})", value=f"```{value_str}```", inline=False)
                value_str = line
                char_count = len(line)
                players_on_page = 1
                page += 1
            else:
                value_str += line
                char_count += len(line)
                players_on_page += 1

        # Add the last page
        if value_str:
             embed.add_field(name=f"Deaths (Page {page})", value=f"```{value_str}```", inline=False)

        if total_players == 0:
             embed.add_field(name="Deaths", value="No death data available.", inline=False)

        await ctx.send(embed=embed)
    else:
        await ctx.send("No death data available.")

async def advancementlist_command(ctx, bot):
    """Show advancement counts for all players."""
    await ctx.message.add_reaction('⭐')

    adv_data = get_all_advancements() # Already sorted highest to lowest

    if adv_data:
        embed = discord.Embed(
            title="Advancement Counts",
            description="All player advancement counts (highest to lowest)",
            color=discord.Color.gold()
        )

        # Paginate
        value_str = ""
        char_count = 0
        page = 1
        total_players = len(adv_data)
        players_on_page = 0
        max_chars = 1000

        for mc_name, _, advancements in adv_data:
            line = f"{mc_name}: {advancements}\n"
            if char_count + len(line) > max_chars and players_on_page > 0:
                 embed.add_field(name=f"Advancements (Page {page})", value=f"```{value_str}```", inline=False)
                 value_str = line
                 char_count = len(line)
                 players_on_page = 1
                 page += 1
            else:
                 value_str += line
                 char_count += len(line)
                 players_on_page += 1

        if value_str:
             embed.add_field(name=f"Advancements (Page {page})", value=f"```{value_str}```", inline=False)

        if total_players == 0:
             embed.add_field(name="Advancements", value="No advancement data available.", inline=False)

        await ctx.send(embed=embed)
    else:
        await ctx.send("No advancement data available.")

async def playtimelist_command(ctx, bot):
    """Show playtimes for all players."""
    await ctx.message.add_reaction('🕒')

    playtime_data = get_all_playtimes() # Already sorted highest to lowest

    if playtime_data:
        embed = discord.Embed(
            title="Playtime Counts",
            description="All player playtimes (highest to lowest)",
            color=discord.Color.green()
        )

        # Paginate
        value_str = ""
        char_count = 0
        page = 1
        total_players = len(playtime_data)
        players_on_page = 0
        max_chars = 1000

        for mc_name, _, seconds in playtime_data:
            line = f"{mc_name}: {format_playtime(seconds)}\n"
            if char_count + len(line) > max_chars and players_on_page > 0:
                 embed.add_field(name=f"Playtime (Page {page})", value=f"```{value_str}```", inline=False)
                 value_str = line
                 char_count = len(line)
                 players_on_page = 1
                 page += 1
            else:
                 value_str += line
                 char_count += len(line)
                 players_on_page += 1

        if value_str:
             embed.add_field(name=f"Playtime (Page {page})", value=f"```{value_str}```", inline=False)

        if total_players == 0:
             embed.add_field(name="Playtime", value="No playtime data available.", inline=False)

        await ctx.send(embed=embed)
    else:
        await ctx.send("No playtime data available.")


async def currentstats_command(ctx, bot):
    """Displays stats accumulated for the current day and current week."""
    await ctx.message.add_reaction('📊')
    logger.info(f"Current stats command triggered by {ctx.author}")

    try:
        # Get Today's Stats (period_days=1 includes only today based on new logic)
        today_stats = get_stats_for_period(1) # Use 1 day period for today

        # Get This Week's Stats (Sunday to Now, est based)
        now_est = datetime.datetime.now(pytz.est)
        # What day is it? (0=Mon, 6=Sun) -> We want Sunday as start (day 6)
        # days_since_sunday = now_est.weekday() + 1 if now_est.weekday() != 6 else 0 # Incorrect calculation
        days_since_sunday = (now_est.weekday() + 1) % 7 # Correct: Mon=1, Tue=2... Sun=0 -> days since last Sun

        start_of_week_est = now_est - datetime.timedelta(days=days_since_sunday)
        start_date_str = start_of_week_est.strftime("%Y-%m-%d")
        end_date_str = now_est.strftime("%Y-%m-%d") # Today

        logger.debug(f"Fetching week stats from {start_date_str} to {end_date_str}")

        # Query specifically for the week range (Sun-Now)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT minecraft_username,
                   SUM(deaths) as total_deaths,
                   SUM(advancements) as total_advancements,
                   SUM(playtime_seconds) as total_playtime
            FROM stats_history
            WHERE date BETWEEN ? AND ?
            GROUP BY minecraft_username
        ''', (start_date_str, end_date_str))
        week_stats = cursor.fetchall()
        conn.close()


        # --- Create Embed ---
        embed = discord.Embed(
            title="Current Activity Stats",
            color=discord.Color.purple(),
            timestamp=datetime.datetime.now(pytz.est)
        )
        embed.set_footer(text="Stats since last midnight est / last Sunday midnight est")

        # --- Format Today's Stats ---
        today_active = [s for s in today_stats if s[1] > 0 or s[2] > 0 or s[3] > 0]
        if today_active:
            today_active.sort(key=lambda x: x[3], reverse=True) # Sort by playtime today
            # Limit display length if necessary
            today_lines = [f"• **`{s[0]}`**: {s[1]}💀 {s[2]}⭐ {format_playtime(s[3])}🕒"
                                   for s in today_active[:15]] # Show top 15 active today
            today_str = "\n".join(today_lines)
            if len(today_str) > 1020: # Trim if too long for embed field
                 today_str = today_str[:1017] + "..."

            embed.add_field(name="☀️ Today's Activity (est)", value=today_str or "No activity recorded yet today.", inline=False)
        else:
            embed.add_field(name="☀️ Today's Activity (est)", value="No activity recorded yet today.", inline=False)

        # --- Format Week's Stats ---
        week_active = [s for s in week_stats if s[1] > 0 or s[2] > 0 or s[3] > 0]
        if week_active:
            # Sort by overall activity score for the week
            def activity_score(stats): return stats[3] + (stats[2] * 60) + (stats[1] * 30)
            week_active.sort(key=activity_score, reverse=True)

            week_lines = [f"• **`{s[0]}`**: {s[1]}💀 {s[2]}⭐ {format_playtime(s[3])}🕒"
                                  for s in week_active[:15]] # Show top 15 active this week
            week_str = "\n".join(week_lines)
            if len(week_str) > 1020: # Trim if too long
                 week_str = week_str[:1017] + "..."

            embed.add_field(name=f"📅 This Week's Activity (Since {start_date_str} est)", value=week_str or "No activity recorded yet this week.", inline=False)
        else:
             embed.add_field(name=f"📅 This Week's Activity (Since {start_date_str} est)", value="No activity recorded yet this week.", inline=False)


        await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in currentstats command: {e}", exc_info=True) # Log traceback
        await ctx.send("An error occurred while fetching current stats. Please check the logs.")
import discord
from discord.ext import commands, tasks
import re
import subprocess
import random
import asyncio
import datetime
import logging

# Import from our modules
from const import (
    DATABASE_PATH, ROLES, ONLINE_ROLE_NAME, WEBHOOK_CHANNEL_ID, MOD_ROLE_ID,
    SCOREBOARD_CHANNEL_ID, DEATH_MARKER, ADVANCEMENT_MARKER, LOG_CHANNEL_ID,
    WHITELIST_ROLE_ID, WEEKLY_RANKINGS_CHANNEL_ID
)
from database.queries import (
    initialize_database, record_death, record_advancement, record_login,
    record_logout, get_player_stats, clear_online_players, save_daily_stats, 
    get_stats_for_period, get_all_deaths, get_all_advancements, get_all_playtimes, get_connection
)
from utils.discord_helpers import (
    get_discord_user, get_player_display_names, get_minecraft_from_discord,
    get_discord_from_minecraft
)
from utils.formatters import format_playtime
from commands.player_stats import (
    deaths_command, advancements_command, playtime_command,
    deathlist_command, advancementlist_command, playtimelist_command
)
from commands.admin import updateroles_command, addhistory_command, whitelist_command
from tasks.leaderboard import leaderboard_update_task
from tasks.roles import (
    add_online_role, remove_online_role, clear_all_online_roles, role_update_task,
    update_achievement_roles
)

from utils.logging import setup_logging

# Initialize bot with required intents
intents = discord.Intents.default()
intents.message_content = True  # For reading message content
intents.members = True  # For accessing member info
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables
server_online = False
online_players = []
logger = None
discord_handler = None

# Daily stats summary task
@tasks.loop(hours=24)
async def daily_stats_summary():
    """Post daily stats summary and save current stats."""
    global logger
    
    try:
        # First, save today's stats snapshot
        save_daily_stats()
        
        stats_channel_id = WEEKLY_RANKINGS_CHANNEL_ID
        
        channel = bot.get_channel(stats_channel_id)
        if not channel:
            logger.warning(f"Could not find stats channel with ID {stats_channel_id}")
            return
        
        # Get yesterday's date
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Connect to DB
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get stats specifically for yesterday
        cursor.execute('''
        SELECT minecraft_username, deaths, advancements, playtime_seconds
        FROM stats_history
        WHERE date = ?
        ''', (yesterday,))
        
        daily_stats = cursor.fetchall()
        conn.close()
        
        if not daily_stats or len(daily_stats) == 0:
            logger.info("No daily stats to report")
            await channel.send("No player activity to report for yesterday.")
            return
        
        # Filter out players with no activity
        active_players = [stats for stats in daily_stats if stats[1] > 0 or stats[2] > 0 or stats[3] > 0]
        
        if not active_players:
            logger.info("No active players yesterday")
            await channel.send("No player activity to report for yesterday.")
            return
        
        # Create embed
        embed = discord.Embed(
            title="📊 Daily Stats Summary",
            description=f"Player activity for {yesterday}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        
        # Most deaths
        most_deaths = sorted(active_players, key=lambda x: x[1], reverse=True)
        if most_deaths and most_deaths[0][1] > 0:
            deaths_str = "\n".join([f"{idx+1}. {stats[0]}: {stats[1]} deaths" 
                                  for idx, stats in enumerate(most_deaths[:3]) if stats[1] > 0])
            embed.add_field(name="💀 Most Deaths", value=deaths_str or "No deaths yesterday", inline=False)
        
        # Most advancements
        most_advancements = sorted(active_players, key=lambda x: x[2], reverse=True)
        if most_advancements and most_advancements[0][2] > 0:
            adv_str = "\n".join([f"{idx+1}. {stats[0]}: {stats[2]} advancements" 
                               for idx, stats in enumerate(most_advancements[:3]) if stats[2] > 0])
            embed.add_field(name="⭐ Most Advancements", value=adv_str or "No advancements yesterday", inline=False)
        
        # Most playtime
        most_playtime = sorted(active_players, key=lambda x: x[3], reverse=True)
        if most_playtime and most_playtime[0][3] > 0:
            playtime_str = "\n".join([f"{idx+1}. {stats[0]}: {format_playtime(stats[3])}" 
                                    for idx, stats in enumerate(most_playtime[:3]) if stats[3] > 0])
            embed.add_field(name="🕒 Most Playtime", value=playtime_str or "No playtime recorded yesterday", inline=False)
        
        # Most active player overall (weighted score: playtime + advancements*60 + deaths*30)
        def activity_score(stats):
            return stats[3] + (stats[2] * 60) + (stats[1] * 30)
        
        most_active = sorted(active_players, key=activity_score, reverse=True)
        if most_active:
            mvp = most_active[0][0]
            embed.add_field(name="🏆 Most Active Player", value=f"**{mvp}**", inline=False)
        
        await channel.send(embed=embed)
        logger.info("Posted daily stats summary")
        
    except Exception as e:
        logger.error(f"Error in daily stats summary: {e}")

@daily_stats_summary.before_loop
async def before_daily_stats():
    """Wait until the bot is ready."""
    await bot.wait_until_ready()
    
    # Calculate time until next run (set to run at 00:05 each day)
    now = datetime.datetime.now()
    future = now.replace(hour=0, minute=5, second=0)
    if now.hour >= 0 and now.minute > 5:  # If already past midnight
        future += datetime.timedelta(days=1)
    
    await asyncio.sleep((future - now).seconds)

# Weekly stats task
@tasks.loop(hours=168)  # 7 days * 24 hours
async def weekly_stats_summary():
    """Post weekly stats summary using saved stats."""
    global logger
    
    try:
        stats_channel_id = WEEKLY_RANKINGS_CHANNEL_ID
        
        channel = bot.get_channel(stats_channel_id)
        if not channel:
            logger.warning(f"Could not find stats channel with ID {stats_channel_id}")
            return
        
        # Date range for past week
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        
        # Connect to DB
        conn = get_connection()
        cursor = conn.cursor()
        
        # Aggregate stats for the past week
        cursor.execute('''
        SELECT minecraft_username, 
               SUM(deaths) as total_deaths, 
               SUM(advancements) as total_advancements,
               SUM(playtime_seconds) as total_playtime
        FROM stats_history
        WHERE date BETWEEN ? AND ?
        GROUP BY minecraft_username
        ''', (start_date, end_date))
        
        weekly_stats = cursor.fetchall()
        conn.close()
        
        if not weekly_stats or len(weekly_stats) == 0:
            logger.info("No weekly stats to report")
            await channel.send("No player activity to report for this week.")
            return
        
        # Filter out players with no activity
        active_players = [stats for stats in weekly_stats if stats[1] > 0 or stats[2] > 0 or stats[3] > 0]
        
        if not active_players:
            logger.info("No active players this week")
            await channel.send("No player activity to report for this week.")
            return
        
        # Create embed
        embed = discord.Embed(
            title="📊 Weekly Stats Summary",
            description=f"Player activity for the week {start_date} to {end_date}",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.now()
        )
        
        # Most deaths
        most_deaths = sorted(active_players, key=lambda x: x[1], reverse=True)
        if most_deaths and most_deaths[0][1] > 0:
            deaths_str = "\n".join([f"{idx+1}. {stats[0]}: {stats[1]} deaths" 
                                  for idx, stats in enumerate(most_deaths[:5]) if stats[1] > 0])
            embed.add_field(name="💀 Most Deaths", value=deaths_str or "No deaths this week", inline=False)
        
        # Most advancements
        most_advancements = sorted(active_players, key=lambda x: x[2], reverse=True)
        if most_advancements and most_advancements[0][2] > 0:
            adv_str = "\n".join([f"{idx+1}. {stats[0]}: {stats[2]} advancements" 
                               for idx, stats in enumerate(most_advancements[:5]) if stats[2] > 0])
            embed.add_field(name="⭐ Most Advancements", value=adv_str or "No advancements this week", inline=False)
        
        # Most playtime
        most_playtime = sorted(active_players, key=lambda x: x[3], reverse=True)
        if most_playtime and most_playtime[0][3] > 0:
            playtime_str = "\n".join([f"{idx+1}. {stats[0]}: {format_playtime(stats[3])}" 
                                    for idx, stats in enumerate(most_playtime[:5]) if stats[3] > 0])
            embed.add_field(name="🕒 Most Playtime", value=playtime_str or "No playtime recorded this week", inline=False)
        
        # Most active player overall (weighted score)
        def activity_score(stats):
            return stats[3] + (stats[2] * 60) + (stats[1] * 30)
        
        most_active = sorted(active_players, key=activity_score, reverse=True)
        if most_active:
            mvp_stats = most_active[0]
            mvp = mvp_stats[0]
            embed.add_field(name="🏆 Player of the Week", 
                          value=f"**{mvp}**\n"
                                f"• {mvp_stats[1]} deaths\n"
                                f"• {mvp_stats[2]} advancements\n"
                                f"• {format_playtime(mvp_stats[3])} played", 
                          inline=False)
        
        await channel.send(embed=embed)
        logger.info("Posted weekly stats summary")
        
    except Exception as e:
        logger.error(f"Error in weekly stats summary: {e}")

@weekly_stats_summary.before_loop
async def before_weekly_stats():
    """Wait until the bot is ready."""
    await bot.wait_until_ready()
    
    # Calculate time until next run (set to run at 00:15 on Sundays)
    now = datetime.datetime.now()
    days_until_sunday = (6 - now.weekday()) % 7  # Sunday is 6
    future = now.replace(hour=0, minute=15, second=0) + datetime.timedelta(days=days_until_sunday)
    if now.weekday() == 6 and now.hour >= 0 and now.minute > 15:  # If already past Sunday midnight
        future += datetime.timedelta(days=7)
    
    await asyncio.sleep((future - now).seconds)

# Dead bots for henry and bear
def run_idle_bots():
    subprocess.Popen(["python", "run_bear.py"])
    subprocess.Popen(["python", "run_henry.py"])
    # Add trading bot
    subprocess.Popen(["python", "trading_bot.py"])

# Bot event handlers
@bot.event
async def on_ready():
    """When bot is ready, initialize everything."""
    global logger, discord_handler
    
    # Set up logging
    logger, discord_handler = setup_logging(bot, LOG_CHANNEL_ID)
    discord_handler.set_ready(True)
    
    logger.info(f'Bot is ready! Logged in as {bot.user}')
    run_idle_bots()
    
    # Initialize database
    initialize_database()
    
    # Set initial status
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is currently offline."))
    
    # Start background tasks
    bot.loop.create_task(leaderboard_update_task(bot))
    bot.loop.create_task(role_update_task(bot))
    daily_stats_summary.start()  # Start the daily stats task
    weekly_stats_summary.start() # Start the weekly stats task
    
    logger.info("Bot initialization complete!")

@bot.event
async def on_message(message):
    """Handle incoming messages."""
    global server_online, online_players, logger
    
    # Ignore own messages
    if message.author == bot.user:
        return
    
    # Debug logging for webhook messages
    if message.channel.id == WEBHOOK_CHANNEL_ID:
        logger.debug(f"Webhook message received: {message.content}")
    
    # Check if it's in the webhook channel
    if message.channel.id == WEBHOOK_CHANNEL_ID:
        # Server status messages
        if ":white_check_mark: **Server has started**" in message.content:
            server_online = True
            # await message.add_reaction('✅')
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is online! (0 players)"))
            logger.info("Server has started!")
            
        elif ":octagonal_sign: **Server has stopped**" in message.content:
            server_online = False
            # await message.add_reaction('🛑')
            
            # Update playtime for all online players
            clear_online_players()
            online_players = []
            
            # Clear online roles
            for guild in bot.guilds:
                await clear_all_online_roles(guild)
            
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is currently offline."))
            logger.info("Server has stopped!")
            
        # Player join - check for both bold and plain text formats
        elif " joined the server" in message.content:
            logger.debug(f"Join message detected: {message.content}")

            match = re.search(r"\*\*(.*?)\*\* joined the server", message.content)
            if not match:
                match = re.search(r"(.*?) joined the server", message.content)

            if match:
                # Properly clean the extracted username
                minecraft_username = re.sub(r"\\(.)", r"\1", match.group(1))
                await message.add_reaction('✅')

                logger.debug(f"Extracted username: {minecraft_username}")
                
                # Check if player exists in database instead of MINECRAFT_TO_DISCORD
                player_stats = get_player_stats(minecraft_username=minecraft_username)
                if player_stats:
                    discord_username = player_stats[1]  # discord_username is second column
                    
                    # Record login
                    record_login(minecraft_username)
                    online_players.append(minecraft_username)
                    
                    # Add online role
                    for guild in bot.guilds:
                        member = get_discord_user(bot, discord_username)
                        if member:
                            await add_online_role(member)
                    
                    # Update bot status
                    discord_display_names = get_player_display_names(online_players, message.guild)
                    status_text = f" {len(discord_display_names)} player(s) online: {', '.join(discord_display_names)}"
                    if len(status_text) > 100:  # If too long, simplify
                        status_text = f"Online: {len(discord_display_names)} players"

                    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
                    logger.info(f"{minecraft_username} joined the server")
                else:
                    await message.add_reaction('❓')
                    logger.warning(f"Unknown player joined: {minecraft_username}")
            else:
                logger.error("Could not extract username from join message")
        
        # Player leave - check for both bold and plain text formats
        elif " left the server" in message.content:
            logger.debug(f"Leave message detected: {message.content}")
            
            # Try bold format first (from markdown)
            match = re.search(r"\*\*(.*?)\*\* left the server", message.content)
            if not match:
                # Try plain text format
                match = re.search(r"(.*?) left the server", message.content)
            
            if match:
                minecraft_username = match.group(1).replace("\\", "")  # Remove escape chars
                await message.add_reaction('👋')
                
                logger.debug(f"Extracted username: {minecraft_username}")
                
                # Check if player exists in database
                player_stats = get_player_stats(minecraft_username=minecraft_username)
                if player_stats:
                    discord_username = player_stats[1]  # discord_username is second column
                    
                    # Record logout
                    record_logout(minecraft_username)
                    if minecraft_username in online_players:
                        online_players.remove(minecraft_username)
                    
                    # Remove online role
                    for guild in bot.guilds:
                        member = get_discord_user(bot, discord_username)
                        if member:
                            await remove_online_role(member)
                    
                    # Update bot status
                    discord_display_names = get_player_display_names(online_players, message.guild)
                    if discord_display_names:
                        status_text = f" {len(discord_display_names)} player(s) online: {', '.join(discord_display_names)}"
                        if len(status_text) > 100:
                            status_text = f"Online: {len(discord_display_names)} players"
                        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=status_text))
                    else:
                        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Server is online. Join now!"))
                    
                    logger.info(f"{minecraft_username} left the server")
                else:
                    await message.add_reaction('❓')
                    logger.warning(f"Unknown player left: {minecraft_username}")
            else:
                logger.error("Could not extract username from leave message")
        
        # Death messages - also check for both formats
        elif message.content.startswith(DEATH_MARKER) or DEATH_MARKER in message.content:
            # Adjust this pattern based on your actual death message format
            match = re.search(f"{DEATH_MARKER} (.*?)(?:\s+\[.*?\])? (died|was|got|fell)", message.content)
            
            if match:
                minecraft_username = re.sub(r"\\(.)", r"\1", match.group(1))
                await message.add_reaction('🇱')  # Regional indicator L emoji
                
                # Debug output to see what username we're actually extracting
                logger.debug(f"Death detected for username: '{minecraft_username}'")
                
                # Check if player exists in database
                player_stats = get_player_stats(minecraft_username=minecraft_username)
                if player_stats:
                    record_death(minecraft_username)
                    logger.info(f"{minecraft_username} died")
                else:
                    await message.add_reaction('❓')
                    logger.warning(f"Unknown player died: {message.content}")
                
                # Send a random death message
                death_messages = [
                        f"And the award for 'Most Creative Way to Lose All Your Items' goes to **{minecraft_username}**...",
                        f"Your gravestone should just read 'Oops' at this point, **{minecraft_username}**.",
                        f"I'm sure your items are happier wherever they are now.",
                        f"Maybe try surviving next time, **{minecraft_username}**?",
                        f"Another beautiful contribution to the respawn button usage statistics.",
                        f"That was definitely the game's fault. Definitely.",
                        f"I guess those diamonds really wanted their freedom, huh **{minecraft_username}**?",
                        f"Taking the express route back to spawn, I see.",
                        f"Your death was... inspirational. For the mobs, anyway.",
                        f"How thoughtful of you to donate all your items to the void.",
                        f"The respawn screen missed you. Glad you two could reunite.",
                        f"Your coordinates have been noted as 'places not to go'.",
                        f"That was certainly... a choice.",
                        f"Amazing how quickly you turn experience points into disappointment.",
                        f"Your items are throwing a farewell party without you, **{minecraft_username}**.",
                        f"I see you've chosen the dramatic exit. Again.",
                        f"**{minecraft_username}** thought they could fly. They were wrong.",
                        f"Just made a generous donation to the item despawn fund.",
                        f"Decided their inventory was too cluttered anyway.",
                        f"Testing the respawn mechanics. For science, of course.",
                        f"Found an exciting new way to return to spawn.",
                        f"Has completed their speedrun to the death screen.",
                        f"Taking an unscheduled break from existing.",
                        f"Thought their armor was just for decoration.",
                        f"Discovered that actions have consequences.",
                        f"Conducting gravity research. Results inconclusive.",
                        f"Just demonstrated what not to do.",
                        f"Perfected the art of item scattering.",
                        f"Made their items available for public collection.",
                        f"Should consider a career that doesn't involve survival.",
                        f"Contributing to the mob kill count statistics. Again.",
                        f"Just rage-quit life.",
                        f"Found out the hard way.",
                        f"Has chosen death as today's activity.",
                        f"Taking the scenic route back to spawn.",
                        f"Apparently thought that was a good idea.",
                        f"Successfully failed. An impressive feat, really.",
                        f"Experiencing technical difficulties. Please stand by.",
                        f"Went to extraordinary lengths to lose all their progress.",
                        f"Clearly needed more practice.",
                        f"Was overcome by a sudden case of not being alive anymore.",
                        f"Demonstrating how not to play Minecraft.",
                        f"Decided to personally check the respawn system.",
                        f"Having an unplanned inventory reset.",
                        f"Should reconsider their life choices. Or death choices.",
                        f"Just helped the server clear some item lag. How generous.",
                        f"That was so pathetic, even the dirt you fell on is ashamed to be associated with you.",
                        f"How does it feel knowing the only thing you’re good at is disappointing everyone?",
                        f"Every time you die, the concept of intelligence takes permanent damage.",
                        f"That was so embarrassing, even the respawn screen is tired of seeing you.",
                        f"Death doesn’t even want you. It just has no choice but to clean up your failures.",
                        f"If stupidity was a speedrun category, you’d be the world record holder.",
                        f"Nothing in this world is more consistent than your ability to ruin everything.",
                        f"Your ability to fail is honestly impressive. Too bad it's the only skill you have.",
                        f"At this point, even your own shadow would rather disassociate from you.",
                        f"Congratulations, you’ve turned dying into a full-time job.",
                        f"Keep this up and the game is going to start preloading the death screen for you.",
                        f"You don’t even deserve a death message. Just quit. Just leave.",
                        f"Watching you play is like watching a train derail in slow motion, except somehow worse.",
                        f"If there was an IQ test for playing this game, you wouldn’t even qualify for the tutorial.",
                        f"Every time you respawn, the world collectively sighs in disappointment.",
                        f"Nothing has ever been wasted as much as the oxygen you’re using up right now.",
                        f"The sheer lack of talent is almost fascinating. Almost.",
                        f"Somehow, the only thing more fragile than your ego is your ability to stay alive.",
                        f"One day, failure might stop following you around. But today is not that day.",
                        f"Your life expectancy in this game is lower than my expectations for you, and those were already rock bottom.",
                        f"You’ve been here for five minutes and I already regret every moment of it.",
                        f"It’s almost impressive how you manage to be wrong in every possible way.",
                        f"The only thing you’ve mastered is finding new ways to embarrass yourself.",
                        f"The world isn’t against you. It’s just watching you lose a fight against yourself.",
                        f"If survival was a multiple-choice question, you’d still somehow pick the wrong answer.",
                        f"The only thing more tragic than your gameplay is the fact that you keep coming back.",
                        f"You couldn’t make it through this game even if you had creative mode.",
                        f"That was so bad, the game should uninstall itself out of pure secondhand embarrassment.",
                        f"Maybe try thinking before acting? Or is that asking too much?",
                        f"Watching paint dry is more exciting than whatever this mess is.",
                        f"You are the reason respawn exists, but honestly, it shouldn’t bother anymore.",
                        f"If failure was an art form, you'd be the Mona Lisa of disappointment.",
                        f"I would say 'get good,' but honestly, that ship sailed a long time ago.",
                        f"You don’t even need enemies when your worst opponent is yourself.",
                        f"Even a random number generator would have better survival instincts than you.",
                        f"The concept of evolution just reversed itself watching that disaster unfold.",
                        f"There is literally no excuse for how unbelievably bad that was.",
                        f"If you were a mob, you'd be the one everyone farms for free loot.",
                        f"The only thing you’ve built in this game is a solid reputation for being terrible.",
                        f"Even the game itself is questioning why you’re still here.",
                        f"Death shouldn’t be this easy, yet here you are proving otherwise.",
                        f"There’s a difference between having bad luck and being the bad luck.",
                        f"This game has thousands of mechanics, and yet you haven’t mastered a single one.",
                        f"If common sense was a stat, yours would be in the negative.",
                        f"You should probably craft a boat, because you've clearly sunk to a new low.",
                        f"Every second you exist in this world is an insult to basic survival instincts.",
                        f"You’ve set a new record for making the worst possible decisions in the shortest amount of time.",
                        f"Your gameplay is proof that some people just aren’t meant to succeed.",
                        f"Survival is a simple concept. Somehow, you’ve managed to misunderstand it entirely.",
                        f"There’s a fine line between being unlucky and being a walking disaster. You obliterated that line.",
                        f"If failure was a potion, you'd be the splash version—affecting everything around you.",
                        f"If brains were durability, yours would have broken a long time ago.",
                        f"The only real danger here is your own inability to function properly.",
                        f"Every time you die, the void whispers ‘not this idiot again.’",
                        f"This isn’t a learning curve, it’s a straight drop off a cliff, just like you.",
                        f"At this point, the respawn button should just be a permanent part of your screen.",
                        f"Out of all possible outcomes, you still somehow manage to choose the worst one.",
                        f"The fact that you thought you’d survive that is the funniest joke of all.",
                        f"You just took 'trial and error' and removed the trial part completely.",
                        f"The only thing more painful than watching this is the thought of you trying again."
                    ]
                await message.channel.send(random.choice(death_messages))

        
        # Inside your advancement message handler
        elif message.content.startswith(ADVANCEMENT_MARKER) or ADVANCEMENT_MARKER in message.content:
            match = re.search(f"{ADVANCEMENT_MARKER} (.*?) has made the advancement", message.content)
            
            if match:
                minecraft_username = re.sub(r"\\(.)", r"\1", match.group(1))
                
                await message.add_reaction(ADVANCEMENT_MARKER)
                
                # Check if player exists in database
                player_stats = get_player_stats(minecraft_username=minecraft_username)
                if player_stats:
                    record_advancement(minecraft_username)
                    logger.info(f"{minecraft_username} got an advancement")
                else:
                    await message.add_reaction('❓')
                    logger.warning(f"Unknown player got advancement: {minecraft_username}")
    
    # Handle playerlist command when server is offline
    if not server_online and message.content.strip() == "playerlist":
        await message.add_reaction('❌')
        await message.channel.send("You can't use this command right now, the server is down.")
    
    # Process commands
    await bot.process_commands(message)

# Stats summary command
@bot.command(name="statssummary")
async def statssummary_cmd(ctx, period="daily", channel_id=None):
    """Post a stats summary or set the stats channel."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await ctx.message.add_reaction('✅')
    
    if channel_id:
        try:
            channel_id = int(channel_id)
            channel = bot.get_channel(channel_id)
            if not channel:
                await ctx.send(f"Could not find channel with ID {channel_id}")
                return
            
            # Store channel ID for future use
            bot.stats_channel_id = channel_id
            await ctx.send(f"Stats channel set to {channel.mention}")
            return
        except ValueError:
            await ctx.send("Invalid channel ID. Please provide a numeric ID.")
            return
    
    # Trigger appropriate summary based on requested period
    if period.lower() == "daily":
        # Run the daily summary task outside its schedule
        await daily_stats_summary()
        await ctx.send("Daily stats summary posted!")
    elif period.lower() == "weekly":
        # Run the weekly summary task outside its schedule
        await weekly_stats_summary()
        await ctx.send("Weekly stats summary posted!")
    else:
        await ctx.send("Invalid period. Use 'daily' or 'weekly'.")

# Command registrations
@bot.command(name="deaths")
async def deaths_cmd(ctx, username=None):
    await deaths_command(ctx, bot, username)

@bot.command(name="advancements")
async def advancements_cmd(ctx, username=None):
    await advancements_command(ctx, bot, username)

@bot.command(name="playtime")
async def playtime_cmd(ctx, username=None):
    await playtime_command(ctx, bot, username)

@bot.command(name="deathlist")
async def deathlist_cmd(ctx):
    await deathlist_command(ctx, bot)

@bot.command(name="advancementlist")
async def advancementlist_cmd(ctx):
    await advancementlist_command(ctx, bot)

@bot.command(name="playtimelist")
async def playtimelist_cmd(ctx):
    await playtimelist_command(ctx, bot)

@bot.command(name="updateroles")
async def updateroles_cmd(ctx):
    await updateroles_command(ctx, bot)

@bot.command(name="addhistory")
async def addhistory_cmd(ctx, subcommand=None, arg=None, *args):
    await addhistory_command(ctx, bot, subcommand, arg, *args)

@bot.command(name="whitelist")
async def whitelist_cmd(ctx, discord_user=None, minecraft_user=None):
    await whitelist_command(ctx, bot, discord_user, minecraft_user)

# Run the bot
if __name__ == "__main__":
    with open('token.txt', 'r') as f:
        TOKEN = f.readline().strip()
    bot.run(TOKEN)

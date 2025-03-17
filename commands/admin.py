import discord
import asyncio
from const import MOD_ROLE_ID, MINECRAFT_TO_DISCORD
from database.queries import get_all_players, bulk_update_history, delete_player, add_player, get_player_stats
from utils.discord_helpers import get_discord_user
from tasks.roles import update_achievement_roles

async def updateroles_command(ctx, bot):
    """Update achievement roles manually."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await update_achievement_roles(bot, ctx.guild)
    await ctx.message.add_reaction('✅')

async def addhistory_command(ctx, bot, subcommand=None, arg=None, *args):
    """Add or update player history with various subcommands.
    
    Subcommands:
    - bulk: Start interactive bulk update mode
    - get USERNAME: Get history for a specific player
    - USERNAME key=value [key=value ...]: Update specific values for a player
    - delete USERNAME: Delete a player from the database
    """
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await ctx.message.add_reaction('✅')
    
    # Handle delete subcommand
    if subcommand and subcommand.lower() == "delete" and arg:
        player_stats = get_player_stats(minecraft_username=arg)
        if player_stats:
            success = delete_player(arg)
            if success:
                await ctx.send(f"Successfully deleted player {arg} from the database.")
            else:
                await ctx.send(f"Error deleting player {arg}.")
        else:
            await ctx.send(f"Player {arg} not found in the database.")
        return
    
    # Handle get subcommand
    elif subcommand and subcommand.lower() == "get" and arg:
        player_stats = get_player_stats(minecraft_username=arg)
        if player_stats:
            mc_username, disc_username, deaths, advancements, playtime = player_stats
            embed = discord.Embed(
                title=f"Player History: {mc_username}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Discord Username", value=disc_username or "Not linked", inline=False)
            embed.add_field(name="Deaths", value=str(deaths), inline=True)
            embed.add_field(name="Advancements", value=str(advancements), inline=True)
            embed.add_field(name="Playtime", value=f"{playtime} seconds", inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Player {arg} not found in the database.")
        return
    
    # Handle bulk subcommand
    elif subcommand and subcommand.lower() == "bulk":
        await handle_bulk_update(ctx, bot)
        return
    
    # Handle direct update (username key=value)
    elif subcommand:
        # In this case, subcommand is the username
        username = subcommand
        player_stats = get_player_stats(minecraft_username=username)
        if not player_stats:
            await ctx.send(f"Player {username} not found in the database.")
            return
        
        # Combine arg and args into a single list
        all_args = [arg] if arg else []
        all_args.extend(args)
        
        if not all_args:
            await ctx.send("Please provide at least one key=value pair to update.")
            return
        
        # Parse key=value pairs
        updates = {username: {}}
        for kv in all_args:
            if '=' not in kv:
                await ctx.send(f"Invalid format: {kv}. Use key=value format.")
                continue
            
            key, value = kv.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            try:
                value = int(value)
                updates[username][key] = value
            except ValueError:
                await ctx.send(f"Invalid value for {key}: {value}. Must be a number.")
                continue
        
        # Apply updates
        if updates[username]:
            success = bulk_update_history(updates)
            if success:
                await ctx.send(f"Successfully updated history for {username}!")
            else:
                await ctx.send("Error updating history. Check logs for details.")
        else:
            await ctx.send("No valid updates provided.")
        return
    
    # Display help if no subcommand provided
    else:
        embed = discord.Embed(
            title="Player History Command",
            description="Usage instructions:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Subcommands",
            value=(
                "**!addhistory bulk**\n"
                "Start interactive bulk update mode\n\n"
                "**!addhistory get USERNAME**\n"
                "Get history for a specific player\n\n"
                "**!addhistory USERNAME key=value [key=value ...]**\n"
                "Update specific values for a player\n\n"
                "**!addhistory delete USERNAME**\n"
                "Delete a player from the database"
            ),
            inline=False
        )
        await ctx.send(embed=embed)

async def handle_bulk_update(ctx, bot):
    """Handle the bulk update flow for addhistory command."""
    # Get current stats
    players = get_all_players()
    
    embed = discord.Embed(
        title="Bulk Player History Update",
        description="Current values for all players. Reply with changes to update.",
        color=discord.Color.blue()
    )
    
    # Format instructions
    instructions = """
To update values, reply with a message in this format:
```
username1: deaths=5, advancements=10, playtime=3600
username2: deaths=2, advancements=15, playtime=7200
```
- You can update one or more values for one or more players
- 'username' should be the Minecraft username
- 'playtime' is in seconds
"""
    embed.add_field(name="Instructions", value=instructions, inline=False)
    
    # Format current values and split if too long
    def add_embed_fields(embed, name, content):
        chunks = [content[i:i + 1000] for i in range(0, len(content), 1000)]
        for index, chunk in enumerate(chunks):
            embed.add_field(name=f"{name} (Part {index + 1})" if len(chunks) > 1 else name, value=f"```{chunk}```", inline=False)

    # Format current values
    current_values = "\n".join(f"{mc_username}: deaths={deaths}, advancements={advancements}, playtime={playtime}"
                            for mc_username, _, deaths, advancements, playtime in players)

    add_embed_fields(embed, "Current Values", current_values)
    
    await ctx.send(embed=embed)
    
    # Wait for response
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        response = await bot.wait_for('message', check=check, timeout=300)  # 5 minute timeout
        
        # Parse response
        updates = {}
        lines = response.content.strip().split('\n')
        
        for line in lines:
            if ':' not in line:
                continue
                
            username, data_str = line.split(':', 1)
            username = username.strip()
            
            # Check if username exists in database
            player_stats = get_player_stats(minecraft_username=username)
            if not player_stats:
                await ctx.send(f"Unknown username: {username}")
                continue
                
            updates[username] = {}
            
            data_parts = data_str.strip().split(',')
            for part in data_parts:
                part = part.strip()
                if '=' not in part:
                    continue
                
                key, value = part.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                try:
                    value = int(value)
                    updates[username][key] = value
                except ValueError:
                    await ctx.send(f"Invalid value for {key}: {value}")
        
        # Apply updates
        success = bulk_update_history(updates)
        
        if success:
            await ctx.send(f"Successfully updated history for {len(updates)} players!")
        else:
            await ctx.send("Error updating history. Check logs for details.")
            
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for response.")

async def whitelist_command(ctx, bot, discord_user=None, minecraft_user=None):
    """Whitelist a player by adding them to the database and giving them the whitelist role."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    # Check for required parameters
    if not discord_user or not minecraft_user:
        await ctx.send("Both Discord user and Minecraft username are required. Format: !whitelist DISCORD_USER MINECRAFT_USER")
        return
    
    await ctx.message.add_reaction('✅')
    
    # Find the Discord user
    member = get_discord_user(bot, discord_user)
    
    if not member:
        await ctx.send(f"Could not find Discord user {discord_user}")
        return
    
    # Add player to database
    success = add_player(minecraft_user, discord_user)
    
    if not success:
        await ctx.send(f"Error adding player {minecraft_user} to database.")
        return
    
    # Add whitelist role
    try:
        from const import WHITELIST_ROLE_ID
        whitelist_role = ctx.guild.get_role(WHITELIST_ROLE_ID)
        if whitelist_role:
            await member.add_roles(whitelist_role)
            await ctx.send(f"Added {member.mention} to the whitelist with Minecraft username {minecraft_user}!")
        else:
            await ctx.send(f"Could not find whitelist role. User has been added to the database, but the role was not assigned.")
    except Exception as e:
        await ctx.send(f"Error assigning role: {str(e)}. The user has been added to the database but the role was not assigned.")

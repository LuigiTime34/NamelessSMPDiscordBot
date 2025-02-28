import discord
import asyncio
from const import MOD_ROLE_ID, MINECRAFT_TO_DISCORD
from database.queries import get_all_players, bulk_update_history
from tasks.roles import update_achievement_roles

async def updateroles_command(ctx, bot):
    """Update achievement roles manually."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await ctx.message.add_reaction('✅')
    
    await update_achievement_roles(bot, ctx.guild)
    await ctx.send("Roles have been updated!")

async def addhistory_command(ctx, bot):
    """Add or update player history."""
    # Check if user has mod role
    if not any(role.id == MOD_ROLE_ID for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.")
        return
    
    await ctx.message.add_reaction('✅')
    
    # Get current stats
    players = get_all_players()
    
    embed = discord.Embed(
        title="Player History",
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
    
    # Format current values
    current_values = "```\n"
    for mc_username, disc_username, deaths, advancements, playtime in players:
        current_values += f"{mc_username}: deaths={deaths}, advancements={advancements}, playtime={playtime}\n"
    current_values += "```"
    
    # Split long content into multiple fields if needed
    def add_embed_fields(embed, name, content):
        chunks = [content[i:i + 1000] for i in range(0, len(content), 1000)]
        for index, chunk in enumerate(chunks):
            embed.add_field(name=f"{name} (Part {index + 1})" if len(chunks) > 1 else name, value=f"```{chunk}```", inline=False)

    # Format current values and split if too long
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
            
            if username not in MINECRAFT_TO_DISCORD:
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
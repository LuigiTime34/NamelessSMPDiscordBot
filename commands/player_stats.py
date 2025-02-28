import discord
from discord.ext import commands
from database.queries import (
    get_player_stats, get_all_deaths, get_all_advancements, get_all_playtimes,
    get_minecraft_from_discord
)
from utils.formatters import format_playtime

class PlayerStats(commands.Cog):
    def __init__(self, bot, minecraft_to_discord):
        self.bot = bot
        self.minecraft_to_discord = minecraft_to_discord
        
    def get_player_minecraft_username(self, ctx, username=None):
        """Helper method to determine which Minecraft player to show stats for."""
        minecraft_username = None
        
        if username:
            # Check if direct Minecraft username
            if username in self.minecraft_to_discord:
                minecraft_username = username
            else:
                # Try to find by Discord name
                for mc_name, disc_name in self.minecraft_to_discord.items():
                    if disc_name.lower() == username.lower():
                        minecraft_username = mc_name
                        break
        else:
            # Use command author
            author_name = ctx.author.name
            minecraft_username = get_minecraft_from_discord(author_name, self.minecraft_to_discord)
        
        return minecraft_username

    @commands.command(name="deaths")
    async def deaths_command(self, ctx, username=None):
        """Show death count for a player."""
        
        minecraft_username = self.get_player_minecraft_username(ctx, username)
        
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

    @commands.command(name="advancements")
    async def advancements_command(self, ctx, username=None):
        """Show advancement count for a player."""
        
        minecraft_username = self.get_player_minecraft_username(ctx, username)
        
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

    @commands.command(name="playtime")
    async def playtime_command(self, ctx, username=None):
        """Show playtime for a player."""
        
        minecraft_username = self.get_player_minecraft_username(ctx, username)
        
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

    @commands.command(name="deathlist")
    async def deathlist_command(self, ctx):
        """Show death counts for all players."""
        
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

    @commands.command(name="advancementlist")
    async def advancementlist_command(self, ctx):
        """Show advancement counts for all players."""
        
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

    @commands.command(name="playtimelist")
    async def playtimelist_command(self, ctx):
        """Show playtimes for all players."""
        
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

def setup(bot, minecraft_to_discord):
    """Setup function to add cog to bot."""
    bot.add_cog(PlayerStats(bot, minecraft_to_discord))
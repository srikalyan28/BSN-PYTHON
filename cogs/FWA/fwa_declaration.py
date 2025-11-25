import discord
from discord.ext import commands
from discord import app_commands
from utils.coc_api import coc_api

class FWADeclarationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="fwa", description="Declare FWA War Result (Win/Lose)")
    @app_commands.describe(clan_tag="The Clan Tag (e.g. #ABC123)", result="The War Result", ping_role="Optional role to ping")
    @app_commands.choices(result=[
        app_commands.Choice(name="Win", value="Win"),
        app_commands.Choice(name="Lose", value="Lose")
    ])
    async def fwa(self, interaction: discord.Interaction, clan_tag: str, result: str, ping_role: discord.Role = None):
        await interaction.response.defer()
        
        # Fetch Clan Details
        clan = await coc_api.get_clan(clan_tag)
        
        if not clan:
            await interaction.followup.send(f"❌ Could not find clan with tag `{clan_tag}`.", ephemeral=True)
            return

        clan_name = clan.name
        clan_logo = clan.badge.url if clan.badge else None

        if result == "Win":
            embed = discord.Embed(
                title=f"🏆 We WIN against {clan_name} 🏆",
                description=f"**Instructions:**\n"
                            "✅ **Score 150 Stars**\n"
                            "✅ Attack for loot and stars!\n"
                            "✅ Ensure all bases are cleared if needed.",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"War WIN declared by {interaction.user.display_name} 🟢")
        else:
            embed = discord.Embed(
                title=f"⚠️ We LOSE against {clan_name} ⚠️",
                description=f"**Instructions:**\n"
                            "🛑 **Score ONLY 2 Stars on Mirror**\n"
                            "🛑 **DO NOT exceed 100 Stars** total score.\n"
                            "🛑 Maintain strict discipline.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"War LOSE declared by {interaction.user.display_name} 🔴")

        if clan_logo:
            embed.set_thumbnail(url=clan_logo)
        
        content = ping_role.mention if ping_role else None
        await interaction.followup.send(content=content, embed=embed)

async def setup(bot):
    await bot.add_cog(FWADeclarationCog(bot))

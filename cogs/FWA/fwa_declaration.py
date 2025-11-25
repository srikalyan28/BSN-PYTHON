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
                            "✅ **(A)Attack On Your Mirror For 3 stars\n**"
                            "✅ (B)Attack On Base 1 For 1 Star(After Our Number 1 Has Taken Its Mirror\n"
                            "✅ Last 12 Hours, All Bases Will Be Open For 3 Stars\n"
                            "✅ Don’t Fill CC And 150⭐️fwa_declaration",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"War WIN declared by {interaction.user.display_name} 🟢")
        else:
            embed = discord.Embed(
                title=f"⚠️ We LOSE against {clan_name} ⚠️",
                description=f"**Instructions:**\n"
                            "🛑 **(A)Attack On Your Mirror For 2 Stars\n**"
                            "🛑 **(B)Attack On Base 1 For 1 Star(After Our Number 1 Has Taken Its Mirrior\n**"
                            "🛑 Last 12 Hours, All Bases Will Be Open For 2 Stars.\n"
                            "🛑 Don’t Fill CC And 100⭐️",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"War LOSE declared by {interaction.user.display_name} 🔴")

        if clan_logo:
            embed.set_thumbnail(url=clan_logo)
        
        content = ping_role.mention if ping_role else None
        await interaction.followup.send(content=content, embed=embed)

async def setup(bot):
    await bot.add_cog(FWADeclarationCog(bot))

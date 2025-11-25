import discord
from discord.ext import commands
from discord import app_commands
from utils.mongo_manager import mongo_manager
from utils.embed_utils import create_invite_embed, create_rejection_embed
import os

class AdminCommandsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="invite_player", description="Send a clan invitation to a player.")
    @app_commands.describe(member="The player to invite", clan_tag="The tag of the clan to invite to")
    async def invite_player(self, interaction: discord.Interaction, member: discord.Member, clan_tag: str):
        # Check permissions (optional, but good practice)
        # if not interaction.user.guild_permissions.manage_guild: ...
        
        # Fetch clan details
        clans = await mongo_manager.get_clans()
        clan = next((c for c in clans if c['clan_tag'] == clan_tag.upper()), None)
        
        if not clan:
            await interaction.response.send_message(f"Clan with tag {clan_tag} not found.", ephemeral=True)
            return

        embed = create_invite_embed(
            clan_name=clan['name'],
            leader_id=clan.get('leader_id'),
            leadership_role_id=clan.get('leadership_role_id'),
            logo_url=clan.get('logo_url'),
            inviter_mention=interaction.user.mention
        )
        
        button = discord.ui.Button(label="Join Clan", style=discord.ButtonStyle.link, url=clan.get('clan_link', 'https://clashofclans.com'))
        view = discord.ui.View()
        view.add_item(button)
        
        await interaction.response.send_message(content=f"Clan Invitation for {member.mention}", embed=embed, view=view)

    @app_commands.command(name="reject_player", description="Send a rejection message to a player.")
    @app_commands.describe(member="The player to reject")
    async def reject_player(self, interaction: discord.Interaction, member: discord.Member):
        embed = create_rejection_embed("Blackspire Nation", member.id)
        await interaction.response.send_message(content=member.mention, embed=embed)

    @invite_player.autocomplete('clan_tag')
    async def clan_tag_autocomplete(self, interaction: discord.Interaction, current: str):
        clans = await mongo_manager.get_clans()
        return [
            app_commands.Choice(name=c['name'], value=c['clan_tag'])
            for c in clans if current.lower() in c['name'].lower() or current.lower() in c['clan_tag'].lower()
        ][:25]

async def setup(bot):
    await bot.add_cog(AdminCommandsCog(bot))

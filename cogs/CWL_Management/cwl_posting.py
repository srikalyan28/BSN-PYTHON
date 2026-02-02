import discord
from discord import app_commands
from discord.ext import commands
from .cwl_models import cwl_models
from .cwl_permissions import cwl_permissions
from .cwl_utils import cwl_utils
from utils.mongo_manager import mongo_manager

async def setup(bot):
    await bot.add_cog(CWLPostingCog(bot))

class CWLPostingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    post_group = app_commands.Group(name="post", description="CWL Posting Commands")

    @post_group.command(name="cwl-overview", description="Post ALL Clans Overview (Owner Only)")
    async def post_overview(self, interaction: discord.Interaction):
        if not cwl_permissions.is_owner(interaction):
            await interaction.response.send_message("❌ Access Denied: Owner only.", ephemeral=True)
            return

        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("No active season.", ephemeral=True)
            return

        assignments = await cwl_models.get_assignments(season['season'])
        if not assignments:
            await interaction.response.send_message("No assignments found for this season.", ephemeral=True)
            return

        # Group by Source
        grouped = {}
        for a in assignments:
            src = a.get("source_clan", "Unknown")
            if src not in grouped: grouped[src] = []
            grouped[src].append(a)

        output = f"**CWL OVERVIEW - {season['season']}**\n\n"
        output += cwl_utils.format_overview(grouped)

        # Discord Message Length Limit is 2000.
        # If output > 2000, we need to split.
        if len(output) > 2000:
            # Simple chunking
            chunks = [output[i:i+1900] for i in range(0, len(output), 1900)]
            for chunk in chunks:
                await interaction.channel.send(chunk)
            await interaction.response.send_message("✅ Posted overview.", ephemeral=True)
        else:
            await interaction.response.send_message(output) # Plain text

    @post_group.command(name="clan-cwl", description="Post Clan Specific CWL Details")
    async def post_clan_cwl(self, interaction: discord.Interaction):
        # Access: Leader, Rep, Owner
        if not (cwl_permissions.is_owner(interaction) or 
                cwl_permissions.is_leader_or_co(interaction) or 
                await cwl_permissions.is_rep(interaction, (await cwl_models.get_active_season())['season'] if await cwl_models.get_active_season() else None)):
            
            await interaction.response.send_message("❌ Access Denied.", ephemeral=True)
            return
            
        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("No active season.", ephemeral=True)
            return

        # Determine Manageable Clans
        clans = await mongo_manager.get_clans()
        manageable_clans = []
        
        if cwl_permissions.is_owner(interaction):
            manageable_clans = clans
        elif cwl_permissions.is_leader_or_co(interaction):
             # Leader can access all because "Auto-detect" logic assumes selection for now.
             manageable_clans = clans
        else:
            # Check Rep status
            # Filter clans where user is rep
            for c in clans:
                reps = await cwl_models.get_reps(season['season'], c['clan_tag'])
                if interaction.user.id in reps:
                    manageable_clans.append(c)
        
        if not manageable_clans:
            await interaction.response.send_message("You are not assigned as a Rep for any clan this season.", ephemeral=True)
            return

        view = PostClanSelectView(manageable_clans, season['season'])
        await interaction.response.send_message(f"Select Clan to post CWL Details for **{season['season']}**:", view=view, ephemeral=True)


class PostClanSelectView(discord.ui.View):
    def __init__(self, clans, season):
        super().__init__(timeout=60)
        options = []
        for c in clans[:25]:
            options.append(discord.SelectOption(label=c['name'], value=c['name'])) # Filter by Name as assignments use Name? 
            # Wait, Assignments use "dest_clan". Did we store Tag or Name in cwl_models assignments?
            # Model: "dest_clan" -> String.
            # Management Modal: User typed "Destination Clan Name". 
            # So we should match by NAME or verify standard.
            # If user typed "Clan A", we query dest_clan="Clan A".
            # So value here should be Name.
        
        self.add_item(PostClanSelect(options, season))

class PostClanSelect(discord.ui.Select):
    def __init__(self, options, season):
        super().__init__(placeholder="Select Clan...", options=options)
        self.season = season

    async def callback(self, interaction: discord.Interaction):
        clan_name = self.values[0]
        
        assignments = await cwl_models.get_assignments(self.season, dest_clan=clan_name)
        if not assignments:
             await interaction.response.send_message(f"No assignments found for **{clan_name}**.", ephemeral=True)
             return

        # Check for link? get from 'clans' via mongo?
        # We only have Name here. Need to find Tag to get Link?
        # Let's hope Clan Name is unique enough or we do a reverse lookup.
        # For plain text output, link is optional helper.
        
        output = cwl_utils.format_clan_details(clan_name, assignments)
        await interaction.channel.send(output)
        await interaction.response.send_message("✅ Posted details.", ephemeral=True)

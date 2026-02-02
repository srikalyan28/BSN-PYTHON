import discord
from discord import app_commands
from discord.ext import commands
from .cwl_models import cwl_models
from .cwl_permissions import cwl_permissions
from .cwl_utils import cwl_utils
from utils.mongo_manager import mongo_manager
import traceback

async def setup(bot):
    await bot.add_cog(CWLForumCog(bot))

class CWLForumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    cwl_group = app_commands.Group(name="cwl", description="CWL Management System")

    @cwl_group.command(name="forum", description="Fill CWL Forum for your clan")
    async def cwl_forum(self, interaction: discord.Interaction):
        # 1. Permission Check
        if not cwl_permissions.is_leader_or_co(interaction):
            await interaction.response.send_message("You do not have permission (Leader/Co-Leader) to use this.", ephemeral=True)
            return

        # 2. Get Active Season
        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("No active CWL Season found. Ask a Manager to set one.", ephemeral=True)
            return
        
        season_name = season['season']

        # 3. Select Clan
        # Fetch all clans
        clans = await mongo_manager.get_clans()
        if not clans:
            await interaction.response.send_message("No clans found in database.", ephemeral=True)
            return

        # Simple "Auto-detect" logic: 
        # If user has a role that matches a clan name? 
        # Or just let them select. A select menu is safest.
        view = CWLForumClanSelectView(clans, season_name)
        await interaction.response.send_message(f"Select the clan for **{season_name}** CWL Forum:", view=view, ephemeral=True)

class CWLForumClanSelectView(discord.ui.View):
    def __init__(self, clans, season_name):
        super().__init__(timeout=60)
        self.season_name = season_name
        
        options = []
        # Limit to 25
        for clan in clans[:25]:
            options.append(discord.SelectOption(
                label=clan['name'],
                value=clan['clan_tag'],
                description=clan.get('clan_tag', '')
            ))
            
        self.add_item(CWLForumClanSelect(options))

class CWLForumClanSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Choose a clan...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        collection_view = self.view
        clan_tag = self.values[0]
        clan_name = [opt.label for opt in self.options if opt.value == clan_tag][0]
        
        # Open Modal
        # Pre-fill? Maybe fetch existing forum data if any
        existing_forum = await cwl_models.get_forum(collection_view.season_name, clan_tag)
        
        modal = CWLForumModal(collection_view.season_name, clan_tag, clan_name, existing_forum)
        await interaction.response.send_modal(modal)

class CWLForumModal(discord.ui.Modal):
    def __init__(self, season, clan_tag, clan_name, existing_data=None):
        super().__init__(title=f"{clan_name} - {season}")
        self.season = season
        self.clan_tag = clan_tag
        
        default_goal = existing_data.get('goal', '') if existing_data else ''
        default_master = existing_data.get('master', '') if existing_data else ''
        default_league = existing_data.get('league', '') if existing_data else ''
        default_format = existing_data.get('format', '') if existing_data else ''
        default_help = existing_data.get('help_needed', '') if existing_data else ''

        self.goal = discord.ui.TextInput(label="Clan CWL Goal", placeholder="Promotion / Hold / Casual", default=default_goal, required=True)
        self.master = discord.ui.TextInput(label="Who is leading CWL?", placeholder="Username / IGN", default=default_master, required=True)
        self.league = discord.ui.TextInput(label="CWL League", placeholder="Champs / Masters / Crystal...", default=default_league, required=True)
        self.format = discord.ui.TextInput(label="Format", placeholder="15v15 or 30v30", default=default_format, required=True)
        self.help_needed = discord.ui.TextInput(label="Help Needed (TH + Count)", placeholder="e.g., TH16 x 2, TH15 x 1", style=discord.TextStyle.paragraph, default=default_help, required=False)

        self.add_item(self.goal)
        self.add_item(self.master)
        self.add_item(self.league)
        self.add_item(self.format)
        self.add_item(self.help_needed)

    async def on_submit(self, interaction: discord.Interaction):
        data = {
            "goal": self.goal.value,
            "master": self.master.value,
            "league": self.league.value,
            "format": self.format.value,
            "help_needed": self.help_needed.value
        }
        
        await cwl_models.save_forum(self.season, self.clan_tag, data)
        await interaction.response.send_message(
            f"✅ **{self.title}** Forum Saved!\n"
            f"**Goal**: {self.goal.value}\n"
            f"**Master**: {self.master.value}\n"
            f"**Format/League**: {self.format.value} ({self.league.value})",
            ephemeral=True
        )

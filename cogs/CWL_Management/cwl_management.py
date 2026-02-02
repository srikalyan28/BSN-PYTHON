import discord
from discord import app_commands
from discord.ext import commands
from .cwl_models import cwl_models
from .cwl_permissions import cwl_permissions
from .cwl_utils import cwl_utils
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import typing

async def setup(bot):
    await bot.add_cog(CWLManagementCog(bot))

class CWLManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    cwl = app_commands.Group(name="cwl", description="CWL Management")
    manager_group = app_commands.Group(name="manager", description="Manage CWL Managers", parent=cwl)

    @cwl.command(name="management", description="Open CWL Management Panel (Managers Only)")
    async def management_panel(self, interaction: discord.Interaction):
        if not await cwl_permissions.is_manager(interaction):
            await interaction.response.send_message("❌ Access Denied: CWL Manager/Owner only.", ephemeral=True)
            return

        embed = discord.Embed(title="CWL Management Panel", description="Select an action below.", color=discord.Color.blue())
        view = CWLManagementView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @manager_group.command(name="add", description="Add a CWL Manager (User or Role)")
    async def manager_add(self, interaction: discord.Interaction, user: typing.Optional[discord.User], role: typing.Optional[discord.Role]):
        if not cwl_permissions.is_owner(interaction):
            await interaction.response.send_message("❌ Access Denied: Owner only.", ephemeral=True)
            return
        
        if not user and not role:
            await interaction.response.send_message("Please provide a User or Role.", ephemeral=True)
            return

        if user: await cwl_models.add_manager(user_id=user.id)
        if role: await cwl_models.add_manager(role_id=role.id)
        
        await interaction.response.send_message(f"✅ Added {user.mention if user else role.mention} as CWL Manager.", ephemeral=True)

    @manager_group.command(name="remove", description="Remove a CWL Manager (User or Role)")
    async def manager_remove(self, interaction: discord.Interaction, user: typing.Optional[discord.User], role: typing.Optional[discord.Role]):
        if not cwl_permissions.is_owner(interaction):
            await interaction.response.send_message("❌ Access Denied: Owner only.", ephemeral=True)
            return

        if user: await cwl_models.remove_manager(user_id=user.id)
        if role: await cwl_models.remove_manager(role_id=role.id)
        
        await interaction.response.send_message(f"✅ Removed {user.mention if user else role.mention} from CWL Managers.", ephemeral=True)


class CWLManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Season Setup", style=discord.ButtonStyle.primary, row=0)
    async def season_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SeasonSetupModal())

    @discord.ui.button(label="Manage Reps", style=discord.ButtonStyle.secondary, row=1)
    async def manage_reps(self, interaction: discord.Interaction, button: discord.ui.Button):
        clans = await mongo_manager.get_clans()
        view = SelectClanForRepView(clans)
        await interaction.response.send_message("Select Clan to manage Reps for:", view=view, ephemeral=True)

    @discord.ui.button(label="Manual Assignment", style=discord.ButtonStyle.success, row=1)
    async def manual_assignment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ManualAssignmentModal())

class SeasonSetupModal(discord.ui.Modal, title="Set Active Season"):
    season_name = discord.ui.TextInput(label="Season Name", placeholder="e.g. February 2026")
    
    async def on_submit(self, interaction: discord.Interaction):
        await cwl_models.set_active_season(self.season_name.value)
        await interaction.response.send_message(f"✅ Active Season set to: **{self.season_name.value}**", ephemeral=True)

class ManualAssignmentModal(discord.ui.Modal, title="Assign Player to CWL Clan"):
    player_tag = discord.ui.TextInput(label="Player Tag", placeholder="#TAG")
    source_clan = discord.ui.TextInput(label="Source Clan Name", placeholder="Origin Clan")
    dest_clan = discord.ui.TextInput(label="Destination Clan Name", placeholder="Target CWL Clan")

    async def on_submit(self, interaction: discord.Interaction):
        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("No active season.", ephemeral=True)
            return
        
        player = await coc_api.get_player(self.player_tag.value)
        if not player:
            await interaction.response.send_message("INVALID TAG.", ephemeral=True)
            return

        await cwl_models.add_assignment(
            season['season'], 
            player.tag, 
            self.source_clan.value, 
            self.dest_clan.value, 
            player.town_hall,
            player.name
        )
        await interaction.response.send_message(f"✅ Assigned **{player.name}** (TH{player.town_hall}) from {self.source_clan.value} -> {self.dest_clan.value}", ephemeral=True)

class SelectClanForRepView(discord.ui.View):
    def __init__(self, clans):
        super().__init__()
        options = [discord.SelectOption(label=c['name'], value=c['clan_tag'], description=c['clan_tag']) for c in clans[:25]]
        self.add_item(RepClanSelect(options))

class RepClanSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Select Clan...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        season = await cwl_models.get_active_season()
        if not season:
            await interaction.response.send_message("No active season.", ephemeral=True)
            return

        clan_tag = self.values[0]
        reps = await cwl_models.get_reps(season['season'], clan_tag)
        rep_text = ", ".join([f"<@{uid}>" for uid in reps]) if reps else "None"
        
        embed = discord.Embed(title=f"Reps for {self.values[0]}", description=f"Current Reps: {rep_text}")
        view = RepManageView(season['season'], clan_tag)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class RepManageView(discord.ui.View):
    def __init__(self, season, clan_tag):
        super().__init__()
        self.season = season
        self.clan_tag = clan_tag
        self.add_item(discord.ui.UserSelect(placeholder="Select Users to ADD/REMOVE", max_values=5))

    @discord.ui.button(label="ADD Selected", style=discord.ButtonStyle.green)
    async def add_reps(self, interaction: discord.Interaction, button: discord.ui.Button):
        select = [x for x in self.children if isinstance(x, discord.ui.UserSelect)][0]
        if not select.values:
            await interaction.response.send_message("No users selected.", ephemeral=True)
            return
        
        added = []
        for user in select.values:
            await cwl_models.add_rep(self.season, self.clan_tag, user.id)
            added.append(user.name)
        await interaction.response.send_message(f"Added reps: {', '.join(added)}", ephemeral=True)

    @discord.ui.button(label="REMOVE Selected", style=discord.ButtonStyle.red)
    async def remove_reps(self, interaction: discord.Interaction, button: discord.ui.Button):
        select = [x for x in self.children if isinstance(x, discord.ui.UserSelect)][0]
        if not select.values:
            await interaction.response.send_message("No users selected.", ephemeral=True)
            return

        removed = []
        for user in select.values:
            await cwl_models.remove_rep(self.season, self.clan_tag, user.id)
            removed.append(user.name)
        await interaction.response.send_message(f"Removed reps: {', '.join(removed)}", ephemeral=True)

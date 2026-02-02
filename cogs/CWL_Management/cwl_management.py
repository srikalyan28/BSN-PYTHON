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

    cwl = app_commands.Group(name="cwl-admin", description="CWL Administration")
    manager_group = app_commands.Group(name="manager", description="Manage CWL Managers", parent=cwl)
    shell_group = app_commands.Group(name="shell", description="Manage Shell Clans", parent=cwl)

    @cwl.command(name="panel", description="Open CWL Management Panel")
    async def panel(self, interaction: discord.Interaction):
        if not await cwl_permissions.is_manager(interaction):
            await interaction.response.send_message("❌ Managers only.", ephemeral=True)
            return
        
        season = await cwl_models.get_active_season()
        embed = discord.Embed(title="CWL Admin Panel", description=f"Season: **{season['season'] if season else 'None'}**", color=discord.Color.red())
        view = AdminPanelView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # --- SHELL CLANS COMMANDS ---
    @shell_group.command(name="add", description="Add a Shell Clan")
    async def shell_add(self, interaction: discord.Interaction, name: str, tag: str):
        if not await cwl_permissions.is_manager(interaction): return
        await cwl_models.add_shell_clan(name, tag.upper())
        await interaction.response.send_message(f"✅ Added Shell Clan: {name} ({tag})", ephemeral=True)

    @shell_group.command(name="list", description="List Shell Clans")
    async def shell_list(self, interaction: discord.Interaction):
        if not await cwl_permissions.is_manager(interaction): return
        shells = await cwl_models.get_shell_clans()
        msg = "\n".join([f"{s['name']} ({s['tag']})" for s in shells]) if shells else "None"
        await interaction.response.send_message(f"**Shell Clans**:\n{msg}", ephemeral=True)

    # --- MANAGER COMMANDS ---
    @manager_group.command(name="add")
    async def m_add(self, i, user: typing.Optional[discord.User], role: typing.Optional[discord.Role]):
        if not cwl_permissions.is_owner(i): await i.response.send_message("Owner only", ephemeral=True); return
        if user: await cwl_models.add_manager(user_id=user.id)
        if role: await cwl_models.add_manager(role_id=role.id)
        await i.response.send_message("✅ Added Manager", ephemeral=True)

    @manager_group.command(name="remove")
    async def m_rem(self, i, user: typing.Optional[discord.User], role: typing.Optional[discord.Role]):
        if not cwl_permissions.is_owner(i): await i.response.send_message("Owner only", ephemeral=True); return
        if user: await cwl_models.remove_manager(user_id=user.id)
        if role: await cwl_models.remove_manager(role_id=role.id)
        await i.response.send_message("✅ Removed Manager", ephemeral=True)


class AdminPanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="Season Setup", style=discord.ButtonStyle.primary, row=0)
    async def season(self, i, b): await i.response.send_modal(SeasonModal())

    @discord.ui.button(label="Allocations / Allotments", style=discord.ButtonStyle.success, row=1)
    async def allotments(self, i, b):
        season = await cwl_models.get_active_season()
        if not season: await i.response.send_message("No Active Season", ephemeral=True); return
        
        reqs = await cwl_models.get_requirements(season['season'])
        clan_tags = list(set([r['clan_tag'] for r in reqs]))
        
        if not clan_tags:
            await i.response.send_message("No requests found.", ephemeral=True)
            return

        all_clans = await mongo_manager.get_clans()
        options = []
        for tag in clan_tags:
            c = next((x for x in all_clans if x['clan_tag'] == tag), None)
            name = c['name'] if c else tag
            options.append(discord.SelectOption(label=name, value=tag))
        
        await i.response.send_message("Select Target Clan (Need Help):", view=AllocationTargetView(season['season'], options), ephemeral=True)

    @discord.ui.button(label="📢 Release Notifications", style=discord.ButtonStyle.danger, row=2)
    async def release(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Notify all clans with allotments
        season = await cwl_models.get_active_season()
        if not season: return
        
        # We need to find all clans that received players
        # Query Overflows where status='allotted'
        # Group by dest (allotted_to_tag)
        allotted = await cwl_models.get_overflows(season['season'], status='allotted')
        dest_tags = list(set([a.get('allotted_to_tag') for a in allotted if a.get('allotted_to_tag')]))
        
        if not dest_tags:
             await interaction.response.send_message("No allotments to release.", ephemeral=True)
             return
             
        await interaction.response.defer(ephemeral=True)
        count = 0
        
        clans = await mongo_manager.get_clans()
        
        for tag in dest_tags:
            clan = next((c for c in clans if c['clan_tag'] == tag), None)
            if not clan: continue
            
            # Find Leadership Channel
            channel_id = clan.get('leadership_channel_id')
            if not channel_id:
                # Try finding channel by name/forum? No, must use configured channel.
                # Fallback to general channel logic or skip? User said "ask... so bot can send messages in right clan leaders chat".
                continue
                
            channel = interaction.guild.get_channel(int(channel_id))
            if not channel: continue
            
            # Ping Leadership Role
            role_id = clan.get('leadership_role_id')
            role_ping = f"<@&{role_id}>" if role_id else "@here"
            
            # Send Message
            try:
                await channel.send(f"📢 {role_ping} **CWL Allotments Released!**\nPlease check your roster adjustments.")
                count += 1
            except:
                pass
        
        await interaction.followup.send(f"✅ Notifications sent to {count} clans.", ephemeral=True)



class SeasonModal(discord.ui.Modal, title="Set Season"):
    name = discord.ui.TextInput(label="Season Name", placeholder="February 2026")
    async def on_submit(self, i): 
        await cwl_models.set_active_season(self.name.value)
        await i.response.send_message(f"✅ Season Set: {self.name.value}", ephemeral=True)


class AllocationTargetView(discord.ui.View):
    def __init__(self, season, options):
        super().__init__()
        self.season = season
        self.add_item(AllocationTargetSelect(season, options))

class AllocationTargetSelect(discord.ui.Select):
    def __init__(self, season, options):
        super().__init__(placeholder="Select Clan to Fill...", options=options)
        self.season = season
    
    async def callback(self, interaction: discord.Interaction):
        clan_tag = self.values[0]
        # Show Requirements Dashboard for this Clan
        reqs = await cwl_models.get_requirements(self.season, clan_tag)
        # reqs: [{th_level, count_needed, count_allotted}]
        
        # Sort by TH
        reqs.sort(key=lambda x: x['th_level'], reverse=True)
        
        embed = discord.Embed(title=f"Allocations for {clan_tag}", color=discord.Color.blue())
        for r in reqs:
            needed = r.get('count_needed', 0)
            allotted = r.get('count_allotted', 0)
            remaining = needed - allotted
            embed.add_field(name=f"TH {r['th_level']}", value=f"Need: {needed} | Filled: {allotted} | **Open: {remaining}**", inline=False)
        
        view = AllocationActionView(self.season, clan_tag, reqs)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class AllocationActionView(discord.ui.View):
    def __init__(self, season, clan_tag, reqs):
        super().__init__()
        self.season = season
        self.clan_tag = clan_tag
        
        # Add buttons for each TH constraint
        for r in reqs:
            remaining = r.get('count_needed', 0) - r.get('count_allotted', 0)
            style = discord.ButtonStyle.secondary
            if remaining > 0: style = discord.ButtonStyle.success
            
            # Button for "Fill TH{X}"
            # Using custom_id to pass data is cleaner but limited length.
            # Using partial?
            self.add_item(FillTHButton(r['th_level'], self.season, self.clan_tag))

class FillTHButton(discord.ui.Button):
    def __init__(self, th, season, clan_tag):
        super().__init__(label=f"Fill TH{th}", style=discord.ButtonStyle.primary)
        self.th = th
        self.season = season
        self.clan_tag = clan_tag

    async def callback(self, interaction: discord.Interaction):
        # 1. Query Overflows (Available, TH >= self.th)
        overflows = await cwl_models.get_overflows(self.season, status="available", min_th=self.th)
        
        if not overflows:
            await interaction.response.send_message(f"No available overflows found for TH{self.th}+.", ephemeral=True)
            return

        # Create Select Menu of Players
        # Format: "Name (TH{th}) - SourceClan"
        options = []
        for p in overflows[:25]: # Limit 25
            options.append(discord.SelectOption(
                label=f"{p['player_name']} (TH{p['player_th']})",
                value=p['player_tag'],
                description=f"From: {p.get('source_clan', 'Unknown')}"
            ))
        
        view = PlayerSelectView(self.season, self.clan_tag, self.th, options)
        await interaction.response.send_message(f"Select players to allot to **{self.clan_tag}** (Slot: TH{self.th}):", view=view, ephemeral=True)

class PlayerSelectView(discord.ui.View):
    def __init__(self, season, target_clan, slot_th, options):
        super().__init__()
        self.add_item(PlayerAllotSelect(season, target_clan, slot_th, options))

class PlayerAllotSelect(discord.ui.Select):
    def __init__(self, season, target_clan, slot_th, options):
        super().__init__(placeholder="Select Players to Allot...", min_values=1, max_values=len(options), options=options)
        self.season = season
        self.target_clan = target_clan
        self.slot_th = slot_th

    async def callback(self, interaction: discord.Interaction):
        # Allot selected players
        selected_tags = self.values
        count = len(selected_tags)
        
        # Lookups needed? We need names for confirmation, but we can trust values
        for tag in selected_tags:
            # Update Overflow Status
            await cwl_models.update_overflow_status(self.season, tag, "allotted", self.target_clan)
            
            # Add to proper assignments table?
            # cwl_models has 'add_assignment'. We should likely use that too for easy query?
            # Or just query Overflows. 'get_assignments' in older model queried that table.
            # Let's keep data in `cwl_overflows` as master logic, but maybe update `cwl_assignments` for legacy viewing?
            # User prompt implied "he can select... and save the allotment".
            # Upgrading: we are filling a `slot_th` requirement.
            pass
        
        # Update Requirements Count
        await cwl_models.increment_allotted_count(self.season, self.target_clan, self.slot_th, amount=count)

        await interaction.response.send_message(f"✅ Allotted {count} players to {self.target_clan}.", ephemeral=True)

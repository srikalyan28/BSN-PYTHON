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
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

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
        
        # New Logic: Notify Source Clans about PENDING Allocations (slots assigned, not filled)
        # Query pending allocations
        pendings = await cwl_models.get_pending_allocations(season['season'])
        source_tags = list(set([p['source_clan'] for p in pendings if p['status'] == 'pending']))

        if not source_tags:
             await interaction.response.send_message("No pending slot allocations to notify.", ephemeral=True)
             return
             
        await interaction.response.defer(ephemeral=True)
        count = 0
        clans = await mongo_manager.get_clans() + await cwl_models.get_shell_clans() # Shells usually don't have channels
        
        for tag in source_tags:
            clan = next((c for c in clans if c.get('clan_tag') == tag or c.get('tag') == tag), None)
            if not clan: continue
            
            channel_id = clan.get('leadership_channel_id') or (await cwl_models.get_forum_metadata(season['season'], tag) or {}).get('channel_id')
            
            if not channel_id: continue
            channel = interaction.guild.get_channel(int(channel_id))
            if not channel: continue
            
            role_id = clan.get('leadership_role_id')
            role_ping = f"<@&{role_id}>" if role_id else "@here"
            
            try:
                await channel.send(f"📢 {role_ping} **CWL Action Required**\nYou have been assigned slots to fill. Run `/cwl allotment` in your forum channel.")
                count += 1
            except: pass
        
        await interaction.followup.send(f"✅ Notifications sent to {count} clans.", ephemeral=True)

    @discord.ui.button(label="Review Submissions", style=discord.ButtonStyle.primary, row=2)
    async def review(self, interaction: discord.Interaction, button: discord.ui.Button):
        season = await cwl_models.get_active_season()
        if not season: return
        
        # Get 'filled' allocations (Leaders submitted)
        all_pending = await cwl_models.get_pending_allocations(season['season'])
        filled = [p for p in all_pending if p.get('status') == 'filled']
        
        if not filled:
            await interaction.response.send_message("No submissions waiting for review.", ephemeral=True)
            return
            
        view = ReviewSubmissionsView(season['season'], filled)
        await interaction.response.send_message(f"found {len(filled)} submissions to review.", view=view, ephemeral=True)

class ReviewSubmissionsView(discord.ui.View):
    def __init__(self, season, items):
        super().__init__()
        for p in items:
            self.add_item(ReviewButton(season, p))

class ReviewButton(discord.ui.Button):
    def __init__(self, season, alloc):
        label = f"{alloc['source_clan']} -> {alloc['target_clan']} (TH{alloc['th_level']})"
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.season = season; self.alloc = alloc
    
    async def callback(self, i):
        # Approve
        # 1. Update Pending Status -> approved
        await cwl_models.approve_allocation(self.season, self.alloc['source_clan'], self.alloc['target_clan'], self.alloc['th_level'])
        
        # 2. Update Overflows (reserved -> allotted)
        tags = self.alloc.get('players', [])
        for tag in tags:
            await cwl_models.update_overflow_status(self.season, tag, "allotted", allotted_to_tag=self.alloc['target_clan'])
            
        # 3. Update Requirements (Count Allotted)
        # Note: We already incremented 'count_allotted' in requirements when we assigned the SLOT.
        # So we don't need to increment again.
        
        self.disabled = True
        self.label += " (Approved)"
        await i.response.edit_message(view=self.view)
        await i.followup.send(f"✅ Approved move of {len(tags)} players.", ephemeral=True)



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
        # 1. Query Overflows (Grouped by Source)
        overflows = await cwl_models.get_overflows(self.season, status="available", min_th=self.th)
        
        if not overflows:
            await interaction.response.send_message(f"No available overflows found for TH{self.th}+.", ephemeral=True)
            return

        # Group by Source Clan
        sources = {}
        for p in overflows:
            src = p.get('source_clan', 'Unknown')
            sources[src] = sources.get(src, 0) + 1
        
        # Select Source Clan
        options = []
        all_clans = await mongo_manager.get_clans() + await cwl_models.get_shell_clans()
        
        for src, count in sources.items():
            if src == self.clan_tag: continue # Can't fill self
            c = next((x for x in all_clans if x.get('clan_tag') == src or x.get('tag') == src), None)
            name = c['name'] if c else src
            options.append(discord.SelectOption(
                label=f"{name} ({count} available)",
                value=src,
                description=f"Can provide TH{self.th}"
            ))

        view = SourceSelectView(self.season, self.clan_tag, self.th, options)
        await interaction.response.send_message(f"Select Source Clan to fill **TH{self.th}** for **{self.clan_tag}**:", view=view, ephemeral=True)

class SourceSelectView(discord.ui.View):
    def __init__(self, season, target_clan, th, options):
        super().__init__()
        self.add_item(SourceSelect(season, target_clan, th, options))

class SourceSelect(discord.ui.Select):
    def __init__(self, season, target_clan, th, options):
        super().__init__(placeholder="Select Source Clan...", options=options)
        self.season = season; self.target = target_clan; self.th = th
    
    async def callback(self, i):
        src = self.values[0]
        # Modal for Count
        await i.response.send_modal(SlotCountModal(self.season, src, self.target, self.th))

class SlotCountModal(discord.ui.Modal, title="Assign Slot Count"):
    count = discord.ui.TextInput(label="Number of players to move", placeholder="e.g. 2")
    def __init__(self, season, src, target, th):
        super().__init__()
        self.season = season; self.src = src; self.target = target; self.th = th

    async def on_submit(self, i):
        try:
            qty = int(self.count.value)
            # Create Pending Allocation
            await cwl_models.add_pending_allocation(self.season, self.src, self.target, self.th, qty)
            # Also update Requirement count (count allocated) for target clan immediate? 
            # Or wait for filled?
            # User wants admin to see "Filled" slots. We should increment "allotted" in requirements so Admin knows they did their job.
            await cwl_models.increment_allotted_count(self.season, self.target, self.th, amount=qty)
            
            await i.response.send_message(f"✅ Assigned **{qty}x TH{self.th}** slots from {self.src} -> {self.target}.\nSource clan leaders will be notified to fill these slots.", ephemeral=True)
        except ValueError:
            await i.response.send_message("Invalid number.", ephemeral=True)

import discord
from discord.ext import commands
from discord import app_commands
import discord.ui
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
import os
import asyncio

class ClanDashboardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Add New Clan", style=discord.ButtonStyle.success, custom_id="add_new_clan")
    async def add_new_clan(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Start the interactive setup
        await interaction.response.send_message(
            "Let's set up a new clan! First, select the **Clan Type** and **Minimum Town Hall**.",
            view=ClanSetupStartView(),
            ephemeral=True
        )

    @discord.ui.button(label="Configure Questions", style=discord.ButtonStyle.secondary, custom_id="configure_questions")
    async def configure_questions(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(QuestionsModal())

    @discord.ui.button(label="Edit Clan", style=discord.ButtonStyle.primary, custom_id="edit_clan")
    async def edit_clan(self, interaction: discord.Interaction, button: discord.ui.Button):
        clans = await mongo_manager.get_clans()
        if not clans:
            await interaction.response.send_message("No clans found to edit.", ephemeral=True)
            return
        view = SelectClanView(clans, action="edit")
        await interaction.response.send_message("Select a clan to edit:", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Clan", style=discord.ButtonStyle.danger, custom_id="delete_clan")
    async def delete_clan(self, interaction: discord.Interaction, button: discord.ui.Button):
        clans = await mongo_manager.get_clans()
        if not clans:
            await interaction.response.send_message("No clans found to delete.", ephemeral=True)
            return
        view = SelectClanView(clans, action="delete")
        await interaction.response.send_message("Select a clan to delete:", view=view, ephemeral=True)

    @discord.ui.button(label="Manage Visibility", style=discord.ButtonStyle.secondary, custom_id="manage_visibility")
    async def manage_visibility(self, interaction: discord.Interaction, button: discord.ui.Button):
        clans = await mongo_manager.get_clans()
        if not clans:
            await interaction.response.send_message("No clans found.", ephemeral=True)
            return
        view = ClanVisibilityView(clans)
        await interaction.response.send_message("Select clans to be **VISIBLE** (uncheck to hide):", view=view, ephemeral=True)

    @discord.ui.button(label="Manage Embeds", style=discord.ButtonStyle.success, custom_id="manage_embeds", row=1)
    async def manage_embeds(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Entry point for Directory Management
        embed = discord.Embed(title="Manage Clan Directory", description="Initiate, Edit, or Delete Clan Directory entries in #our-clans.", color=discord.Color.gold())
        view = ManageClanEmbedsView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class ManageClanEmbedsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Initiate Directory", style=discord.ButtonStyle.primary, emoji="🚀")
    async def initiate(self, interaction: discord.Interaction, button: discord.ui.Button):
        clans = await mongo_manager.get_clans()
        if not clans:
            await interaction.response.send_message("No clans found.", ephemeral=True)
            return
        
        # Filter out clans that already have a thread_id (already initiated)
        # Actually user said: "only one per clan... say directory already exists"
        # So we show all, but check on selection.
        view = DirectoryClanSelectView(clans, action="initiate")
        await interaction.response.send_message("Select a clan to **Initiate** (Create Thread & Embed):", view=view, ephemeral=True)

    @discord.ui.button(label="Edit Directory", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        clans = await mongo_manager.get_clans()
        # Filter for clans that HAVE a thread_id (are initiated)
        initiated_clans = [c for c in clans if c.get('thread_id')]
        
        if not initiated_clans:
            await interaction.response.send_message("No initiated clan directories found. Please Initiate one first.", ephemeral=True)
            return
        
        view = DirectoryClanSelectView(initiated_clans, action="edit")
        await interaction.response.send_message("Select a clan to **Edit**:", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Directory", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Owner check
        if interaction.user.id != int(os.getenv("OWNER_ID")):
             await interaction.response.send_message("You are not authorized to delete directories.", ephemeral=True)
             return

        clans = await mongo_manager.get_clans()
        initiated_clans = [c for c in clans if c.get('thread_id')]
        
        if not initiated_clans:
            await interaction.response.send_message("No initiated clan directories found.", ephemeral=True)
            return

        view = DirectoryClanSelectView(initiated_clans, action="delete")
        await interaction.response.send_message("Select a clan to **Delete** (Remove Thread/Embed Data):", view=view, ephemeral=True)

class DirectoryClanSelectView(discord.ui.View):
    def __init__(self, clans, action):
        super().__init__(timeout=None)
        self.action = action
        self.clans = clans
        
        options = []
        for c in clans:
             description = "Ready to Initiate"
             if action == "initiate" and c.get('thread_id'):
                 description = "⚠️ Already Initiated"
             elif action == "edit":
                 description = f"Status: {c.get('status', 'N/A')} | Cat: {c.get('category', 'N/A')}"
             
             options.append(discord.SelectOption(label=c['name'], value=c['clan_tag'], description=description))

        # Discord limit 25
        self.select_clan.options = options[:25]

    @discord.ui.select(placeholder="Select Clan")
    async def select_clan(self, interaction: discord.Interaction, select: discord.ui.Select):
        clan_tag = select.values[0]
        clan = next((c for c in self.clans if c['clan_tag'] == clan_tag), None)
        
        if not clan:
            await interaction.response.send_message("Clan not found.", ephemeral=True)
            return

        if self.action == "initiate":
            if clan.get('thread_id'):
                await interaction.response.send_message(f"⚠️ **{clan['name']}** already has a directory entry. Use **Edit** to update it, or **Delete** to start fresh.", ephemeral=True)
                return
            
            # Start Initiation Flow: Ask Status & Category
            await interaction.response.send_message(f"Initiating Directory for **{clan['name']}**.\nPlease configured the details below:", view=DirectorySetupView(clan), ephemeral=True)
        
        elif self.action == "edit":
            # Start Edit Flow
            await interaction.response.send_message(f"Editing Directory for **{clan['name']}**:", view=DirectoryEditView(clan), ephemeral=True)

        if self.action == "delete":
            # Delete Flow
            # Call OurClansCog to delete thread
            cog = interaction.client.get_cog("OurClansCog")
            if cog:
                 await cog.delete_clan_directory(clan_tag)
            
            # Clear DB fields
            await mongo_manager.update_clan_field(clan_tag, "thread_id", None)
            await mongo_manager.update_clan_field(clan_tag, "embed_message_id", None)
            await mongo_manager.update_clan_field(clan_tag, "status", None)
            await mongo_manager.update_clan_field(clan_tag, "category", None)
            await mongo_manager.update_clan_field(clan_tag, "description", None)
            await mongo_manager.update_clan_field(clan_tag, "leaders_note", None)
            
            await interaction.response.send_message(f"🗑️ Directory and Thread for **{clan['name']}** have been removed.", ephemeral=True)

class DirectorySetupView(discord.ui.View):
    def __init__(self, clan):
        super().__init__(timeout=None)
        self.clan = clan
        self.status = None
        self.category = None
    
    @discord.ui.select(placeholder="Select Status", options=[
        discord.SelectOption(label="Family", value="family", emoji="🛡️"),
        discord.SelectOption(label="Trial", value="trial", emoji="🧪")
    ])
    async def select_status(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.status = select.values[0]
        if self.status and self.category:
            self.confirm_btn.disabled = False
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.select(placeholder="Select Category", options=[
        discord.SelectOption(label="Main", value="Main", emoji="🏰"),
        discord.SelectOption(label="Feeder", value="Feeder", emoji="🎓"),
        discord.SelectOption(label="Farming", value="Farming", emoji="🌾"),
        discord.SelectOption(label="Trial", value="Trial", emoji="🧪")
    ])
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        if self.status and self.category:
            self.confirm_btn.disabled = False
            await interaction.response.edit_message(view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Create Directory (Thread & Embed)", style=discord.ButtonStyle.green, disabled=True)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Call the logic to create thread/embed
        # We need to call a function in OurClansCog, or import it.
        # Ideally, we trigger the logic. 
        # Since logic is in OurClansCog, we can get the cog and call a method.
        
        await interaction.response.defer()
        
        # Save Basic Info First
        await mongo_manager.update_clan_field(self.clan['clan_tag'], "status", self.status)
        await mongo_manager.update_clan_field(self.clan['clan_tag'], "category", self.category)
        
        # Call OurClansCog to create thread
        cog = interaction.client.get_cog("OurClansCog")
        if cog:
            success, msg = await cog.create_clan_directory(self.clan['clan_tag'])
            if success:
                await interaction.followup.send(f"✅ **Success!** {msg}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ **Error:** {msg}", ephemeral=True)
        else:
            await interaction.followup.send("❌ **Error:** `OurClansCog` is not loaded. Please contact admin.", ephemeral=True)

class DirectoryEditView(discord.ui.View):
    def __init__(self, clan):
        super().__init__(timeout=None)
        self.clan = clan

    @discord.ui.select(placeholder="Edit Field", options=[
        discord.SelectOption(label="Status", value="status"),
        discord.SelectOption(label="Category", value="category"),
        discord.SelectOption(label="Leaders Note", value="leaders_note")
    ])
    async def select_field(self, interaction: discord.Interaction, select: discord.ui.Select):
        field = select.values[0]
        
        if field == "status":
            # Sub-view for status
            await interaction.response.send_message("Select New Status:", view=SimpleUpdateView(self.clan['clan_tag'], "status", ["family", "trial"]), ephemeral=True)
        elif field == "category":
             await interaction.response.send_message("Select New Category:", view=SimpleUpdateView(self.clan['clan_tag'], "category", ["Main", "Feeder", "Farming", "Trial"]), ephemeral=True)
        else:
            # Modal for text fields
            label = "Leaders Note"
            modal = SingleFieldModal(self.clan['clan_tag'], field, label, self.clan.get(field, ""))
            await interaction.response.send_modal(modal)

class SimpleUpdateView(discord.ui.View):
    def __init__(self, clan_tag, field, options_list):
        super().__init__(timeout=None)
        options = []
        for opt in options_list:
            options.append(discord.SelectOption(label=opt.title(), value=opt))
        
        self.select = discord.ui.Select(placeholder=f"Select {field}", options=options)
        self.select.callback = self.callback
        self.add_item(self.select)
        self.clan_tag = clan_tag
        self.field = field

    async def callback(self, interaction: discord.Interaction):
        val = self.select.values[0]
        await mongo_manager.update_clan_field(self.clan_tag, self.field, val)
        await interaction.response.send_message(f"✅ Updated **{self.field}** to `{val}`.", ephemeral=True)
        
        # Trigger Embed Update if possible
        cog = interaction.client.get_cog("OurClansCog")
        if cog:
            await cog.update_clan_embed(self.clan_tag)

class ClanVisibilityView(discord.ui.View):
    def __init__(self, clans):
        super().__init__(timeout=None)
        self.clans = clans
        
        # Determine max clans per page if we were paginating, but for now just show all or max 25
        # Select Menu with Multi-Select to toggle visibility.
        
        options = []
        # Sort clans by name for better UI
        sorted_clans = sorted(clans, key=lambda x: x.get('name', ''))[:25]
        
        for clan in sorted_clans:
            # Standardize on 'visible' field. Toggle logic: if 'visible' is True, it's Eye.
            is_visible = clan.get('visible', False)
            if isinstance(is_visible, str):
                is_visible = is_visible.lower() == 'true'
                
            label = f"{'👁️' if is_visible else '🙈'} {clan['name']}"
            desc = f"Currently {'Visible' if is_visible else 'Hidden'}"
            options.append(discord.SelectOption(
                label=label, 
                value=clan['clan_tag'], 
                description=desc,
                default=is_visible
            ))
            
        self.select = discord.ui.Select(
            placeholder="Select visible clans (uncheck to hide)...",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id="visibility_select"
        )
        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        selected_tags = self.select.values
        
        # Update all clans in this view's scope
        updates = []
        for clan in self.clans:
            tag = clan['clan_tag']
            # If tag is in selected_tags, it should be VISIBLE
            new_visible = tag in selected_tags
            
            # Only update if changed
            if clan.get('visible') != new_visible:
                updates.append(mongo_manager.update_clan_field(tag, "visible", new_visible))
                # Also CLEAN UP the 'hidden' field if it exists to avoid future confusion
                updates.append(mongo_manager.update_clan_field(tag, "hidden", None))
        
        if updates:
            await asyncio.gather(*updates)
            
        await interaction.response.send_message(f"✅ Visibility updated! {len(selected_tags)} clans are now marked as visible.", ephemeral=True)

class QuestionsModal(discord.ui.Modal, title="Configure Interview Questions"):
    questions = discord.ui.TextInput(label="Questions (One per line)", style=discord.TextStyle.paragraph, placeholder="Enter questions here...")

    async def on_submit(self, interaction: discord.Interaction):
        questions_list = self.questions.value.split('\n')
        questions_list = [q.strip() for q in questions_list if q.strip()]
        await mongo_manager.save_questions("join_clan", questions_list)
        await interaction.response.send_message("Interview questions saved!", ephemeral=True)

class ClanDashboardCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        print("Clan Dashboard Cog Loaded")
        self.bot.add_view(ClanDashboardView())

    @app_commands.command(name="clandashboard", description="Open the Clan Dashboard")
    async def clandashboard(self, interaction: discord.Interaction):
        if interaction.user.id != int(os.getenv("OWNER_ID")):
             await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
             return
        
        embed = discord.Embed(title="Clan Dashboard", description="Manage Clans (Add, Edit, Delete)", color=discord.Color.green())
        view = ClanDashboardView()
        await interaction.response.send_message(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(ClanDashboardCog(bot))

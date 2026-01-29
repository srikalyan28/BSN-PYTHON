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
        
        # Create options
        options = []
        for clan in clans:
            # Default to FALSE (Hidden) if missing, to match Ticket System logic
            is_visible = clan.get('visible', False)
            options.append(discord.SelectOption(
                label=clan['name'],
                value=clan['clan_tag'],
                description=clan['clan_tag'],
                default=is_visible
            ))
        
        # Select Menu
        self.select = discord.ui.Select(
            placeholder="Select Visible Clans",
            min_values=0,
            max_values=len(options),
            options=options
        )
        self.select.callback = self.callback
        self.add_item(self.select)

    async def callback(self, interaction: discord.Interaction):
        selected_tags = self.select.values
        
        # Update all clans
        for clan in self.clans:
            tag = clan['clan_tag']
            is_visible = tag in selected_tags
            await mongo_manager.update_clan_field(tag, "visible", is_visible)
            
        await interaction.response.send_message(f"✅ Visibility updated! {len(selected_tags)} clans are now visible.", ephemeral=True)

class ClanSetupStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.clan_type = None
        self.min_th = None

    @discord.ui.select(placeholder="Select Clan Type", options=[
        discord.SelectOption(label="Regular", value="Regular"),
        discord.SelectOption(label="Feeder", value="Feeder")
    ])
    async def select_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.clan_type = select.values[0]
        await interaction.response.defer()

    @discord.ui.select(placeholder="Select Minimum Town Hall", options=[
        discord.SelectOption(label="TH 11", value="11"),
        discord.SelectOption(label="TH 12", value="12"),
        discord.SelectOption(label="TH 13", value="13"),
        discord.SelectOption(label="TH 14", value="14"),
        discord.SelectOption(label="TH 15", value="15"),
        discord.SelectOption(label="TH 16", value="16"),
        discord.SelectOption(label="TH 17", value="17")
    ])
    async def select_th(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.min_th = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.clan_type or not self.min_th:
            await interaction.response.send_message("Please select both Clan Type and Minimum Town Hall.", ephemeral=True)
            return
        
        # Disable view
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Start chat collection
        await collect_clan_details(interaction, self.clan_type, self.min_th)

async def collect_clan_details(interaction, clan_type, min_th):
    # Helper to wait for message
    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

    try:
        # 1. Name
        await interaction.followup.send("Please enter the **Clan Name**:", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        name = msg.content
        await msg.delete() # Clean up user input if possible

        # 2. Tag
        await interaction.followup.send(f"Great! Enter the **Clan Tag** for {name}:", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        tag = msg.content.upper()
        await msg.delete()

        # 3. Abbreviation (New)
        await interaction.followup.send("Enter **Clan Abbreviation** (e.g. ICL, DB):", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        abbreviation = msg.content.upper()
        await msg.delete()

        # 3. Link
        await interaction.followup.send("Paste the **Clan Link** (from Clash of Clans):", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        link = msg.content
        await msg.delete()

        # 4. Logo
        await interaction.followup.send("Please upload the **Clan Logo** (Attachment) or paste a **Permanent URL**:", ephemeral=True)
        msg_logo = await interaction.client.wait_for('message', check=check, timeout=60)
        
        logo = None
        if msg_logo.attachments:
            # Re-upload to the channel to ensure persistence
            try:
                # Create a file object from the attachment
                file = await msg_logo.attachments[0].to_file()
                # Send it back to the channel (non-ephemeral) so it persists
                asset_msg = await interaction.channel.send(content=f"**[Asset]** Logo for {name} ({tag})", file=file)
                logo = asset_msg.attachments[0].url
            except Exception as e:
                print(f"Failed to re-upload logo asset: {e}")
                # Fallback to original url (might expire if msg is deleted)
                logo = msg_logo.attachments[0].url
        else:
            logo = msg_logo.content
            
        await msg_logo.delete()

        # 5. Leader
        await interaction.followup.send("Mention the **Clan Leader** (e.g., @User):", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        leader_id = msg.mentions[0].id if msg.mentions else None
        if not leader_id:
            # Fallback if they just typed ID
            if msg.content.isdigit():
                leader_id = msg.content
            else:
                await interaction.followup.send("Invalid mention. Aborting.", ephemeral=True)
                return
        await msg.delete()

        # 6. Roles Logic
        view = RoleSetupView()
        # Create a message to hold the view so we can edit it if needed, or just follow up
        view_msg = await interaction.followup.send("Do you want to **Auto-Create Discord Roles** (Member & Leadership) for this clan?", view=view, ephemeral=True)
        await view.wait()
        
        leadership_role_id = None
        clan_role_id = None
        
        if view.choice == "auto":
            try:
                guild = interaction.guild
                # Create Roles
                # Member Role: <NAME>
                m_role = await guild.create_role(name=name, mentionable=True)
                # Leader Role: <NAME> Leadership
                l_role = await guild.create_role(name=f"{name} Leadership", mentionable=True)
                
                clan_role_id = str(m_role.id)
                leadership_role_id = str(l_role.id)
                await interaction.followup.send(f"✅ Auto-Created Roles: {m_role.mention} and {l_role.mention}", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"⚠️ Error creating roles: {e}. Roles set to None. Edit later.", ephemeral=True)
                
        else:
            # Manual Entry
            # Leadership Role
            await interaction.followup.send("Mention the **Leadership Role** (e.g., @Role):", ephemeral=True)
            msg = await interaction.client.wait_for('message', check=check, timeout=60)
            leadership_role_id = msg.role_mentions[0].id if msg.role_mentions else (msg.content if msg.content.isdigit() else None)
            await msg.delete()
            
            # Member Role
            await interaction.followup.send("Mention the **Clan Member Role** (e.g., @Role):", ephemeral=True)
            msg = await interaction.client.wait_for('message', check=check, timeout=60)
            clan_role_id = msg.role_mentions[0].id if msg.role_mentions else (msg.content if msg.content.isdigit() else None)
            await msg.delete()

        # Fetch additional details from CoC API
        clan_details = await coc_api.get_clan(tag)
        war_league = clan_details.war_league.name if clan_details and clan_details.war_league else "Unranked"
        badge_url = clan_details.badge.url if clan_details else ""
        
        capital_hall = "N/A"
        if clan_details:
             if hasattr(clan_details, 'capital_hall_level'):
                 capital_hall = str(clan_details.capital_hall_level)
             elif hasattr(clan_details, 'capital_districts'):
                 districts = clan_details.capital_districts
                 if districts:
                     for d in districts:
                         if d.name == "Capital Peak":
                             capital_hall = str(d.hall_level)
                             break
                     if capital_hall == "N/A" and districts:
                         capital_hall = str(districts[0].hall_level)

        # Save
        clan_data = {
            "name": name,
            "clan_tag": tag,
            "clan_abbreviation": abbreviation,
            "type": clan_type,
            "min_th": int(min_th),
            "clan_link": link,
            "logo_url": logo,
            "leader_id": str(leader_id),
            "leadership_role_id": str(leadership_role_id) if leadership_role_id else None,
            "clan_role_id": str(clan_role_id) if clan_role_id else None,
            "war_league": war_league,
            "capital_hall": str(capital_hall),
            "badge_url": badge_url
        }
        
        await mongo_manager.save_clan(clan_data)
        await interaction.followup.send(f"✅ **{name}** ({abbreviation}) has been added successfully!", ephemeral=True)

    except asyncio.TimeoutError:
        await interaction.followup.send("Timed out. Please start over.", ephemeral=True)

class RoleSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.choice = None

    @discord.ui.button(label="Yes, Auto-Create", style=discord.ButtonStyle.success)
    async def auto(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "auto"
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="No, Manual Input", style=discord.ButtonStyle.secondary)
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.choice = "manual"
        self.stop()
        await interaction.response.defer()


class SelectClanView(discord.ui.View):
    def __init__(self, clans, action):
        super().__init__(timeout=None)
        self.action = action
        options = []
        for clan in clans:
            options.append(discord.SelectOption(label=clan['name'], value=clan['clan_tag'], description=f"Tag: {clan['clan_tag']}"))
        
        self.select_clan.options = options[:25]

    @discord.ui.select(placeholder="Select a Clan")
    async def select_clan(self, interaction: discord.Interaction, select: discord.ui.Select):
        clan_tag = select.values[0]
        if self.action == "delete":
            await mongo_manager.delete_clan(clan_tag)
            await interaction.response.send_message(f"Clan with tag {clan_tag} deleted.", ephemeral=True)
        elif self.action == "edit":
            # Fetch current clan data to pass to the view
            clans = await mongo_manager.get_clans()
            clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
            if clan:
                await interaction.response.send_message(f"Editing **{clan['name']}**. Select a field to edit:", view=ClanFieldSelectionView(clan), ephemeral=True)
            else:
                await interaction.response.send_message("Clan not found.", ephemeral=True)

class ClanFieldSelectionView(discord.ui.View):
    def __init__(self, clan_data):
        super().__init__(timeout=None)
        self.clan_data = clan_data

    @discord.ui.select(placeholder="Select Field to Edit", options=[
        discord.SelectOption(label="Clan Name", value="name"),
        discord.SelectOption(label="Clan Tag", value="clan_tag"),
        discord.SelectOption(label="Clan Type", value="type", description="Regular or Feeder"),
        discord.SelectOption(label="Min Town Hall", value="min_th"),
        discord.SelectOption(label="Leader ID", value="leader_id"),
        discord.SelectOption(label="Leadership Role ID", value="leadership_role_id"),
        discord.SelectOption(label="Clan Role ID", value="clan_role_id"),
        discord.SelectOption(label="Abbreviation", value="clan_abbreviation"),
        discord.SelectOption(label="Clan Link", value="clan_link"),
        discord.SelectOption(label="Logo URL", value="logo_url")
    ])
    async def select_field(self, interaction: discord.Interaction, select: discord.ui.Select):
        field_key = select.values[0]
        field_label = next(opt.label for opt in select.options if opt.value == field_key)
        current_value = self.clan_data.get(field_key, "")
        
        if field_key == "logo_url":
            # Special handling for Logo to allow attachments
            await interaction.response.send_message("Please upload the new **Clan Logo** (Attachment) or paste a **Permanent URL**:", ephemeral=True)
            
            def check(m):
                return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

            try:
                msg_logo = await interaction.client.wait_for('message', check=check, timeout=60)
                
                logo = None
                if msg_logo.attachments:
                    # Re-upload logic
                    try:
                        file = await msg_logo.attachments[0].to_file()
                        asset_msg = await interaction.channel.send(content=f"**[Asset]** Logo for {self.clan_data['name']} ({self.clan_data['clan_tag']})", file=file)
                        logo = asset_msg.attachments[0].url
                    except Exception as e:
                        print(f"Failed to re-upload logo asset: {e}")
                        logo = msg_logo.attachments[0].url
                else:
                    logo = msg_logo.content
                
                await msg_logo.delete()
                
                await mongo_manager.update_clan_field(self.clan_data['clan_tag'], "logo_url", logo)
                await interaction.followup.send(f"✅ Updated **Logo URL** successfully.", ephemeral=True)
                
            except asyncio.TimeoutError:
                await interaction.followup.send("Timed out. Edit cancelled.", ephemeral=True)
            return

        await interaction.response.send_modal(SingleFieldModal(self.clan_data['clan_tag'], field_key, field_label, current_value))

class SingleFieldModal(discord.ui.Modal):
    def __init__(self, clan_tag, field_key, field_label, current_value):
        super().__init__(title=f"Edit {field_label}")
        self.clan_tag = clan_tag
        self.field_key = field_key
        
        style = discord.TextStyle.short
        if field_key == "leaders_note":
            style = discord.TextStyle.paragraph
            
        self.input = discord.ui.TextInput(label=field_label, default=str(current_value), required=True, style=style)
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        new_value = self.input.value
        
        # Type conversion if necessary
        if self.field_key == "min_th":
            if new_value.isdigit():
                new_value = int(new_value)
            else:
                await interaction.response.send_message("Min Town Hall must be a number.", ephemeral=True)
                return
        
        await mongo_manager.update_clan_field(self.clan_tag, self.field_key, new_value)
        
        # If updating Clan Tag, refresh other stats
        if self.field_key == "clan_tag":
            clan_details = await coc_api.get_clan(new_value)
            if clan_details:
                war_league = clan_details.war_league.name if clan_details.war_league else "Unranked"
                
                capital_hall = "N/A"
                if hasattr(clan_details, 'capital_hall_level'):
                     capital_hall = str(clan_details.capital_hall_level)
                elif hasattr(clan_details, 'capital_districts'):
                     districts = clan_details.capital_districts
                     if districts:
                         for d in districts:
                             if d.name == "Capital Peak":
                                 capital_hall = str(d.hall_level)
                                 break
                         if capital_hall == "N/A" and districts:
                             capital_hall = str(districts[0].hall_level)
                
                # We need to update the old tag entry? No, update_clan_field updates based on OLD tag?
                # Wait, update_clan_field uses `self.clan_tag` which is the OLD tag.
                # If we change the tag, we are effectively renaming the key.
                # But `update_clan_field` does `update_one({"clan_tag": clan_tag}, {"$set": {field: value}})`
                # So it updates the document where clan_tag is the OLD tag, setting the NEW tag.
                # So the document now has the NEW tag.
                # But we also need to update war_league and capital_hall on that SAME document (which now has the NEW tag).
                # But `update_clan_field` is atomic.
                # So we should probably do a second update using the NEW tag (since the first update changed it).
                
                await mongo_manager.update_clan_field(new_value, "war_league", war_league)
                await mongo_manager.update_clan_field(new_value, "capital_hall", capital_hall)
                if clan_details:
                    await mongo_manager.update_clan_field(new_value, "badge_url", clan_details.badge.url)
                
                await interaction.response.send_message(f"✅ Updated **{self.field_key}** to `{new_value}` and refreshed stats.", ephemeral=True)
                return

        await interaction.response.send_message(f"✅ Updated **{self.field_key}** to `{new_value}`.", ephemeral=True)

class ClanVisibilityView(discord.ui.View):
    def __init__(self, clans):
        super().__init__(timeout=None)
        self.clans = clans
        
        # Determine max clans per page if we were paginating, but for now just show all or max 25
        # Select Menu with Multi-Select? Or Checkboxes (not supported)?
        # Using a Multi-Select Menu to toggle visibility is cleanest given 25 limit.
        
        options = []
        for clan in self.clans[:25]:
            is_visible = clan.get('hidden', False) == False
            label = f"{'👁️' if is_visible else '🙈'} {clan['name']}"
            desc = f"Currently {'Visible' if is_visible else 'Hidden'}"
            options.append(discord.SelectOption(label=label, value=clan['clan_tag'], description=desc))
            
        self.add_item(ClanVisibilitySelect(options))

class ClanVisibilitySelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Toggle Clan Visibility...", min_values=1, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_tags = self.values
        # Toggle logic: If it was hidden, make visible. If visible, make hidden?
        # Or simpler: The selection simply inverts whatever state it currently is in?
        # Actually user wants to "Select clans to be VISIBLE (uncheck to hide)" style?
        # Discord select doesn't persist checks nicely.
        # Let's just flip the status of selected clans.
        
        c = 0
        for tag in selected_tags:
            # Fetch current
             clans = await mongo_manager.get_clans()
             clan = next((c for c in clans if c['clan_tag'] == tag), None)
             if clan:
                 current_hidden = clan.get('hidden', False)
                 new_hidden = not current_hidden
                 await mongo_manager.update_clan_field(tag, "hidden", new_hidden)
                 c += 1
        
        await interaction.response.send_message(f"Toggled visibility for {c} clans. Please reload the menu to see updates.", ephemeral=True)

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

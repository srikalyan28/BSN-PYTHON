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

class ClanVisibilityView(discord.ui.View):
    def __init__(self, clans):
        super().__init__(timeout=None)
        self.clans = clans
        
        # Create options
        options = []
        for clan in clans:
            is_visible = clan.get('visible', True)
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
        discord.SelectOption(label="Cruise", value="Cruise")
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

        # 3. Link
        await interaction.followup.send("Paste the **Clan Link** (from Clash of Clans):", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        link = msg.content
        await msg.delete()

        # 4. Logo
        await interaction.followup.send("Paste the **Clan Logo URL** (Image Link):", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        logo = msg.content
        await msg.delete()

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

        # 6. Role
        await interaction.followup.send("Mention the **Leadership Role** (e.g., @Role):", ephemeral=True)
        msg = await interaction.client.wait_for('message', check=check, timeout=60)
        role_id = msg.role_mentions[0].id if msg.role_mentions else None
        if not role_id:
             if msg.content.isdigit():
                role_id = msg.content
             else:
                await interaction.followup.send("Invalid role mention. Aborting.", ephemeral=True)
                return
        await msg.delete()

        # Fetch additional details from CoC API
        clan_details = await coc_api.get_clan(tag)
        war_league = clan_details.war_league.name if clan_details and clan_details.war_league else "Unranked"
        
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
            "type": clan_type,
            "min_th": int(min_th),
            "clan_link": link,
            "logo_url": logo,
            "leader_id": str(leader_id),
            "leadership_role_id": str(role_id),
            "war_league": war_league,
            "capital_hall": str(capital_hall)
        }
        
        await mongo_manager.save_clan(clan_data)
        await interaction.followup.send(f"✅ **{name}** has been added successfully!", ephemeral=True)

    except asyncio.TimeoutError:
        await interaction.followup.send("Timed out. Please start over.", ephemeral=True)


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
        discord.SelectOption(label="Clan Type", value="type", description="Regular or Cruise"),
        discord.SelectOption(label="Min Town Hall", value="min_th"),
        discord.SelectOption(label="Leader ID", value="leader_id"),
        discord.SelectOption(label="Leadership Role ID", value="leadership_role_id"),
        discord.SelectOption(label="Clan Link", value="clan_link"),
        discord.SelectOption(label="Logo URL", value="logo_url")
    ])
    async def select_field(self, interaction: discord.Interaction, select: discord.ui.Select):
        field_key = select.values[0]
        field_label = next(opt.label for opt in select.options if opt.value == field_key)
        current_value = self.clan_data.get(field_key, "")
        
        await interaction.response.send_modal(SingleFieldModal(self.clan_data['clan_tag'], field_key, field_label, current_value))

class SingleFieldModal(discord.ui.Modal):
    def __init__(self, clan_tag, field_key, field_label, current_value):
        super().__init__(title=f"Edit {field_label}")
        self.clan_tag = clan_tag
        self.field_key = field_key
        
        self.input = discord.ui.TextInput(label=field_label, default=str(current_value), required=True)
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
                
                await interaction.response.send_message(f"✅ Updated **{self.field_key}** to `{new_value}` and refreshed stats.", ephemeral=True)
                return

        await interaction.response.send_message(f"✅ Updated **{self.field_key}** to `{new_value}`.", ephemeral=True)

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

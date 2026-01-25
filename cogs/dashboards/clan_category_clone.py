import discord
from discord.ext import commands
from discord import app_commands
from utils.mongo_manager import mongo_manager
import asyncio

class CloneCategoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        print("Clone Category Cog Loaded")

    @app_commands.command(name="create_clan_category", description="Clone a category setup for a clan")
    async def create_clan_category(self, interaction: discord.Interaction):
        # Admin check?
        
        # 1. Select Clan
        clans = await mongo_manager.get_clans()
        if not clans:
            await interaction.response.send_message("No clans found in database.", ephemeral=True)
            return

        view = CloneWizardSelectClan(clans)
        await interaction.response.send_message("Select the **Target Clan** to build a category for:", view=view, ephemeral=True)

class CloneWizardSelectClan(discord.ui.View):
    def __init__(self, clans):
        super().__init__(timeout=None)
        self.clans = clans
        
        options = []
        for c in clans:
            # Check if role/abbrev exist
            missing = []
            if not c.get('clan_role_id'): missing.append("Role")
            if not c.get('leadership_role_id'): missing.append("LeaderRole")
            if not c.get('clan_abbreviation'): missing.append("Abbrev")
            
            desc = f"Ready"
            if missing:
                desc = f"⚠️ Missing: {', '.join(missing)}"
            
            options.append(discord.SelectOption(label=c['name'], value=c['clan_tag'], description=desc))
            
        self.select.options = options[:25]

    @discord.ui.select(placeholder="Select Target Clan")
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        clan_tag = select.values[0]
        clan = next((c for c in self.clans if c['clan_tag'] == clan_tag), None)
        
        # Validation
        if not clan.get('clan_role_id') or not clan.get('leadership_role_id') or not clan.get('clan_abbreviation'):
             await interaction.response.send_message(f"❌ **{clan['name']}** is missing Role IDs or Abbreviation. Please use **Edit Clan** in the dashboard to fix this first.", ephemeral=True)
             return
             
        # Next Step: Select Template Category
        # We can use a ChannelSelect menu limited to Categories
        view = CloneWizardSelectTemplate(clan)
        await interaction.response.send_message(f"Selected **{clan['name']}**.\nNow select the **Template Category** to clone from:", view=view, ephemeral=True)


class CloneWizardSelectTemplate(discord.ui.View):
    def __init__(self, target_clan):
        super().__init__(timeout=None)
        self.target_clan = target_clan

    @discord.ui.select(cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="Select Template Category")
    async def select(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        template = select.values[0] # Appears as a Channel object (CategoryChannel)
        
        # Next: Define Template Roles
        # We need to ask user which roles in that template are the "Old Member" and "Old Leader" roles
        await interaction.response.send_message(
            f"Selected Template: **{template.name}**.\nNow, please identify the **Template Roles** (the ones used in the template that should be replaced).", 
            view=CloneWizardRoleMapping(self.target_clan, template), 
            ephemeral=True
        )

class CloneWizardRoleMapping(discord.ui.View):
    def __init__(self, target_clan, template_cat):
        super().__init__(timeout=None)
        self.target_clan = target_clan
        self.template_cat = template_cat
        self.old_member_role = None
        self.old_leader_role = None

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select TEMPLATE Member Role")
    async def select_member(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.old_member_role = select.values[0]
        self.check_complete()
        await interaction.response.edit_message(view=self)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Select TEMPLATE Leader Role")
    async def select_leader(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        self.old_leader_role = select.values[0]
        self.check_complete()
        await interaction.response.edit_message(view=self)

    def check_complete(self):
        if self.old_member_role and self.old_leader_role:
            self.confirm.disabled = False
        else:
            self.confirm.disabled = True

    @discord.ui.button(label="Next: Input Template Abbreviation", style=discord.ButtonStyle.primary, disabled=True)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TemplateAbbrevModal(self.target_clan, self.template_cat, self.old_member_role, self.old_leader_role))


class TemplateAbbrevModal(discord.ui.Modal, title="Template Abbreviation"):
    abbrev = discord.ui.TextInput(label="Template Abbreviation", placeholder="e.g. TG (for '📝・tg-clan-info')", min_length=1, max_length=10)

    def __init__(self, target_clan, template_cat, old_member_role, old_leader_role):
        super().__init__()
        self.target_clan = target_clan
        self.template_cat = template_cat
        self.old_member = old_member_role
        self.old_leader = old_leader_role

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        template_abbrev = self.abbrev.value.strip()
        
        await perform_clone(interaction, self.target_clan, self.template_cat, self.old_member, self.old_leader, template_abbrev)


async def perform_clone(interaction, target_clan, template_cat, old_member, old_leader, template_abbrev):
        guild = interaction.guild
        
        # Resolve Target Roles
        try:
            new_member_role = guild.get_role(int(target_clan['clan_role_id']))
            new_leader_role = guild.get_role(int(target_clan['leadership_role_id']))
        except:
            await interaction.followup.send("❌ Error finding Target Clan Roles. Ensure IDs are valid.", ephemeral=True)
            return

        if not new_member_role or not new_leader_role:
             await interaction.followup.send("❌ Target Clan Roles not found in server.", ephemeral=True)
             return

        # Refetch Template Category from Guild to ensure we have .channels
        real_template = guild.get_channel(template_cat.id)
        if not real_template:
            await interaction.followup.send("❌ Template Category not found in cache. Please try again.", ephemeral=True)
            return
            
        print(f"Cloning from Template: {real_template.name} | Channels: {len(real_template.channels)}")

        # 1. Create Category
        new_cat_name = f"-----{target_clan['name']}-----"
        
        # Clone Category logic (permissions?)
        # Base perms for the new category should probably mimic the template? 
        # But we need to swap the overwrites immediately or applied after?
        # Safe way: Create with overwrites.
        
        overwrites = real_template.overwrites
        new_overwrites = process_overwrites(overwrites, old_member, old_leader, new_member_role, new_leader_role)
        
        new_cat = await guild.create_category(name=new_cat_name, overwrites=new_overwrites, position=real_template.position + 1)
        
        report = [f"Created Category: **{new_cat_name}**"]
        
        # 2. Clone Channels
        new_abbrev = target_clan.get('clan_abbreviation', '').lower()
        template_abbrev = template_abbrev.lower()
        
        try:
            for ch in real_template.channels:
                # Name Replacement
                # "📝・tg-clan-info" -> "📝・icl-clan-info"
                new_name = ch.name.lower().replace(template_abbrev, new_abbrev)
                
                # Perms
                ch_overwrites = process_overwrites(ch.overwrites, old_member, old_leader, new_member_role, new_leader_role)
                
                if isinstance(ch, discord.TextChannel):
                    new_ch = await new_cat.create_text_channel(name=new_name, topic=ch.topic, overwrites=ch_overwrites, slowmode_delay=ch.slowmode_delay)
                elif isinstance(ch, discord.VoiceChannel):
                    new_ch = await new_cat.create_voice_channel(name=new_name, overwrites=ch_overwrites, bitrate=ch.bitrate, user_limit=ch.user_limit)
                elif isinstance(ch, discord.StageChannel):
                     new_ch = await new_cat.create_stage_channel(name=new_name, topic=ch.topic, overwrites=ch_overwrites)
                elif isinstance(ch, discord.ForumChannel):
                     new_ch = await guild.create_forum_channel(name=new_name, topic=ch.topic, overwrites=ch_overwrites, category=new_cat)
                
                report.append(f"Cloned {ch.name} -> **{new_name}**")
                await asyncio.sleep(0.5) # Safe rate limit
                
            await interaction.followup.send(f"✅ **Cloning Complete for {target_clan['name']}!**\n" + "\n".join(report[:15]), ephemeral=True)

        except Exception as e:
            print(f"Clone Error: {e}")
            await interaction.followup.send(f"❌ Critical Clone Error: {e}", ephemeral=True)


def process_overwrites(overwrites, old_member, old_leader, new_member, new_leader):
    new_ov = {}
    for target, overwrite in overwrites.items():
        if target.id == old_member.id:
            new_ov[new_member] = overwrite
        elif target.id == old_leader.id:
            new_ov[new_leader] = overwrite
        else:
            new_ov[target] = overwrite
    return new_ov

async def setup(bot):
    await bot.add_cog(CloneCategoryCog(bot))

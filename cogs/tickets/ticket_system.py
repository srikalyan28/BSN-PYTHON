import discord
from discord.ext import commands
import discord.ui
from utils.mongo_manager import mongo_manager
from utils.coc_api import coc_api
from utils.embed_utils import create_invite_embed, create_rejection_embed
import os
import asyncio
from datetime import datetime
from discord.ext import tasks
import aiohttp

TICKET_CATEGORY_ID = 1364627200271319140

class TicketSystemCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.clan_stats_updater.start()

    def cog_unload(self):
        self.clan_stats_updater.cancel()

    @tasks.loop(hours=12)
    async def clan_stats_updater(self):
        print("Starting scheduled clan stats update...")
        clans = await mongo_manager.get_clans()
        for c in clans:
            try:
                clan_tag = c['clan_tag']
                clan_details = await coc_api.get_clan(clan_tag)
                if clan_details:
                    updates = {}
                    
                    # War League
                    war_league = clan_details.war_league.name if clan_details.war_league else "Unranked"
                    if c.get('war_league') != war_league:
                        updates["war_league"] = war_league
                        
                    # Capital Hall
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
                    
                    if c.get('capital_hall') != capital_hall:
                        updates["capital_hall"] = capital_hall

                    # Apply Updates
                    if updates:
                        for field, value in updates.items():
                            await mongo_manager.update_clan_field(clan_tag, field, value)
                        print(f"Updated stats for {c['name']} ({clan_tag}): {updates}")
                        
            except Exception as e:
                print(f"Error updating stats for {c.get('name', 'Unknown')}: {e}")

    @clan_stats_updater.before_loop
    async def before_stats_update(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not isinstance(channel, discord.TextChannel):
            return
        
        if channel.category_id != TICKET_CATEGORY_ID:
            return

        # Wait a bit for Ticket Tool to finish its setup
        await asyncio.sleep(3)

        # Start the interview flow
        await self.start_interview(channel)

    async def start_interview(self, channel):
        # Identify Ticket Owner from overwrites
        owner_id = None
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Member) and not target.bot:
                owner_id = target.id
                break
        
        embed = discord.Embed(
            title="Welcome to Blackspire Nation Recruitment",
            description="Please follow the steps below to apply for a clan.",
            color=discord.Color.gold()
        )
        await channel.send(embed=embed, view=ContinentView(owner_id))

    async def ask_question(self, interaction, session_data, questions, index):
        if index >= len(questions):
            # All questions answered
            # Post Answers to Thread
            ans_embed = discord.Embed(title="Interview Answers", color=discord.Color.orange())
            for item in session_data["answers"]:
                ans_embed.add_field(name=item['question'], value=item['answer'], inline=False)
            
            thread = interaction.guild.get_thread(session_data["thread_id"])
            if thread:
                await thread.send(embed=ans_embed)
            
            # Proceed to Clan Selection
            await self.start_clan_selection(interaction, session_data, 0)
            return

        q = questions[index]
        embed = discord.Embed(title=f"Question {index + 1}", description=q, color=discord.Color.blue())
        embed.set_footer(text="Type your answer in the chat, then click 'Done' when finished.")
        view = QuestionDoneView(session_data, questions, index, self)
        await interaction.channel.send(embed=embed, view=view)

    async def start_clan_selection(self, interaction, session_data, account_index):
        # Wrapper to use interaction.channel
        await self.send_clan_selection(interaction.channel, session_data, account_index)

    async def send_clan_selection(self, channel, session_data, account_index, is_reselection=False):
        if account_index >= len(session_data["accounts"]):
            # All selections made
            await self.submit_application_channel(channel, session_data)
            return

        acc = session_data["accounts"][account_index]
        
        # SKIP IF REJECTED (unless it's a specific re-selection, in which case we process it)
        # If is_reselection is True, we assume we are targeting this specific account, so we don't auto-skip
        # unless we explicitly want to logic check. But for re-selection, user is picking a new one.
        if not is_reselection and acc.get("selected_clan_tag") == "rejected":
             await self.send_clan_selection(channel, session_data, account_index + 1)
             return

        # Fetch All Clans
        clans = await mongo_manager.get_clans()
        
        # Filter by eligibility (Visible + Min TH)
        valid_clans = [c for c in clans if int(c.get('min_th', 99)) <= int(acc['th']) and c.get('visible', True)]
        
        # SELF-HEALING STATS LOGIC
        updates_made = False
        for c in valid_clans:
            if c.get('war_league', 'N/A') == 'N/A' or c.get('capital_hall', 'N/A') == 'N/A':
                try:
                    clan_details = await coc_api.get_clan(c['clan_tag'])
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
                        await mongo_manager.update_clan_field(c['clan_tag'], "war_league", war_league)
                        await mongo_manager.update_clan_field(c['clan_tag'], "capital_hall", capital_hall)
                        c['war_league'] = war_league
                        c['capital_hall'] = capital_hall
                        updates_made = True
                except Exception as e:
                    print(f"Error healing stats: {e}")
        
        if updates_made:
            print("Self-healed clan stats.")

        # Sort into Regular and Feeder
        regular_clans = [c for c in valid_clans if c.get('type', 'Regular').lower() == 'regular']
        feeder_clans = [c for c in valid_clans if c.get('type', 'Regular').lower() == 'feeder']

        # If NO suitable clans
        if not regular_clans and not feeder_clans:
            criteria_embed = discord.Embed(
                title="Criteria Mismatch",
                description=f"Hello **{acc['name']}**,\n\nUnfortunately, no suitable clans are available for your profile (**TH{acc['th']}**) at this time.",
                color=discord.Color.red()
            )
            await channel.send(embed=criteria_embed)
            
            # Mark as rejected
            session_data["accounts"][account_index]["selected_clan_tag"] = "rejected"
            
            if is_reselection:
                 await channel.send(f"⚠️ **{acc['name']}** still does not meet criteria for any available clans.")
                 return

            await self.send_clan_selection(channel, session_data, account_index + 1)
            return

        embed = discord.Embed(title=f"Select Clan for {acc['name']}", description="Please choose from the available clans below.", color=discord.Color.purple())
        view = ClanSelectionView(session_data, account_index, regular_clans, feeder_clans, self, is_reselection)
        await channel.send(embed=embed, view=view)

    async def submit_application(self, interaction, session_data):
        # Compatibility wrapper
        await self.submit_application_channel(interaction.channel, session_data)

    async def submit_application_channel(self, channel, session_data):
        guild = channel.guild
        thread = guild.get_thread(session_data["thread_id"])
        
        summary_embed = discord.Embed(title="Application Summary", color=discord.Color.purple())
        summary_embed.add_field(name="Continent", value=session_data["continent"])
        summary_embed.add_field(name="Age", value=session_data["age"])
        
        mentions = []
        clans = await mongo_manager.get_clans()
        
        for i, acc in enumerate(session_data["accounts"]):
            clan_tag = acc.get("selected_clan_tag")
            
            if clan_tag == "rejected" or clan_tag == "none":
                 summary_embed.add_field(name=f"Account: {acc['name']}", value="Status: Auto-Rejected (No suitable clan)", inline=False)
                 continue

            clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
            
            clan_name = clan['name'] if clan else "None"
            summary_embed.add_field(name=f"Account: {acc['name']}", value=f"Applied to: {clan_name}", inline=False)
            
            if clan:
                if 'leader_id' in clan: mentions.append(f"<@{clan['leader_id']}>")
                if 'leadership_role_id' in clan: mentions.append(f"<@&{clan['leadership_role_id']}>")
        
        await thread.send(content=f"New Application! {' '.join(set(mentions))}", embed=summary_embed)
        
        # Send Approval View to Thread
        await thread.send("Leadership Action:", view=ApprovalView(session_data, clans))
        
        # Send Confirmation Embed to User
        confirm_embed = discord.Embed(
            title="🎉 Application Delivered! 🎉",
            description="Your application has been successfully sent to the **High Council**.",
            color=discord.Color.gold()
        )
        if guild.icon:
            confirm_embed.set_thumbnail(url=guild.icon.url)
            
        confirm_embed.add_field(name="What's Next?", value="Our leadership team is reviewing your village stats and battle records. We'll be with you shortly!", inline=False)
        confirm_embed.add_field(name="While You Wait", value="Check out our rules or chat with other members.", inline=False)
        confirm_embed.set_footer(text="Clash On! ⚔️")
        
        await channel.send(embed=confirm_embed)

    async def submit_reapplication(self, interaction, session_data, account_index):
        # Notify thread about re-application
        thread = interaction.guild.get_thread(session_data["thread_id"])
        acc = session_data["accounts"][account_index]
        clan_tag = acc.get("selected_clan_tag")
        
        # We need to fetch clan name
        clans = await mongo_manager.get_clans()
        clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
        clan_name = clan['name'] if clan else clan_tag
        
        reapp_embed = discord.Embed(title="🔄 Account Re-Applied", color=discord.Color.orange())
        reapp_embed.add_field(name="Account", value=f"{acc['name']} ({acc['tag']})")
        reapp_embed.add_field(name="New Choice", value=clan_name)
        
        mentions = []
        if clan:
             if 'leader_id' in clan: mentions.append(f"<@{clan['leader_id']}>")
             if 'leadership_role_id' in clan: mentions.append(f"<@&{clan['leadership_role_id']}>")
             
        await thread.send(content=f"Update! {' '.join(set(mentions))}", embed=reapp_embed)
        
        # Send NEW Approval View (it will filter out already accepted ones)
        await thread.send("Leadership Action:", view=ApprovalView(session_data, clans))
        
        # Confirm to user
        await interaction.channel.send(f"✅ Re-submitted **{acc['name']}** to **{clan_name}**.")

class ContinentView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=None)
        self.continent = None
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Choose your Continent", options=[
        discord.SelectOption(label="Asia", value="Asia"),
        discord.SelectOption(label="North America", value="North America"),
        discord.SelectOption(label="South America", value="South America"),
        discord.SelectOption(label="Africa", value="Africa"),
        discord.SelectOption(label="Australia", value="Australia"),
        discord.SelectOption(label="Europe", value="Europe")
    ])
    async def select_continent(self, interaction: discord.Interaction, select: discord.ui.Select):
        if self.continent: # Prevent double selection processing
             await interaction.response.defer()
             return

        self.continent = select.values[0]
        # Disable select and show confirm button
        select.disabled = True
        await interaction.response.edit_message(view=self)
        
        confirm_view = ConfirmContinentView(self.continent, self.owner_id)
        await interaction.followup.send(f"You selected **{self.continent}**. Confirm?", view=confirm_view, ephemeral=True)

class ConfirmContinentView(discord.ui.View):
    def __init__(self, continent, owner_id):
        super().__init__(timeout=None)
        self.continent = continent
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Confirmed!", view=None)
        # Proceed to Age
        await interaction.channel.send("Please select your age bracket:", view=AgeView(self.continent, self.owner_id))

    @discord.ui.button(label="Reselect", style=discord.ButtonStyle.secondary)
    async def reselect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Reselecting...", view=None)
        # Send ContinentView again
        await interaction.channel.send("Choose your Continent:", view=ContinentView(self.owner_id))

class AgeView(discord.ui.View):
    def __init__(self, continent, owner_id):
        super().__init__(timeout=None)
        self.continent = continent
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Choose your Age Bracket", options=[
        discord.SelectOption(label="Below 17", value="<17"),
        discord.SelectOption(label="17-25", value="17-25"),
        discord.SelectOption(label="25+", value="25+")
    ])
    async def select_age(self, interaction: discord.Interaction, select: discord.ui.Select):
        age = select.values[0]
        select.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Proceed to Account Count
        await interaction.channel.send("How many accounts would you like to join with?", view=AccountCountView(self.continent, age, self.owner_id))

class AccountCountView(discord.ui.View):
    def __init__(self, continent, age, owner_id):
        super().__init__(timeout=None)
        self.continent = continent
        self.age = age
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.owner_id and interaction.user.id != self.owner_id:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Select Number of Accounts", options=[
        discord.SelectOption(label="1 Account", value="1"),
        discord.SelectOption(label="2 Accounts", value="2"),
        discord.SelectOption(label="3 Accounts", value="3")
    ])
    async def select_count(self, interaction: discord.Interaction, select: discord.ui.Select):
        count = int(select.values[0])
        select.disabled = True
        await interaction.response.edit_message(view=self)
        
        session_data = {
            "continent": self.continent,
            "age": self.age,
            "account_count": count,
            "accounts": [],
            "user_id": interaction.user.id
        }
        await self.collect_player_details(interaction, session_data, 0)

    async def collect_player_details(self, interaction, session_data, index):
        if index >= session_data["account_count"]:
            await self.finalize_collection(interaction, session_data)
            return

        account_num = index + 1
        embed = discord.Embed(title=f"Account #{account_num} Details", description="Please enter the Player Tag for this account.", color=discord.Color.blue())
        await interaction.channel.send(embed=embed, view=PlayerTagView(session_data, index))

    async def finalize_collection(self, interaction, session_data):
        # Create Private Thread
        thread = await interaction.channel.create_thread(name=f"Interview - {interaction.user.name}", type=discord.ChannelType.private_thread)
        session_data["thread_id"] = thread.id
        
        # Post Stats and Screenshots to Thread
        for acc in session_data["accounts"]:
            player = acc['stats']
            
            # Safe access to attributes
            weapon = getattr(player, "town_hall_weapon", None)
            weapon_str = f" (Weapon: {weapon})" if weapon else ""
            
            stats_embed = discord.Embed(title=f"Stats for {acc['name']} ({acc['tag']})", color=discord.Color.green())
            stats_embed.add_field(name="Town Hall", value=f"{player.town_hall}{weapon_str}", inline=True)
            stats_embed.add_field(name="XP Level", value=str(player.exp_level), inline=True)
            stats_embed.add_field(name="Trophies", value=str(player.trophies), inline=True)
            stats_embed.add_field(name="War Stars", value=str(player.war_stars), inline=True)
            
            heroes = "\n".join([f"{h.name}: {h.level}" for h in player.heroes]) if player.heroes else "None"
            stats_embed.add_field(name="Heroes", value=heroes, inline=False)
            
            await thread.send(embed=stats_embed)
            if 'screenshot_url' in acc:
                await thread.send(f"**Base Screenshot for {acc['name']}**:\n{acc['screenshot_url']}")
        
        # Start Interview Questions in Main Channel
        await interaction.channel.send("Thank you for the details. Let's proceed with a few questions.")
        
        questions = await mongo_manager.get_questions("join_clan")
        if not questions:
            questions = ["Why do you want to join?", "Do you have Discord notifications on?"]
        
        session_data["answers"] = []
        session_data["answers"] = []
        
        cog = interaction.client.get_cog("TicketSystemCog")
        if cog:
            await cog.ask_question(interaction, session_data, questions, 0)

class QuestionDoneView(discord.ui.View):
    def __init__(self, session_data, questions, index, cog_instance):
        super().__init__(timeout=None)
        self.session_data = session_data
        self.questions = questions
        self.index = index
        self.cog_instance = cog_instance
        self.start_time = datetime.now()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session_data.get("user_id") and interaction.user.id != self.session_data["user_id"]:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Done", style=discord.ButtonStyle.success)
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Collect messages sent by user since start_time
        messages = []
        async for msg in interaction.channel.history(after=self.start_time):
            if msg.author.id == interaction.user.id:
                messages.append(msg.content)
        
        if not messages:
            await interaction.response.send_message("❌ You must provide an answer before clicking Done!", ephemeral=True)
            return

        answer = "\n".join(messages)
        self.session_data["answers"].append({"question": self.questions[self.index], "answer": answer})
        
        await interaction.response.edit_message(view=None) # Remove button
        await self.cog_instance.ask_question(interaction, self.session_data, self.questions, self.index + 1)

class PlayerTagView(discord.ui.View):
    def __init__(self, session_data, index):
        super().__init__(timeout=None)
        self.session_data = session_data
        self.index = index

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session_data.get("user_id") and interaction.user.id != self.session_data["user_id"]:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Enter Tag", style=discord.ButtonStyle.primary)
    async def enter_tag(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerTagModal(self.session_data, self.index))

class PlayerTagModal(discord.ui.Modal, title="Enter Player Tag"):
    tag = discord.ui.TextInput(label="Player Tag", placeholder="#ABC123")

    def __init__(self, session_data, index):
        super().__init__()
        self.session_data = session_data
        self.index = index

    async def on_submit(self, interaction: discord.Interaction):
        tag = self.tag.value.upper().replace("#", "")
        
        # Fetch Stats using CoC API
        player = await coc_api.get_player(tag)
        
        if player:
            name = player.name
            th = player.town_hall
            
            # CHECK GLOBAL MIN TH
            clans = await mongo_manager.get_clans()
            if clans:
                # Filter visible clans only? User said "lowest town hall accepting clan".
                # Probably should check all active/visible clans.
                min_th_global = min([int(c.get('min_th', 99)) for c in clans if c.get('visible', True)], default=0)
                
                if th < min_th_global:
                     # IMMEDIATE REJECTION
                    criteria_embed = discord.Embed(
                        title="Criteria Mismatch",
                        description=f"Hello **{name}**,\n\nUnfortunately, your Town Hall level (**TH{th}**) does not meet the minimum requirement of **TH{min_th_global}** established for our clan family.",
                        color=discord.Color.red()
                    )
                    criteria_embed.add_field(name="Account", value=f"{name} ({tag})", inline=True)
                    criteria_embed.add_field(name="Your TH", value=str(th), inline=True)
                    criteria_embed.add_field(name="Required TH", value=str(min_th_global), inline=True)
                    
                    await interaction.response.send_message(embed=criteria_embed)
                    
                    # Add as rejected so we don't break the loop count
                    account_data = {
                        "tag": "rejected",
                        "name": name,
                        "th": th,
                        "stats": player,
                        "selected_clan_tag": "rejected" 
                    }
                    self.session_data["accounts"].append(account_data)
                    
                    # Next account
                    next_index = self.index + 1
                    if next_index < self.session_data["account_count"]:
                         embed = discord.Embed(title=f"Account #{next_index + 1} Details", description="Please enter the Player Tag for this account.", color=discord.Color.blue())
                         await interaction.channel.send(embed=embed, view=PlayerTagView(self.session_data, next_index))
                    else:
                         await finalize_collection_standalone(interaction, self.session_data)
                    return

            account_data = {
                "tag": f"#{player.tag.strip('#')}",
                "name": name,
                "th": th,
                "stats": player # Store full player object (or dict representation if needed)
            }
            
            # Account Found Embed
            found_embed = discord.Embed(
                title="Player Found",
                description=f"We found **{name}** (TH{th})!",
                color=discord.Color.blue()
            )
            found_embed.add_field(name="Next Step", value="Please upload a screenshot of your base now.")
            await interaction.response.send_message(embed=found_embed)
            
            try:
                msg = await interaction.client.wait_for('message', check=lambda m: m.channel.id == interaction.channel.id and m.attachments and m.author.id == interaction.user.id, timeout=120)
                account_data["screenshot_url"] = msg.attachments[0].url
                
                # Screenshot Received Embed
                ss_embed = discord.Embed(
                    title="Screenshot Received",
                    description="✅ Your base screenshot has been uploaded successfully.",
                    color=discord.Color.green()
                )
                await interaction.channel.send(embed=ss_embed)
            except asyncio.TimeoutError:
                # No Screenshot Embed
                no_ss_embed = discord.Embed(
                    title="No Screenshot",
                    description="⚠️ No screenshot was detected. Proceeding without one.",
                    color=discord.Color.orange()
                )
                await interaction.channel.send(embed=no_ss_embed)
            
            self.session_data["accounts"].append(account_data)
            
            # Next account
            next_index = self.index + 1
            if next_index < self.session_data["account_count"]:
                 embed = discord.Embed(title=f"Account #{next_index + 1} Details", description="Please enter the Player Tag for this account.", color=discord.Color.blue())
                 await interaction.channel.send(embed=embed, view=PlayerTagView(self.session_data, next_index))
            else:
                 await finalize_collection_standalone(interaction, self.session_data)

        else:
            await interaction.response.send_message("Invalid Tag or API Error. Please try again.", ephemeral=True)

# --- Emoji Helpers ---
def get_emoji_str(bot, name):
    # 1. Try Asset Server (Exact)
    asset_guild = bot.get_guild(1360555270048055366)
    if asset_guild:
        emoji = discord.utils.get(asset_guild.emojis, name=name)
        if emoji: return str(emoji)
    
    # 2. Try Global (Exact)
    emoji = discord.utils.get(bot.emojis, name=name)
    if emoji: return str(emoji)
    
    # 3. Try Asset Server (Case Insensitive)
    if asset_guild:
        for e in asset_guild.emojis:
            if e.name.lower() == name.lower():
                return str(e)

    # 4. Try Global (Case Insensitive)
    for e in bot.emojis:
        if e.name.lower() == name.lower():
            return str(e)

    return ""

def map_league_name(name):
    s = name.replace(" League", "").strip()
    league_emoji_name = s.replace(" ", "")

    # Gold Special Case
    if "Gold" in name:
            if " I" in name and "II" not in name: league_emoji_name = "Gold1"
            elif name.endswith(" I"): league_emoji_name = "Gold1"
            else: league_emoji_name = "Gold2"
    else:
        # Standard Roman Map
        roman_map = {"I": "1", "II": "2", "III": "3"}
        parts = s.split(" ")
        if len(parts) == 2 and parts[1] in roman_map:
            league_emoji_name = f"{parts[0]}{roman_map[parts[1]]}"
    
    return league_emoji_name

async def finalize_collection_standalone(interaction, session_data):
    # This is a hack to bridge the gap between Modal (no cog instance) and Cog methods.
    # Ideally we pass cog instance to View/Modal.
    # For now, we just instantiate a dummy view to call the method if we can, or just copy logic.
    # But wait, we can get the Cog from the bot instance if we had it.
    # Let's just use the same logic as AccountCountView.finalize_collection but we need to re-instantiate it or move it to a standalone function.
    # Moving to standalone function `finalize_collection_logic` is best.
    pass # We will use the method in AccountCountView by passing the cog instance to views.
    # Actually, I'll just make the Modal call a helper function that does what `finalize_collection` does.

    # Re-implementing the logic here for simplicity in this artifact context
    thread = await interaction.channel.create_thread(name=f"Interview - {interaction.user.name}", type=discord.ChannelType.private_thread)
    session_data["thread_id"] = thread.id
    
    for acc in session_data["accounts"]:
        if acc.get("selected_clan_tag") == "rejected":
            await thread.send(f"⚠️ **Account Skipped:** {acc['name']} (TH{acc['th']}) - Does not meet minimum requirements.")
            continue
            
        player = acc['stats']
        
        # Safe access to attributes
        weapon = getattr(player, "town_hall_weapon", None)
        weapon_str = f" (Weapon: {weapon})" if weapon else ""
        
        stats_embed = discord.Embed(title=f"Stats for {acc['name']} ({acc['tag']})", color=discord.Color.green())
        stats_embed.add_field(name="Town Hall", value=f"{player.town_hall}{weapon_str}", inline=True)
        stats_embed.add_field(name="XP Level", value=str(player.exp_level), inline=True)
        stats_embed.add_field(name="Trophies", value=str(player.trophies), inline=True)
        stats_embed.add_field(name="War Stars", value=str(player.war_stars), inline=True)
        
        heroes = "\n".join([f"{h.name}: {h.level}" for h in player.heroes]) if player.heroes else "None"
        stats_embed.add_field(name="Heroes", value=heroes, inline=False)
        
        # coc.py uses 'pets' or 'hero_pets' depending on version, usually 'pets' in v2
        pets_list = getattr(player, "pets", []) or getattr(player, "hero_pets", [])
        pets = "\n".join([f"{p.name}: {p.level}" for p in pets_list]) if pets_list else "None"
        stats_embed.add_field(name="Pets", value=pets, inline=False)
        
        await thread.send(embed=stats_embed)
        if 'screenshot_url' in acc:
            await thread.send(f"**Base Screenshot for {acc['name']}**:\n{acc['screenshot_url']}")
            
    # Check if ALL accounts are rejected
    if all(acc.get("selected_clan_tag") == "rejected" for acc in session_data["accounts"]):
        # All accounts failed criteria -> Final Rejection
        rejection_embed = create_rejection_embed("Blackspire Nation", session_data["user_id"])
        await interaction.channel.send(embed=rejection_embed)
        return

    # Proceed to Questions Embed
    proceed_embed = discord.Embed(
        title="Details Collected",
        description="Thank you for providing your account details. We will now proceed with a brief interview.",
        color=discord.Color.purple()
    )
    await interaction.channel.send(embed=proceed_embed)
    
    questions = await mongo_manager.get_questions("join_clan")
    if not questions:
        questions = ["Why do you want to join?", "Do you have Discord notifications on?"]
        
    session_data["answers"] = []
    # We need to start the question loop. We can't easily call Cog method here without the instance.
    # I will modify the views to accept `cog_instance`.
    # But for this artifact, I will assume the Modal has access or I will use a global/static approach.
    # Let's use `interaction.client.get_cog("TicketSystemCog")`.
    cog = interaction.client.get_cog("TicketSystemCog")
    if cog:
        await cog.ask_question(interaction, session_data, questions, 0)

class ClanSelectionView(discord.ui.View):
    def __init__(self, session_data, account_index, regular_clans, feeder_clans, cog_instance, is_reselection=False):
        super().__init__(timeout=None)
        self.session_data = session_data
        self.account_index = account_index
        self.cog_instance = cog_instance
        self.is_reselection = is_reselection
        
        options = []
        
        # Regular Clans Block
        if regular_clans:
            options.append(discord.SelectOption(
                label="--- REGULAR CLANS ---",
                value="HEADER_REGULAR",
                description="Main Family Clans",
                emoji="🛡️"
            ))
            for c in regular_clans:
                 options.append(self.create_clan_option(c))
        
        # Feeder Clans Block
        if feeder_clans:
            options.append(discord.SelectOption(
                label="--- FEEDER CLANS ---",
                value="HEADER_FEEDER",
                description="Development & Feeder Clans",
                emoji="🎓"
            ))
            for c in feeder_clans:
                 options.append(self.create_clan_option(c))

        # Truncate if too many (Discord max 25)
        # We prioritize showing clans over headers if tight, but unlikely for now
        if len(options) > 25:
             options = options[:25]
        
        if not options:
             options.append(discord.SelectOption(label="No suitable clans found", value="none"))
        
        self.select_clan.options = options

    def create_clan_option(self, c):
        # Determine Emoji
        emoji = "🛡️" 
        sanitized_name = c['name'].replace(" ", "").lower()
        sanitized_tag = c['clan_tag'].replace("#", "").lower()
        
        # Priority 1: Custom Emoji (Name or Tag)
        e_str = get_emoji_str(self.cog_instance.bot, sanitized_name)
        if not e_str: 
            e_str = get_emoji_str(self.cog_instance.bot, sanitized_tag)
        
        # Priority 2: League Emoji
        if not e_str:
            raw_league = c.get('war_league', 'Unranked')
            league_emoji_name = map_league_name(raw_league)
            e_str = get_emoji_str(self.cog_instance.bot, league_emoji_name)
        
        if e_str:
             emoji = discord.PartialEmoji.from_str(e_str)

        # Description
        league_text = f"{c.get('war_league', 'Unranked')}"
        min_th = c.get('min_th', 1)
        ch_level = c.get('capital_hall', '0')
        desc = f'{league_text} | TH{min_th}+ | CH {ch_level}'
        
        return discord.SelectOption(
            label=c['name'], 
            value=c['clan_tag'], 
            description=desc,
            emoji=emoji
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.session_data.get("user_id") and interaction.user.id != self.session_data["user_id"]:
            await interaction.response.send_message("This control is not for you.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Select Clan")
    async def select_clan(self, interaction: discord.Interaction, select: discord.ui.Select):
        clan_tag = select.values[0]
        
        # Check for Headers
        if clan_tag.startswith("HEADER_"):
            await interaction.response.send_message("⚠️ Please select a **valid clan** from the list, not the category header.", ephemeral=True)
            # Reset view to allow re-selection (Select menu stays stuck on value otherwise in some clients, but usually OK to just reply ephemeral and let them pick again)
            return

        if clan_tag == "none":
            # REJECTION FLOW
            acc = self.session_data["accounts"][self.account_index]
            
            # Send Rejection Embed directly to user (Ephemeral or DMs? User asked for "reject player thing")
            # Usually strict rejection is sent to the thread/channel.
            rejection_embed = create_rejection_embed("Blackspire Nation", self.session_data["user_id"])
            await interaction.channel.send(content=f"<@{self.session_data['user_id']}>", embed=rejection_embed)
            
            await interaction.response.send_message(f"Marked {acc['name']} as rejected due to no suitable clans.", ephemeral=True)
            
            # Mark as rejected in session data (or just don't add selected_clan_tag)
            self.session_data["accounts"][self.account_index]["selected_clan_tag"] = "rejected"
        else:
            self.session_data["accounts"][self.account_index]["selected_clan_tag"] = clan_tag
            # Reset status to pending just in case
            self.session_data["accounts"][self.account_index]["status"] = "pending"
            await interaction.response.edit_message(content=f"Selected clan: {clan_tag}", view=None)
        
        if self.is_reselection:
            # STOP LOOP, PROCESS RE-APP
            await self.cog_instance.submit_reapplication(interaction, self.session_data, self.account_index)
        else:
            # Next account
            await self.cog_instance.start_clan_selection(interaction, self.session_data, self.account_index + 1)

class ApprovalView(discord.ui.View):
    def __init__(self, session_data, clans):
        super().__init__(timeout=None)
        self.session_data = session_data
        self.clans = clans
        
        # Add dynamic buttons for each account
        for i, acc in enumerate(session_data["accounts"]):
            # Check status - if already accepted/rejected, don't show buttons
            status = acc.get("status", "pending")
            if status != "pending":
                continue

            clan_tag = acc.get("selected_clan_tag")
            if clan_tag and clan_tag != "none" and clan_tag != "rejected":
                clan = next((c for c in clans if c['clan_tag'] == clan_tag), None)
                clan_name = clan['name'] if clan else clan_tag
                
                # Accept Button
                accept_btn = discord.ui.Button(label=f"Accept {acc['name']} -> {clan_name}", style=discord.ButtonStyle.success, custom_id=f"accept_{i}")
                accept_btn.callback = self.make_accept_callback(i, clan)
                self.add_item(accept_btn)
                
                # Pass Button
                pass_btn = discord.ui.Button(label=f"Pass {acc['name']}", style=discord.ButtonStyle.danger, custom_id=f"pass_{i}")
                pass_btn.callback = self.make_pass_callback(i, clan)
                self.add_item(pass_btn)

    def make_accept_callback(self, index, clan):
        async def callback(interaction: discord.Interaction):
            # Permission check
            if not self.check_permission(interaction, clan):
                error_embed = discord.Embed(
                    title="⚠️ Unauthorized Action ⚠️",
                    description=f"{interaction.user.mention}, hold your horses! 🐴\nYou aren't a leader of **{clan['name']}**.\n\n**Guilty as charged!** 🛑 Please avoid messing with other clans' tickets.",
                    color=discord.Color.red()
                )
                error_embed.set_footer(text="This incident has been logged. (Just kidding, but seriously, don't.)")
                await interaction.response.send_message(embed=error_embed)
                return
            
            acc = self.session_data["accounts"][index]
            
            # Use Logo URL directly (User explicitly requested NO fallback to badge)
            logo_url = clan.get('logo_url')
            
            embed = create_invite_embed(
                clan_name=clan['name'],
                leader_id=clan.get('leader_id'),
                leadership_role_id=clan.get('leadership_role_id'),
                logo_url=logo_url,
                inviter_mention=interaction.user.mention
            )
            
            button = discord.ui.Button(label="Join Clan", style=discord.ButtonStyle.link, url=clan.get('clan_link', 'https://clashofclans.com'))
            view = discord.ui.View()
            view.add_item(button)
            
            # Send to MAIN CHANNEL (not thread)
            main_channel = interaction.channel.parent
            if main_channel:
                await main_channel.send(content=f"Clan Invitation for <@{self.session_data['user_id']}>", embed=embed, view=view)
            
            # Mark as accepted
            self.session_data["accounts"][index]["status"] = "accepted"

            await interaction.response.send_message(f"Accepted {acc['name']}!", ephemeral=True)
            
            # Disable buttons for this account
            for child in self.children:
                if isinstance(child, discord.ui.Button) and (child.custom_id == f"accept_{index}" or child.custom_id == f"pass_{index}"):
                    child.disabled = True
            await interaction.message.edit(view=self)

        return callback

    def make_pass_callback(self, index, clan):
        async def callback(interaction: discord.Interaction):
            if not self.check_permission(interaction, clan):
                error_embed = discord.Embed(
                    title="⚠️ Unauthorized Action ⚠️",
                    description=f"{interaction.user.mention}, hold your horses! 🐴\nYou aren't a leader of **{clan['name']}**.\n\n**Guilty as charged!** 🛑 Please avoid messing with other clans' tickets.",
                    color=discord.Color.red()
                )
                error_embed.set_footer(text="This incident has been logged. (Just kidding, but seriously, don't.)")
                await interaction.response.send_message(embed=error_embed)
                return
            
            acc = self.session_data["accounts"][index]
            
            # Send rejection to MAIN CHANNEL
            main_channel = interaction.channel.parent
            if main_channel:
                # Reverted to simple message as requested
                await main_channel.send(f"Sorry <@{self.session_data['user_id']}>, your application for {acc['name']} to {clan['name']} was passed. Please select another clan.")
            
            # Re-trigger selection for this account ONLY (is_reselection=True)
            cog = interaction.client.get_cog("TicketSystemCog")
            if cog and main_channel:
                 # Call with is_reselection=True to prevent loop
                 await cog.send_clan_selection(main_channel, self.session_data, index, is_reselection=True)

            await interaction.response.send_message(f"Passed {acc['name']}.", ephemeral=True)
            
            # Disable buttons for this account
            # We must iterate over self.children which contains the buttons
            for child in self.children:
                if isinstance(child, discord.ui.Button) and (child.custom_id == f"accept_{index}" or child.custom_id == f"pass_{index}"):
                    child.disabled = True
            
            # Update the view on the message
            await interaction.message.edit(view=self)

        return callback

    def check_permission(self, interaction, clan):
        if not clan: return False
        user_role_ids = [r.id for r in interaction.user.roles]
        role_id = int(clan.get('leadership_role_id', 0))
        leader_id = int(clan.get('leader_id', 0))
        
        print(f"DEBUG: Checking permission for {interaction.user.name} ({interaction.user.id})")
        print(f"DEBUG: User Roles: {user_role_ids}")
        print(f"DEBUG: Required Role: {role_id}, Leader ID: {leader_id}")
        
        is_authorized = role_id in user_role_ids or interaction.user.id == leader_id
        print(f"DEBUG: Authorized: {is_authorized}")
        
        return is_authorized

async def setup(bot):
    await bot.add_cog(TicketSystemCog(bot))

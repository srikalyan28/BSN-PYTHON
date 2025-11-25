import discord
from discord.ext import commands
from discord import app_commands
from utils.mongo_manager import mongo_manager

class CountingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.milestones = {
            69: "Nice! 😎",
            100: "🎉 Century mark! Keep counting!",
            111: "All ones! 1️⃣1️⃣1️⃣",
            222: "All twos! 2️⃣2️⃣2️⃣",
            333: "All threes! 3️⃣3️⃣3️⃣",
            444: "All fours! 4️⃣4️⃣4️⃣",
            500: "Half a thousand! You're doing great! 🌟",
            555: "All fives! 5️⃣5️⃣5️⃣",
            666: "Spooky number! 👻",
            777: "Lucky sevens! 🎰",
            888: "All eights! 8️⃣8️⃣8️⃣",
            999: "All nines! 9️⃣9️⃣9️⃣",
            1000: "🎊 ONE THOUSAND! What an achievement!",
            1234: "Sequential! 1-2-3-4! 🔢",
            2000: "Two thousand! The future is here! 🚀",
            3000: "Three thousand! You're unstoppable! 💪",
            5000: "FIVE THOUSAND! Legendary counting! 👑",
            8888: "Quadruple eights! 8️⃣8️⃣8️⃣8️⃣ So satisfying!",
            9000: "IT'S OVER 9000!!! 💥",
            9999: "One away from 10k! The tension! 😬",
            10000: "🎆 TEN THOUSAND! You've reached counting greatness! 🏆",
            11111: "All ones! 1️⃣1️⃣1️⃣1️⃣1️⃣",
            12345: "Perfect sequence! 1-2-3-4-5! 🎯",
            15000: "Fifteen thousand! Halfway to 30k! 🌈",
            20000: "TWENTY THOUSAND! Double digits! 🎊",
            22222: "All twos! 2️⃣2️⃣2️⃣2️⃣2️⃣",
            25000: "Quarter of 100k! You're amazing! 🌟",
            30000: "THIRTY THOUSAND! Incredible dedication! 💎",
            33333: "All threes! 3️⃣3️⃣3️⃣3️⃣3️⃣",
            44444: "All fours! 4️⃣4️⃣4️⃣4️⃣4️⃣",
            50000: "FIFTY THOUSAND! Half a century of thousands! 🏅",
            55555: "All fives! 5️⃣5️⃣5️⃣5️⃣5️⃣",
            66666: "All sixes! 6️⃣6️⃣6️⃣6️⃣6️⃣",
            69420: "The ultimate meme number! Nice and blazing! 😎🔥",
            77777: "All sevens! 7️⃣7️⃣7️⃣7️⃣7️⃣ JACKPOT!",
            88888: "All eights! 8️⃣8️⃣8️⃣8️⃣8️⃣",
            99999: "All nines! 9️⃣9️⃣9️⃣9️⃣9️⃣",
            100000: "💯 ONE HUNDRED THOUSAND! LEGENDARY STATUS ACHIEVED! 👑🎆🏆"
        }

    @app_commands.command(name="setup_counting", description="Set the current channel as the counting channel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_counting(self, interaction: discord.Interaction):
        await mongo_manager.set_counting_channel(interaction.guild.id, interaction.channel.id)
        await interaction.response.send_message(f"✅ Counting channel set to {interaction.channel.mention}. Start counting from 1!", ephemeral=True)

    @app_commands.command(name="disable_counting", description="Disable counting for this server.")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_counting(self, interaction: discord.Interaction):
        await mongo_manager.remove_counting_channel(interaction.guild.id)
        await interaction.response.send_message("✅ Counting disabled.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Check if this is a counting channel
        data = await mongo_manager.get_counting_channel(message.guild.id)
        if not data or data['channel_id'] != message.channel.id:
            return

        content = message.content.strip()
        
        # Validate if it's a number
        if not content.isdigit():
            await message.delete()
            await message.channel.send(f"{message.author.mention}, this channel supports only numbers!", delete_after=5)
            return

        number = int(content)
        current_count = data.get('current_count', 0)
        expected_number = current_count + 1

        # Validate sequence
        if number != expected_number:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, wrong number! The next number is **{expected_number}**.", delete_after=5)
            return

        # Validate double counting
        if data.get('last_user_id') == message.author.id:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, you can't count twice in a row! Wait for someone else.", delete_after=5)
            return

        # Success! Update DB and React
        await mongo_manager.update_count(message.guild.id, number, message.author.id)
        await message.add_reaction("✅")

        # Check Milestones
        if number in self.milestones:
            await message.channel.send(f"{self.milestones[number]} (Reached by {message.author.mention})")

async def setup(bot):
    await bot.add_cog(CountingCog(bot))

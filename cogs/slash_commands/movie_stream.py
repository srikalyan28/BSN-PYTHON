import discord
from discord.ext import commands
from discord import app_commands

# Hardcoded list of allowed user IDs (owners/admins)
ALLOWED_USER_IDS = [
    123456789012345678,  # Replace with your Discord user ID
    987654321098765432,
    1272176835769405552,  # Add more admin IDs as needed
]

class MovieStream(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="post_movie_stream", description="Post an upcoming movie stream announcement.")
    @app_commands.describe(
        movie_name="Name of the movie",
        poster_url="Direct URL to the movie poster image",
        timestamp="Timestamp (use Discord timestamp generator)",
    )
    async def post_movie_stream(self, interaction: discord.Interaction, movie_name: str, poster_url: str, timestamp: str):
        # Permission check
        if interaction.user.id not in ALLOWED_USER_IDS:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🎬 Upcoming Movie Stream: {movie_name}",
            description=f"**Movie:** {movie_name}\n**Time:** {timestamp}\n\nGet your popcorn ready! 🍿",
            color=discord.Color.dark_red()
        )
        embed.set_image(url=poster_url)
        embed.set_footer(text="Hosted by the Movie Night Team")
        embed.set_author(name="Movie Night", icon_url="https://cdn-icons-png.flaticon.com/512/833/833314.png")

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(MovieStream(bot))

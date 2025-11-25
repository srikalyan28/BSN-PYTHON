import coc
import os
from dotenv import load_dotenv

load_dotenv(override=True)

class CoCClient:
    def __init__(self):
        self.client = coc.Client()
        self.token = os.getenv("COC_API_TOKEN")
        self._is_logged_in = False

    async def ensure_login(self):
        if not self._is_logged_in:
            if not self.token:
                self.token = os.getenv("COC_API_TOKEN")
            
            if self.token:
                try:
                    await self.client.login_with_tokens(self.token.strip())
                    self._is_logged_in = True
                    print("Logged in to CoC API via coc.py")
                except coc.InvalidCredentials:
                    print("Invalid CoC API Token.")
                except Exception as e:
                    print(f"Failed to login to CoC API: {e}")
            else:
                print("No CoC API Token found.")

    async def get_player(self, tag):
        await self.ensure_login()
        if not self._is_logged_in:
            return None

        try:
            player = await self.client.get_player(tag)
            return player
        except coc.NotFound:
            print(f"Player {tag} not found.")
            return None
        except Exception as e:
            print(f"Error fetching player {tag}: {e}")
            return None

    async def get_clan(self, tag):
        await self.ensure_login()
        if not self._is_logged_in:
            return None

        try:
            clan = await self.client.get_clan(tag)
            return clan
        except coc.NotFound:
            print(f"Clan {tag} not found.")
            return None
        except Exception as e:
            print(f"Error fetching clan {tag}: {e}")
            return None

    async def close(self):
        await self.client.close()

coc_api = CoCClient()

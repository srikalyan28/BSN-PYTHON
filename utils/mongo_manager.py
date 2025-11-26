import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

class MongoManager:
    def __init__(self):
        self.uri = os.getenv("MONGO_URI")
        self.db_name = os.getenv("MONGO_DB_NAME")
        self.client = None
        self.db = None

    async def connect(self):
        if not self.uri:
            print("Error: MONGO_URI not found in environment variables.")
            return
        
        try:
            self.client = AsyncIOMotorClient(self.uri)
            self.db = self.client[self.db_name]
            print(f"Connected to MongoDB: {self.db_name}")
        except Exception as e:
            print(f"Failed to connect to MongoDB: {e}")

    async def get_collection(self, collection_name):
        if self.db is None:
            await self.connect()
        return self.db[collection_name]

    async def save_questions(self, ticket_type, questions):
        if self.db is None:
            await self.connect()
        collection = self.db["questions"]
        await collection.update_one(
            {"ticket_type": ticket_type},
            {"$set": {"questions": questions}},
            upsert=True
        )

    async def get_questions(self, ticket_type):
        if self.db is None:
            await self.connect()
        collection = self.db["questions"]
        doc = await collection.find_one({"ticket_type": ticket_type})
        return doc["questions"] if doc else []

    async def save_clan(self, clan_data):
        if self.db is None:
            await self.connect()
        collection = self.db["clans"]
        # Assuming clan_tag is unique
        await collection.update_one(
            {"clan_tag": clan_data["clan_tag"]},
            {"$set": clan_data},
            upsert=True
        )

    async def update_clan_field(self, clan_tag, field, value):
        if self.db is None:
            await self.connect()
        collection = self.db["clans"]
        await collection.update_one(
            {"clan_tag": clan_tag},
            {"$set": {field: value}}
        )

    async def get_clans(self):
        if self.db is None:
            await self.connect()
        collection = self.db["clans"]
        cursor = collection.find({})
        clans = []
        async for clan in cursor:
            clans.append(clan)
        return clans

    async def delete_clan(self, clan_tag):
        if self.db is None:
            await self.connect()
        collection = self.db["clans"]
        await collection.delete_one({"clan_tag": clan_tag})

    async def get_counting_channel(self, guild_id):
        if self.db is None:
            await self.connect()
        collection = self.db["counting_channels"]
        return await collection.find_one({"guild_id": guild_id})

    async def set_counting_channel(self, guild_id, channel_id):
        if self.db is None:
            await self.connect()
        collection = self.db["counting_channels"]
        await collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"channel_id": channel_id, "current_count": 0, "last_user_id": None}},
            upsert=True
        )

    async def remove_counting_channel(self, guild_id):
        if self.db is None:
            await self.connect()
        collection = self.db["counting_channels"]
        await collection.delete_one({"guild_id": guild_id})

    async def update_count(self, guild_id, new_count, user_id):
        if self.db is None:
            await self.connect()
        collection = self.db["counting_channels"]
        await collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"current_count": new_count, "last_user_id": user_id}}
        )

    async def save_buc_team(self, team_data):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_teams"]
        await collection.update_one(
            {"name": team_data["name"]},
            {"$set": team_data},
            upsert=True
        )

    async def get_buc_teams(self):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_teams"]
        cursor = collection.find({})
        teams = []
        async for team in cursor:
            teams.append(team)
        return teams

    async def delete_buc_team(self, team_name):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_teams"]
        await collection.delete_one({"name": team_name})

    async def save_buc_match(self, match_data):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_matches"]
        await collection.update_one(
            {"id": match_data["id"]},
            {"$set": match_data},
            upsert=True
        )

    async def get_buc_matches(self):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_matches"]
        cursor = collection.find({})
        matches = []
        async for match in cursor:
            matches.append(match)
        return matches

    async def delete_buc_match(self, match_id):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_matches"]
        await collection.delete_one({"id": match_id})

    async def save_buc_settings(self, settings):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_settings"]
        await collection.update_one(
            {"type": "general"},
            {"$set": settings},
            upsert=True
        )

    async def get_buc_settings(self):
        if self.db is None:
            await self.connect()
        collection = self.db["buc_settings"]
        return await collection.find_one({"type": "general"})

    async def save_bsn_team(self, team_data):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_teams"]
        await collection.update_one(
            {"name": team_data["name"]},
            {"$set": team_data},
            upsert=True
        )

    async def get_bsn_teams(self):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_teams"]
        cursor = collection.find({})
        teams = []
        async for team in cursor:
            teams.append(team)
        return teams

    async def delete_bsn_team(self, team_name):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_teams"]
        await collection.delete_one({"name": team_name})

    async def save_bsn_pending_team(self, team_data):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_pending_teams"]
        await collection.update_one(
            {"name": team_data["name"]},
            {"$set": team_data},
            upsert=True
        )

    async def get_bsn_pending_team(self, team_name):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_pending_teams"]
        return await collection.find_one({"name": team_name})

    async def delete_bsn_pending_team(self, team_name):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_pending_teams"]
        await collection.delete_one({"name": team_name})

    async def save_bsn_match(self, match_data):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_matches"]
        await collection.update_one(
            {"id": match_data["id"]},
            {"$set": match_data},
            upsert=True
        )

    async def get_bsn_matches(self):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_matches"]
        cursor = collection.find({})
        matches = []
        async for match in cursor:
            matches.append(match)
        return matches

    async def delete_bsn_match(self, match_id):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_matches"]
        await collection.delete_one({"id": match_id})

    async def save_bsn_settings(self, settings):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_settings"]
        await collection.update_one(
            {"type": "general"},
            {"$set": settings},
            upsert=True
        )

    async def get_bsn_settings(self):
        if self.db is None:
            await self.connect()
        collection = self.db["bsn_settings"]
        return await collection.find_one({"type": "general"})

mongo_manager = MongoManager()

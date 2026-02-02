from utils.mongo_manager import mongo_manager
import datetime

class CWLModels:
    """
    Handles all database interactions for the CWL Management System.
    Uses new collections: cwl_seasons, cwl_managers, cwl_representatives, cwl_forums, cwl_assignments.
    """
    
    # --- SEASONS ---
    @staticmethod
    async def get_active_season():
        db = await mongo_manager.get_collection("cwl_seasons")
        return await db.find_one({"status": "active"})

    @staticmethod
    async def set_active_season(season_name):
        db = await mongo_manager.get_collection("cwl_seasons")
        # Archive current active season
        await db.update_many({"status": "active"}, {"$set": {"status": "archived"}})
        # Set new season
        await db.update_one(
            {"season": season_name},
            {"$set": {"status": "active", "created_at": datetime.datetime.utcnow()}},
            upsert=True
        )

    # --- MANAGERS ---
    @staticmethod
    async def add_manager(user_id=None, role_id=None):
        db = await mongo_manager.get_collection("cwl_managers")
        data = {"created_at": datetime.datetime.utcnow()}
        if user_id: data["user_id"] = user_id
        if role_id: data["role_id"] = role_id
        await db.insert_one(data)

    @staticmethod
    async def remove_manager(user_id=None, role_id=None):
        db = await mongo_manager.get_collection("cwl_managers")
        query = {}
        if user_id: query["user_id"] = user_id
        if role_id: query["role_id"] = role_id
        if query: await db.delete_one(query)

    @staticmethod
    async def get_managers():
        db = await mongo_manager.get_collection("cwl_managers")
        cursor = db.find({})
        return [doc async for doc in cursor]

    # --- REPRESENTATIVES ---
    @staticmethod
    async def add_rep(season, clan_tag, user_id):
        db = await mongo_manager.get_collection("cwl_representatives")
        await db.update_one(
            {"season": season, "clan_tag": clan_tag},
            {"$addToSet": {"user_ids": user_id}},
            upsert=True
        )

    @staticmethod
    async def remove_rep(season, clan_tag, user_id):
        db = await mongo_manager.get_collection("cwl_representatives")
        await db.update_one(
            {"season": season, "clan_tag": clan_tag},
            {"$pull": {"user_ids": user_id}}
        )

    @staticmethod
    async def get_reps(season, clan_tag):
        db = await mongo_manager.get_collection("cwl_representatives")
        doc = await db.find_one({"season": season, "clan_tag": clan_tag})
        return doc["user_ids"] if doc else []

    @staticmethod
    async def get_all_reps(season):
        db = await mongo_manager.get_collection("cwl_representatives")
        cursor = db.find({"season": season})
        return [doc async for doc in cursor]

    # --- FORUMS ---
    @staticmethod
    async def save_forum(season, clan_tag, data):
        db = await mongo_manager.get_collection("cwl_forums")
        update_data = {
            "season": season,
            "clan_tag": clan_tag,
            "updated_at": datetime.datetime.utcnow(),
            **data
        }
        await db.update_one(
            {"season": season, "clan_tag": clan_tag},
            {"$set": update_data},
            upsert=True
        )

    @staticmethod
    async def get_forum(season, clan_tag):
        db = await mongo_manager.get_collection("cwl_forums")
        return await db.find_one({"season": season, "clan_tag": clan_tag})

    # --- ASSIGNMENTS ---
    @staticmethod
    async def add_assignment(season, player_tag, source_clan, dest_clan, th_level, player_name):
        db = await mongo_manager.get_collection("cwl_assignments")
        await db.update_one(
            {"season": season, "player_tag": player_tag},
            {"$set": {
                "source_clan": source_clan,
                "dest_clan": dest_clan,
                "town_hall": th_level,
                "player_name": player_name,
                "updated_at": datetime.datetime.utcnow()
            }},
            upsert=True
        )

    @staticmethod
    async def get_assignments(season, dest_clan=None):
        db = await mongo_manager.get_collection("cwl_assignments")
        query = {"season": season}
        if dest_clan:
            query["dest_clan"] = dest_clan
        
        cursor = db.find(query)
        return [doc async for doc in cursor]

cwl_models = CWLModels()

async def setup(bot):
    pass

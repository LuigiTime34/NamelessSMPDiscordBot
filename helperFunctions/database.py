import sqlite3

from const import DATABASE_PATH, MINECRAFT_TO_DISCORD

def initializeDatabase():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        # Create tables if they don't exist
        tables = ["minecraft_to_discord", "deaths", "advancements"]
        for table in tables:
            cursor.execute(f'SELECT name FROM sqlite_master WHERE type="table" AND name="{table}";')
            if cursor.fetchone() is None:
                print(f"Creating table {table}")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS minecraft_to_discord (
                discord_name TEXT NOT NULL PRIMARY KEY,
                minecraft_name TEXT NOT NULL
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS deaths (
                discord_name TEXT PRIMARY KEY,
                death_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (discord_name) REFERENCES minecraft_to_discord (discord_name)
            );
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS advancements (
                discord_name TEXT PRIMARY KEY,
                advancement_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (discord_name) REFERENCES minecraft_to_discord (discord_name)
            );
        ''')
        conn.commit()

def addMinecraftToDiscordToDatabase(MINECRAFT_TO_DISCORD):
    with sqlite3.connect(DATABASE_PATH) as conn:
        for minecraft_name, discord_name in MINECRAFT_TO_DISCORD.items():
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO minecraft_to_discord (discord_name, minecraft_name)
                VALUES (?, ?)
                ON CONFLICT (discord_name) DO UPDATE SET minecraft_name = excluded.minecraft_name;
            ''', (discord_name, minecraft_name))
        conn.commit()

if __name__ == "__main__":
    DATABASE_PATH = 'stats.db'
    # Minecraft to Discord username mapping
    MINECRAFT_TO_DISCORD = {
    "LuigiTime34": "luigi_is_better",
    "_gingercat_": "sblujay",
    "KerDreigerTiger": ".kaiserleopold",
    "Block_Builder": "kazzpyr",
    "AmbiguouSaurus": "bobbilby",
    "wwffd": "wizardcat1000",
    "BurgersAreYumYum": "ih8tk",
    "Dinnerbone5117": "salmon5117_73205",
    "Frogloverender": "frogloverender",
    "Sweatshirtboi16": "sweatshirtboi16",
    "MindJames": "mindjames_93738",
    "therealgoos": "therealgoos",
    "BigSharkyBRo": "car248.",
    "Brandonslay": "ctslayer.",
    "ItzT1g3r": "greattigergaming",
    "the_rock_gaming": "the_rock_gaming",
    "THERYZEN7": "asillygooberguy",
    "spleeftrappedlol": "neoptolemus_"
}

    initializeDatabase()
    addMinecraftToDiscordToDatabase(MINECRAFT_TO_DISCORD)

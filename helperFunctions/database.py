import sqlite3
import discord

from const import DATABASE_PATH, MINECRAFT_TO_DISCORD

def initializeDatabase():
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                discordUsername TEXT NOT NULL PRIMARY KEY,
                discordDisplayName TEXT NOT NULL,
                minecraftName TEXT NOT NULL,
                deathCount INTEGER NOT NULL DEFAULT 0,
                advancementCount INTEGER NOT NULL DEFAULT 0,
                joinTime INTEGER NOT NULL DEFAULT 0,
                playtimeSeconds INTEGER NOT NULL DEFAULT 0
            );
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server (
                serverIsOnline BOOLEAN NOT NULL PRIMARY KEY DEFAULT 0
            );''')

        cursor.execute('INSERT OR IGNORE INTO server (serverIsOnline) VALUES (0);')

        conn.commit()

def addMinecraftToDiscordToDatabase(MINECRAFT_TO_DISCORD, bot, DATABASE_PATH):
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()

        data = []
        for minecraft_name, discord_username in MINECRAFT_TO_DISCORD.items():
            user = discord.utils.get(bot.get_all_members(), name=discord_username)
            discord_display_name = user.display_name if user else discord_username  # Fallback to username if not found
            data.append((discord_username, discord_display_name, minecraft_name))

        cursor.executemany('''INSERT OR IGNORE INTO users (discordUsername, discordDisplayName, minecraftName) 
                              VALUES (?, ?, ?);''', data)
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

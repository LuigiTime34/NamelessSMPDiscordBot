import sqlite3
import os
from const import DATABASE_PATH, MINECRAFT_TO_DISCORD

def get_db_connection():
    """Get a connection to the database"""
    conn = sqlite3.connect(DATABASE_PATH)
    return conn

def initialize_database():
    """Create database tables if they don't exist."""
    print(f"Initializing database at {DATABASE_PATH}")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Main stats table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS player_stats (
        minecraft_username TEXT PRIMARY KEY,
        discord_username TEXT,
        deaths INTEGER DEFAULT 0,
        advancements INTEGER DEFAULT 0,
        playtime_seconds INTEGER DEFAULT 0
    )
    ''')
    
    # Tracking table for online players
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS online_players (
        minecraft_username TEXT PRIMARY KEY,
        login_time INTEGER
    )
    ''')
    
    # Initialize all players from the mapping with default values
    for mc_username, disc_username in MINECRAFT_TO_DISCORD.items():
        cursor.execute('''
        INSERT OR IGNORE INTO player_stats 
        (minecraft_username, discord_username, deaths, advancements, playtime_seconds) 
        VALUES (?, ?, 0, 0, 0)
        ''', (mc_username, disc_username))
    
    conn.commit()
    conn.close()
    print("Database initialized!")
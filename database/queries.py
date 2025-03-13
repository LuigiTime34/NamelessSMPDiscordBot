import sqlite3
import datetime
from const import DATABASE_PATH, MINECRAFT_TO_DISCORD
from database.connection import get_connection
from utils.logging import setup_logging
import logging

# Setup logger
logger = logging.getLogger('nameless_bot')

def initialize_database():
    """Create database tables if they don't exist."""
    logger.info(f"Initializing database at {DATABASE_PATH}")
    conn = get_connection()
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
    
    # Daily stats history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS stats_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        minecraft_username TEXT NOT NULL,
        date TEXT NOT NULL,
        deaths INTEGER DEFAULT 0,
        advancements INTEGER DEFAULT 0,
        playtime_seconds INTEGER DEFAULT 0,
        UNIQUE(minecraft_username, date)
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
    logger.info("Database initialized!")

def record_death(minecraft_username):
    """Increment death count for a player."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE player_stats SET deaths = deaths + 1 WHERE minecraft_username = ?", 
            (minecraft_username,)
        )
        
        # Also update today's stats directly
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
        INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
        VALUES (?, ?, 1, 0, 0)
        ON CONFLICT(minecraft_username, date) DO UPDATE SET
        deaths = deaths + 1
        ''', (minecraft_username, today))
        
        conn.commit()
        conn.close()
        logger.info(f"Recorded death for {minecraft_username}")
    except Exception as e:
        logger.error(f"Error recording death: {e}")

def record_advancement(minecraft_username):
    """Increment advancement count for a player."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE player_stats SET advancements = advancements + 1 WHERE minecraft_username = ?", 
            (minecraft_username,)
        )
        
        # Also update today's stats directly
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
        INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
        VALUES (?, ?, 0, 1, 0)
        ON CONFLICT(minecraft_username, date) DO UPDATE SET
        advancements = advancements + 1
        ''', (minecraft_username, today))
        
        conn.commit()
        conn.close()
        logger.info(f"Recorded advancement for {minecraft_username}")
    except Exception as e:
        logger.error(f"Error recording advancement: {e}")

def record_login(minecraft_username):
    """Record when a player logs in."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        current_time = int(datetime.datetime.now().timestamp())
        cursor.execute(
            "INSERT OR REPLACE INTO online_players (minecraft_username, login_time) VALUES (?, ?)",
            (minecraft_username, current_time)
        )
        conn.commit()
        conn.close()
        logger.info(f"Recorded login for {minecraft_username} at {current_time}")
    except Exception as e:
        logger.error(f"Error recording login: {e}")

def record_logout(minecraft_username):
    """Record when a player logs out and update playtime."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get login time
        cursor.execute(
            "SELECT login_time FROM online_players WHERE minecraft_username = ?",
            (minecraft_username,)
        )
        result = cursor.fetchone()
        
        if result:
            login_time = result[0]
            current_time = int(datetime.datetime.now().timestamp())
            playtime = current_time - login_time
            
            # Update total playtime
            cursor.execute(
                "UPDATE player_stats SET playtime_seconds = playtime_seconds + ? WHERE minecraft_username = ?",
                (playtime, minecraft_username)
            )
            
            # Also update today's stats
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            cursor.execute('''
            INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(minecraft_username, date) DO UPDATE SET
            playtime_seconds = playtime_seconds + ?
            ''', (minecraft_username, today, playtime, playtime))
            
            # Remove from online players
            cursor.execute(
                "DELETE FROM online_players WHERE minecraft_username = ?",
                (minecraft_username,)
            )
            
            conn.commit()
            logger.info(f"Recorded logout for {minecraft_username}, added {playtime} seconds")
        else:
            logger.error(f"No login record found for {minecraft_username}")
        
        conn.close()
        return playtime if result else 0
    except Exception as e:
        logger.error(f"Error recording logout: {e}")
        return 0

def get_player_stats(minecraft_username=None, discord_username=None):
    """Get stats for a player by minecraft or discord username."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        if minecraft_username:
            cursor.execute(
                "SELECT * FROM player_stats WHERE minecraft_username = ?",
                (minecraft_username,)
            )
        elif discord_username:
            cursor.execute(
                "SELECT * FROM player_stats WHERE discord_username = ?",
                (discord_username,)
            )
        else:
            return None
        
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting player stats: {e}")
        return None

def get_all_players():
    """Get stats for all players."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM player_stats")
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting all players: {e}")
        return []

def get_all_deaths():
    """Get all player death counts sorted from lowest to highest."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT minecraft_username, discord_username, deaths FROM player_stats ORDER BY deaths ASC"
        )
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting death counts: {e}")
        return []

def get_all_advancements():
    """Get all player advancement counts sorted from highest to lowest."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT minecraft_username, discord_username, advancements FROM player_stats ORDER BY advancements DESC"
        )
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting advancement counts: {e}")
        return []

def get_all_playtimes():
    """Get all player playtimes sorted from highest to lowest."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT minecraft_username, discord_username, playtime_seconds FROM player_stats ORDER BY playtime_seconds DESC"
        )
        result = cursor.fetchall()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting playtimes: {e}")
        return []

def get_online_players_db():
    """Get list of currently online players from the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT minecraft_username FROM online_players")
        result = cursor.fetchall()
        conn.close()
        return [player[0] for player in result]
    except Exception as e:
        logger.error(f"Error getting online players: {e}")
        return []

def clear_online_players():
    """Clear all online players and update playtimes."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get all online players
        cursor.execute("SELECT minecraft_username, login_time FROM online_players")
        players = cursor.fetchall()
        
        current_time = int(datetime.datetime.now().timestamp())
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Update playtime for each player
        for player in players:
            minecraft_username, login_time = player
            playtime = current_time - login_time
            
            cursor.execute(
                "UPDATE player_stats SET playtime_seconds = playtime_seconds + ? WHERE minecraft_username = ?",
                (playtime, minecraft_username)
            )
            
            # Also update today's stats
            cursor.execute('''
            INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(minecraft_username, date) DO UPDATE SET
            playtime_seconds = playtime_seconds + ?
            ''', (minecraft_username, today, playtime, playtime))
            
            logger.info(f"Added {playtime} seconds to {minecraft_username}")
        
        # Clear the online players table
        cursor.execute("DELETE FROM online_players")
        
        conn.commit()
        conn.close()
        logger.info(f"Cleared {len(players)} online players")
    except Exception as e:
        logger.error(f"Error clearing online players: {e}")

def bulk_update_history(updates):
    """Update player stats in bulk from provided dictionary."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        for minecraft_username, stats in updates.items():
            if 'deaths' in stats:
                cursor.execute(
                    "UPDATE player_stats SET deaths = ? WHERE minecraft_username = ?",
                    (stats['deaths'], minecraft_username)
                )
            
            if 'advancements' in stats:
                cursor.execute(
                    "UPDATE player_stats SET advancements = ? WHERE minecraft_username = ?",
                    (stats['advancements'], minecraft_username)
                )
            
            if 'playtime' in stats:
                cursor.execute(
                    "UPDATE player_stats SET playtime_seconds = ? WHERE minecraft_username = ?",
                    (stats['playtime'], minecraft_username)
                )
        
        conn.commit()
        conn.close()
        logger.info(f"Bulk updated history for {len(updates)} players")
        return True
    except Exception as e:
        logger.error(f"Error updating history: {e}")
        return False

def delete_player(minecraft_username):
    """Delete a player from the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Delete from player_stats
        cursor.execute(
            "DELETE FROM player_stats WHERE minecraft_username = ?",
            (minecraft_username,)
        )
        
        # Also delete from online_players if they're there
        cursor.execute(
            "DELETE FROM online_players WHERE minecraft_username = ?",
            (minecraft_username,)
        )
        
        # Also delete from stats_history
        cursor.execute(
            "DELETE FROM stats_history WHERE minecraft_username = ?",
            (minecraft_username,)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"Deleted player {minecraft_username} from database")
        return True
    except Exception as e:
        logger.error(f"Error deleting player: {e}")
        return False

def add_player(minecraft_username, discord_username):
    """Add a new player to the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Insert player into database
        cursor.execute(
            "INSERT OR IGNORE INTO player_stats (minecraft_username, discord_username, deaths, advancements, playtime_seconds) VALUES (?, ?, 0, 0, 0)",
            (minecraft_username, discord_username)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"Added player {minecraft_username} ({discord_username}) to database")
        return True
    except Exception as e:
        logger.error(f"Error adding player: {e}")
        return False

def save_daily_stats():
    """Save current stats as a daily snapshot."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get current date in YYYY-MM-DD format
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        
        # Get yesterday's stats for comparison
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Get all player current stats
        players = get_all_players()
        
        # For each player, calculate daily differences and save
        for mc_username, disc_username, deaths, advancements, playtime in players:
            # Get yesterday's stats if they exist
            cursor.execute(
                "SELECT deaths, advancements, playtime_seconds FROM stats_history WHERE minecraft_username = ? AND date = ?", 
                (mc_username, yesterday)
            )
            yesterday_stats = cursor.fetchone()
            
            if yesterday_stats:
                # Calculate differences
                deaths_today = max(0, deaths - yesterday_stats[0])
                advancements_today = max(0, advancements - yesterday_stats[1])
                playtime_today = max(0, playtime - yesterday_stats[2])
            else:
                # If no yesterday stats, we can't calculate accurately, just use zeros
                deaths_today = 0
                advancements_today = 0
                playtime_today = 0
                
                # For players who were online today, use their current session
                cursor.execute(
                    "SELECT login_time FROM online_players WHERE minecraft_username = ?",
                    (mc_username,)
                )
                online = cursor.fetchone()
                if online:
                    login_time = online[0]
                    current_time = int(datetime.datetime.now().timestamp())
                    playtime_today = current_time - login_time
            
            # Insert or update today's record
            cursor.execute('''
            INSERT OR REPLACE INTO stats_history 
            (minecraft_username, date, deaths, advancements, playtime_seconds)
            VALUES (?, ?, ?, ?, ?)
            ''', (mc_username, today, deaths_today, advancements_today, playtime_today))
        
        conn.commit()
        conn.close()
        logger.info(f"Saved daily stats for {len(players)} players")
        return True
    except Exception as e:
        logger.error(f"Error saving daily stats: {e}")
        return False

def get_stats_for_period(period_days):
    """Get stats for the specified period (days)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Calculate date range
        end_date = datetime.datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.datetime.now() - datetime.timedelta(days=period_days)).strftime("%Y-%m-%d")
        
        # Get stats for period
        cursor.execute('''
        SELECT minecraft_username, 
               SUM(deaths) as total_deaths, 
               SUM(advancements) as total_advancements,
               SUM(playtime_seconds) as total_playtime
        FROM stats_history
        WHERE date BETWEEN ? AND ?
        GROUP BY minecraft_username
        ''', (start_date, end_date))
        
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Error getting stats for period: {e}")
        return []
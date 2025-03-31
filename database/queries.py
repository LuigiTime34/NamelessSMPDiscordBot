import sqlite3
import datetime
from const import DATABASE_PATH, MINECRAFT_TO_DISCORD
from database.connection import get_connection # Ensure this import is present
from utils.logging import setup_logging
import logging
import pytz # Import pytz for timezone handling

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
        date TEXT NOT NULL, -- Store date as YYYY-MM-DD (est)
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

        # Also update today's stats directly (use est date)
        today_est = datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d")
        cursor.execute('''
        INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
        VALUES (?, ?, 1, 0, 0)
        ON CONFLICT(minecraft_username, date) DO UPDATE SET
        deaths = deaths + 1
        ''', (minecraft_username, today_est))

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

        # Also update today's stats directly (use est date)
        today_est = datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d")
        cursor.execute('''
        INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
        VALUES (?, ?, 0, 1, 0)
        ON CONFLICT(minecraft_username, date) DO UPDATE SET
        advancements = advancements + 1
        ''', (minecraft_username, today_est))

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
        current_time = int(datetime.datetime.now(pytz.utc).timestamp()) # Use est timestamp
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
    """Record when a player logs out and update playtime. Returns playtime added."""
    playtime = 0 # Default return value
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
            current_time = int(datetime.datetime.now(pytz.utc).timestamp()) # Use est timestamp
            # Ensure playtime is not negative if clock adjustments happened
            playtime = max(0, current_time - login_time)

            # Update total playtime
            cursor.execute(
                "UPDATE player_stats SET playtime_seconds = playtime_seconds + ? WHERE minecraft_username = ?",
                (playtime, minecraft_username)
            )

            # Also update today's stats (use est date)
            today_est = datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d")
            cursor.execute('''
            INSERT INTO stats_history (minecraft_username, date, deaths, advancements, playtime_seconds)
            VALUES (?, ?, 0, 0, ?)
            ON CONFLICT(minecraft_username, date) DO UPDATE SET
            playtime_seconds = playtime_seconds + ?
            ''', (minecraft_username, today_est, playtime, playtime))

            # Remove from online players
            cursor.execute(
                "DELETE FROM online_players WHERE minecraft_username = ?",
                (minecraft_username,)
            )

            conn.commit()
            logger.info(f"Recorded logout for {minecraft_username}, added {playtime} seconds")
        else:
            # Log this case - might happen on bot restart if player was online
            logger.warning(f"No login record found for {minecraft_username} upon logout.")

        conn.close()
        return playtime # Return the calculated playtime
    except Exception as e:
        logger.error(f"Error recording logout for {minecraft_username}: {e}")
        return 0 # Return 0 on error

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
            conn.close() # Close connection before returning
            return None

        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting player stats for {minecraft_username or discord_username}: {e}")
        # Ensure connection is closed in case of error during fetch/execute
        try: conn.close()
        except: pass
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
        try: conn.close()
        except: pass
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
        try: conn.close()
        except: pass
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
        try: conn.close()
        except: pass
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
        try: conn.close()
        except: pass
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
        try: conn.close()
        except: pass
        return []

def clear_online_players():
    """Clear all online players and update playtimes (e.g., on server stop/bot shutdown)."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get all online players
        cursor.execute("SELECT minecraft_username, login_time FROM online_players")
        players = cursor.fetchall()

        if not players:
            conn.close()
            logger.info("No online players to clear.")
            return # Nothing to do

        current_time = int(datetime.datetime.now(pytz.utc).timestamp()) # Use est timestamp
        today_est = datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d") # Use est date

        # Update playtime for each player
        for player in players:
            minecraft_username, login_time = player
            playtime = max(0, current_time - login_time)

            if playtime > 0: # Only update if there's playtime to add
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
                ''', (minecraft_username, today_est, playtime, playtime))

                logger.info(f"Added {playtime} seconds to {minecraft_username} during clear")

        # Clear the online players table
        cursor.execute("DELETE FROM online_players")

        conn.commit()
        conn.close()
        logger.info(f"Cleared {len(players)} online players and updated their playtime.")
    except Exception as e:
        logger.error(f"Error clearing online players: {e}")
        try: conn.close()
        except: pass


def bulk_update_history(updates):
    """Update player stats in bulk from provided dictionary."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        for minecraft_username, stats in updates.items():
            # Validate keys to prevent injection or errors
            valid_keys = {'deaths', 'advancements', 'playtime'}
            update_clauses = []
            update_values = []

            if 'deaths' in stats and isinstance(stats['deaths'], int):
                update_clauses.append("deaths = ?")
                update_values.append(stats['deaths'])
            if 'advancements' in stats and isinstance(stats['advancements'], int):
                 update_clauses.append("advancements = ?")
                 update_values.append(stats['advancements'])
            # Map 'playtime' key from input to 'playtime_seconds' column
            if 'playtime' in stats and isinstance(stats['playtime'], int):
                 update_clauses.append("playtime_seconds = ?")
                 update_values.append(stats['playtime'])

            if update_clauses:
                 sql = f"UPDATE player_stats SET {', '.join(update_clauses)} WHERE minecraft_username = ?"
                 update_values.append(minecraft_username)
                 cursor.execute(sql, tuple(update_values))
                 logger.debug(f"Bulk updated {minecraft_username} with {stats}")
            else:
                 logger.warning(f"No valid updates provided for {minecraft_username} in bulk update: {stats}")


        conn.commit()
        conn.close()
        logger.info(f"Bulk updated history for {len(updates)} players")
        return True
    except Exception as e:
        logger.error(f"Error updating history: {e}")
        try: conn.close()
        except: pass
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
        logger.error(f"Error deleting player {minecraft_username}: {e}")
        try: conn.close()
        except: pass
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
        logger.error(f"Error adding player {minecraft_username}: {e}")
        try: conn.close()
        except: pass
        return False

def save_daily_stats():
    """Ensure an entry exists for today in stats_history for all known players.
       Called by the daily summary task before processing yesterday.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Get current date in YYYY-MM-DD format (est)
        today_est = datetime.datetime.now(pytz.utc).strftime("%Y-%m-%d")

        # Get all known players from the main stats table
        cursor.execute("SELECT minecraft_username FROM player_stats")
        all_mc_users = [row[0] for row in cursor.fetchall()]

        # For each player, ensure they have an entry for today (don't overwrite incremental values)
        inserted_count = 0
        for mc_username in all_mc_users:
            # Use INSERT OR IGNORE to safely create the row if it doesn't exist
            # Initialize with 0s; actual increments happen in record_death/advancement/logout
            cursor.execute('''
            INSERT OR IGNORE INTO stats_history
            (minecraft_username, date, deaths, advancements, playtime_seconds)
            VALUES (?, ?, 0, 0, 0)
            ''', (mc_username, today_est))
            if cursor.rowcount > 0:
                inserted_count += 1

        conn.commit()
        conn.close()
        if inserted_count > 0:
            logger.info(f"Ensured/Created daily stats entries for {inserted_count} players for date {today_est}")
        # else: # Optional: reduce log spam
        #     logger.debug(f"All players already had stats entries for {today_est}")
        return True
    except Exception as e:
        logger.error(f"Error saving/ensuring daily stats entries: {e}")
        try: conn.close()
        except: pass
        return False

def get_stats_for_period(period_days):
    """Get aggregated stats for the specified period ending today (est).
       period_days=1 means today only.
       period_days=7 means today + previous 6 days.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Calculate date range using est dates
        end_date_dt = datetime.datetime.now(pytz.utc)
        # For a 1-day period, start_date is also today
        # For a 7-day period, start_date is 6 days ago (today inclusive)
        start_date_dt = end_date_dt - datetime.timedelta(days=max(0, period_days - 1))

        end_date = end_date_dt.strftime("%Y-%m-%d")
        start_date = start_date_dt.strftime("%Y-%m-%d")

        logger.debug(f"Getting stats for period: {start_date} to {end_date}")

        # Get aggregated stats for period
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
        logger.error(f"Error getting stats for period {period_days} days ({start_date} to {end_date}): {e}")
        try: conn.close()
        except: pass
        return []
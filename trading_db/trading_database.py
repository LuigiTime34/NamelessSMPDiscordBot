# database.py
import sqlite3
import datetime
import json

class Database:
    def __init__(self, db_file="trading_db/trading_bot.db"):
        self.db_file = db_file
        self.conn = None
        self.setup_database()
    
    def setup_database(self):
        """Create the database and tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_file)
        cursor = self.conn.cursor()
        
        # Create active trades table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_trades (
            trade_id TEXT PRIMARY KEY,
            user_id INTEGER,
            message_id INTEGER,
            thread_id INTEGER,
            channel_id INTEGER,
            end_time TEXT,
            offering TEXT,
            looking_for TEXT,
            additional_details TEXT
        )
        ''')
        
        # Create welcome message table to track if welcome message was sent
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS welcome_message (
            channel_id INTEGER PRIMARY KEY,
            message_id INTEGER
        )
        ''')
        
        self.conn.commit()
    
    def add_trade(self, trade_id, user_id, message_id, thread_id, channel_id, end_time, offering, looking_for, additional_details):
        """Add a new trade to the database."""
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO active_trades (trade_id, user_id, message_id, thread_id, channel_id, end_time, offering, looking_for, additional_details)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade_id, user_id, message_id, thread_id, channel_id, end_time.isoformat(), offering, looking_for, additional_details))
        self.conn.commit()
    
    def get_all_active_trades(self):
        """Get all active trades from the database."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM active_trades')
        trades = cursor.fetchall()
        
        result = {}
        for trade in trades:
            trade_id, user_id, message_id, thread_id, channel_id, end_time_str, offering, looking_for, additional_details = trade
            end_time = datetime.datetime.fromisoformat(end_time_str)
            
            result[trade_id] = {
                "user_id": user_id,
                "message_id": message_id,
                "thread_id": thread_id,
                "channel_id": channel_id,
                "end_time": end_time,
                "offering": offering,
                "looking_for": looking_for,
                "additional_details": additional_details
            }
        
        return result
    
    def remove_trade(self, trade_id):
        """Remove a trade from the database."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM active_trades WHERE trade_id = ?', (trade_id,))
        self.conn.commit()
    
    def save_welcome_message(self, channel_id, message_id):
        """Save the welcome message ID for a channel."""
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE INTO welcome_message (channel_id, message_id)
        VALUES (?, ?)
        ''', (channel_id, message_id))
        self.conn.commit()
    
    def get_welcome_message(self, channel_id):
        """Get the welcome message ID for a channel."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT message_id FROM welcome_message WHERE channel_id = ?', (channel_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    
    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()
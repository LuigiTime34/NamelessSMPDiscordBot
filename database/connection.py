import sqlite3
import os
from const import DATABASE_PATH

def get_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    return conn
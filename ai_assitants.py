import discord
from discord.ext import commands, tasks # tasks might not be used here but keep import for now
import sqlite3
import os
import asyncio
import logging
import datetime
import time
import aiohttp
import const # Your const.py file
import json # For logging complex objects
import re # Keep for potential future use? Remove if not used.
# import openai
import io
import time
question_helper_cooldowns = {}
from dotenv import load_dotenv

load_dotenv()

# --- Gemini LLM Setup ---
try:
    import google.generativeai as genai
    from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig # Added GenerationConfig
    from google.api_core import exceptions as google_exceptions # Specific Google exceptions
    logger = logging.getLogger('nameless_bot') # Initialize logger early
    logger.info("Successfully imported google.generativeai")
except ImportError:
    print("ERROR: google-generativeai library not found.")
    print("Please install it: pip install -U google-generativeai")
    exit(1)

# --- Dynamic Import for Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('nameless_bot')
discord_log_handler = None; setup_logging = None
try:
    import importlib
    logging_module = importlib.import_module(const.LOGGING_MODULE_PATH)
    if hasattr(logging_module, 'setup_logging') and hasattr(logging_module, 'DiscordHandler'):
        setup_logging = logging_module.setup_logging; DiscordHandler = logging_module.DiscordHandler
        logger.info("Custom logging module loaded.")
    else: logger.error("Custom logging module missing functions.")
except Exception as e: logger.exception(f"Error loading logging module: {e}.")

# --- Read Secrets ---
TOKEN = os.getenv("DISCORD_TOKEN_AI")
if not TOKEN:
    print("Error: DISCORD_TOKEN_AI not found in .env file!")
    exit(1)
    
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not found in .env file!")
    exit(1)

# --- Configure LLM (OpenRouter Client) ---
# Configure the openai client to point to OpenRouter
# try:
#     openai_client = openai.AsyncOpenAI(
#         base_url=const.OPENROUTER_API_BASE,
#         api_key=OPENROUTER_API_KEY,
#     )
#     OPENROUTER_MODEL_ID = const.GEMINI_MODEL_NAME # Use the const value
#     logger.info(f"OpenRouter client configured for model: {OPENROUTER_MODEL_ID}")
# except Exception as e:
#     logger.critical(f"Failed to configure OpenAI client for OpenRouter: {e}", exc_info=True)
#     exit(1)
try:
    genai.configure(api_key=GOOGLE_API_KEY)
    GEMINI_MODEL_ID = const.GEMINI_FLASH_MODEL_NAME # Use the new const value
    logger.info(f"Google GenAI client configured for model: {GEMINI_MODEL_ID}")
    # Default safety settings (adjust as needed)
    SAFETY_SETTINGS = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }
    # Default generation config (adjust as needed)
    GENERATION_CONFIG = GenerationConfig(
        max_output_tokens=1024, # Increased slightly, adjust if needed
        temperature=0.7,
    )
except Exception as e:
    logger.critical(f"Failed to configure Google GenAI client: {e}", exc_info=True)
    exit(1)
    

# --- Bot Setup ---
intents = discord.Intents.all(); intents.message_content = True; intents.members = True; intents.guilds = True
BOT_PREFIX = getattr(const, 'BOT_PREFIX', '!')
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None, case_insensitive=True)

# --- Logging Setup (Initialize Custom Handler) ---
LOG_LEVEL = logging.DEBUG if os.getenv("BOT_DEBUG") else logging.INFO
logger.setLevel(LOG_LEVEL)
if setup_logging:
    try: logger, discord_log_handler = setup_logging(bot, const.LOGGING_CHANNEL_ID, level=LOG_LEVEL); logger.info(f"Custom logging configured.")
    except Exception as e: logger.exception("Failed to initialize custom logging handler."); discord_log_handler = None
else: logger.warning("Using basic fallback logging.")

# --- Database Setup & Helpers ---
db_conn = None; db_cursor = None
DB_SETUP_LOCK = asyncio.Lock()

async def init_db():
    """Initializes DB connection and tables."""
    global db_conn, db_cursor
    async with DB_SETUP_LOCK:
        if db_conn: return
        try:
            logger.info(f"Connecting to DB: {const.DATABASE_FILE}")
            # --- MODIFIED: Added detect_types ---
            db_conn = await bot.loop.run_in_executor(None, lambda: sqlite3.connect(const.DATABASE_FILE, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES))
            db_conn.row_factory = sqlite3.Row
            db_cursor = db_conn.cursor()
            await bot.loop.run_in_executor(None, db_cursor.execute, 'PRAGMA foreign_keys = ON')
            logger.info("DB connected. Ensuring tables exist...")
            # Assistants Table (Unchanged definition)
            await bot.loop.run_in_executor(None, db_cursor.execute, '''
                CREATE TABLE IF NOT EXISTS assistants (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL COLLATE NOCASE,
                    description TEXT, system_prompt TEXT NOT NULL, avatar_url TEXT )
            ''')
            await bot.loop.run_in_executor(None, db_cursor.execute, "CREATE UNIQUE INDEX IF NOT EXISTS idx_assistant_user_name ON assistants (user_id, name)")

            # --- MODIFIED: Added warning_sent_at column ---
            await bot.loop.run_in_executor(None, db_cursor.execute, '''
                 CREATE TABLE IF NOT EXISTS active_threads (
                    thread_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    assistant_id INTEGER NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    warning_sent_at TIMESTAMP DEFAULT NULL, -- Timestamp when inactivity warning was sent
                    FOREIGN KEY (assistant_id) REFERENCES assistants (id) ON DELETE CASCADE )
            ''')
            # --- END MODIFICATION ---

            await bot.loop.run_in_executor(None, db_conn.commit)
            logger.info(f"Database '{const.DATABASE_FILE}' initialized/verified.")
        except sqlite3.Error as e: logger.exception(f"CRITICAL: DB Init Error: {e}"); db_conn = None

async def close_db():
    """Closes the database connection."""
    global db_conn
    if db_conn:
        try: await bot.loop.run_in_executor(None, db_conn.close); logger.info("DB closed.")
        except Exception as e: logger.exception(f"Error closing DB: {e}")
        finally: db_conn = None

# --- Async Database Helpers ---
# Using simplified structure for readability
async def run_db_query_async(query: str, params: tuple = (), fetch_one=False, fetch_all=False, commit=False):
    if not db_conn: logger.error("DB Query attempted while DB not connected."); return False, "DB unavailable."
    try:
        loop = asyncio.get_running_loop()
        # Define sync function to run in executor
        def _sync_operation():
            # Create cursor inside sync function if modifying data or need isolation
            cursor = db_conn.cursor()
            cursor.execute(query, params)
            result = None
            rowcount = cursor.rowcount # Get rowcount for potential use
            if fetch_one: result = cursor.fetchone()
            elif fetch_all: result = cursor.fetchall()
            if commit: db_conn.commit()
            cursor.close()
            return result, rowcount # Return both result and rowcount if needed

        result, rowcount = await loop.run_in_executor(None, _sync_operation)
        # Return success, result, and rowcount (caller can decide which to use)
        return True, result, rowcount
    except sqlite3.Error as e:
        logger.exception(f"Async DB Error query '{query[:50]}' params {params}: {e}")
        return False, str(e), 0 # Return error string and 0 rowcount

async def add_assistant(user_id: int, name: str, desc: str, prompt: str, avatar: str):
    query = "INSERT INTO assistants (user_id, name, description, system_prompt, avatar_url) VALUES (?, ?, ?, ?, ?)"
    params = (user_id, name, desc, prompt, avatar)
    success, err_or_result, _ = await run_db_query_async(query, params, commit=True)
    if success: logger.info(f"Assistant '{name}' added user {user_id}."); return True, "Assistant created."
    if isinstance(err_or_result, str) and "UNIQUE constraint failed" in err_or_result: return False, "Name already used by you."
    return False, f"DB error: {err_or_result}"

async def update_assistant(assistant_id: int, user_id: int, name: str, desc: str, prompt: str) -> tuple[bool, str]:
    """Updates an existing assistant's text fields."""
    # First, check for name conflicts excluding the current assistant
    success, existing, _ = await run_db_query_async(
        "SELECT id FROM assistants WHERE user_id = ? AND name = ? AND id != ?",
        (user_id, name, assistant_id),
        fetch_one=True
    )
    if not success:
        return False, f"DB error checking name conflict: {existing}"
    if existing:
        return False, f"You already have another assistant named '{name}'."

    # Proceed with update if name is unique
    query = """
        UPDATE assistants
        SET name = ?, description = ?, system_prompt = ?
        WHERE id = ? AND user_id = ?
    """
    params = (name, desc, prompt, assistant_id, user_id)
    success, error_msg, rowcount = await run_db_query_async(query, params, commit=True)

    if success and rowcount > 0:
        logger.info(f"Assistant {assistant_id} updated by user {user_id}. Name: '{name}'")
        return True, "Assistant updated successfully."
    elif success: # rowcount was 0
        logger.warning(f"Update failed for assistant {assistant_id} by user {user_id} (not found or not owned).")
        return False, "Assistant not found or you don't own it."
    else: # DB error
        logger.error(f"DB error updating assistant {assistant_id}: {error_msg}")
        return False, f"Database error during update: {error_msg}"

async def update_assistant_avatar(assistant_id: int, user_id: int, avatar_url: str) -> tuple[bool, str]:
    """Updates only the avatar URL of an assistant."""
    query = "UPDATE assistants SET avatar_url = ? WHERE id = ? AND user_id = ?"
    params = (avatar_url, assistant_id, user_id)
    success, error_msg, rowcount = await run_db_query_async(query, params, commit=True)

    if success and rowcount > 0:
        logger.info(f"Avatar updated for assistant {assistant_id} by user {user_id}.")
        return True, "Avatar updated successfully."
    elif success:
         logger.warning(f"Avatar update failed for assistant {assistant_id} by user {user_id} (not found or not owned).")
         return False, "Assistant not found or you don't own it."
    else:
         logger.error(f"DB error updating avatar for assistant {assistant_id}: {error_msg}")
         return False, f"Database error updating avatar: {error_msg}"

async def get_user_assistant_count(user_id: int) -> int:
    success, result, _ = await run_db_query_async("SELECT COUNT(*) FROM assistants WHERE user_id = ?", (user_id,), fetch_one=True)
    return result[0] if success and result else 0

async def get_assistants(user_id: int = None):
    query = "SELECT * FROM assistants ORDER BY name COLLATE NOCASE"; params = ()
    if user_id: query = "SELECT * FROM assistants WHERE user_id = ? ORDER BY name COLLATE NOCASE"; params = (user_id,)
    success, result, _ = await run_db_query_async(query, params, fetch_all=True); return result if success else []

async def get_assistant_by_id(assistant_id: int):
    success, result, _ = await run_db_query_async("SELECT * FROM assistants WHERE id = ?", (assistant_id,), fetch_one=True); return result if success else None

async def delete_assistant_by_id(assistant_id: int, user_id: int) -> bool:
    success, _, rowcount = await run_db_query_async("DELETE FROM assistants WHERE id = ? AND user_id = ?", (assistant_id, user_id), commit=True)
    if success and rowcount > 0: logger.info(f"Assistant {assistant_id} deleted by {user_id}."); return True
    elif success: logger.warning(f"User {user_id} failed delete assist {assistant_id}."); return False
    else: return False # Error occurred

async def add_active_thread(thread_id: int, user_id: int, assistant_id: int):
    # No warning column
    query = "INSERT INTO active_threads (thread_id, user_id, assistant_id, message_count, last_activity) VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)"
    params = (thread_id, user_id, assistant_id)
    success, _, _ = await run_db_query_async(query, params, commit=True)
    if success: logger.info(f"Thread {thread_id} added active.")
    return success

async def get_active_thread(thread_id: int):
    # --- MODIFIED: Select warning_sent_at ---
    query = "SELECT thread_id, user_id, assistant_id, message_count, last_activity, warning_sent_at FROM active_threads WHERE thread_id = ?"
    params = (thread_id,)
    success, result, _ = await run_db_query_async(query, params, fetch_one=True); return result if success else None

async def remove_active_thread(thread_id: int):
    success, _, rowcount = await run_db_query_async("DELETE FROM active_threads WHERE thread_id = ?", (thread_id,), commit=True)
    if success and rowcount > 0: logger.info(f"Thread {thread_id} removed active."); return True
    return False # Not found or error

# --- MODIFIED: Resets warning timestamp on activity ---
async def increment_message_count(thread_id: int):
    """Increments message count and resets warning timestamp."""
    query = "UPDATE active_threads SET message_count = message_count + 1, last_activity = CURRENT_TIMESTAMP, warning_sent_at = NULL WHERE thread_id = ?"
    params = (thread_id,)
    success, _, rowcount = await run_db_query_async(query, params, commit=True)
    return success and rowcount > 0

async def set_thread_warning_timestamp(thread_id: int):
    """Sets the warning timestamp for a thread."""
    query = "UPDATE active_threads SET warning_sent_at = CURRENT_TIMESTAMP WHERE thread_id = ?"
    params = (thread_id,)
    success, _, rowcount = await run_db_query_async(query, params, commit=True)
    if success and rowcount > 0: logger.info(f"Set warning timestamp for thread {thread_id}.")
    elif success: logger.warning(f"Tried to set warning timestamp for non-existent thread {thread_id}.")
    else: logger.error(f"DB error setting warning timestamp for thread {thread_id}.")
    return success and rowcount > 0

# --- LLM Interaction (Using OpenRouter / OpenAI Library) ---
DEBUG_LLM_CALLS = True
REACTION_PATTERN = re.compile(r"\[react:\s*(\S+)\s*\]\s*$")
DELETE_KEYWORD = "delete"


@tasks.loop(minutes=1) # Check every minute
async def check_thread_timeouts():
    logger.debug("Running check_thread_timeouts task...")
    # Fetch all active threads with necessary columns
    success, rows, _ = await run_db_query_async(
        "SELECT thread_id, user_id, assistant_id, last_activity, warning_sent_at FROM active_threads",
        fetch_all=True
    )
    if not success or not rows:
        if not success: logger.error("Failed to fetch active threads for timeout check.")
        else: logger.debug("No active threads found for timeout check.")
        return

    now_aware = datetime.datetime.now(datetime.timezone.utc)
    # Ensure constants are defined in const.py
    try:
        warning_delta = datetime.timedelta(minutes=const.THREAD_INACTIVITY_WARNING_MINUTES)
        close_delta = datetime.timedelta(minutes=const.THREAD_INACTIVITY_CLOSE_MINUTES)
        if close_delta <= warning_delta:
             logger.error("THREAD_INACTIVITY_CLOSE_MINUTES must be greater than THREAD_INACTIVITY_WARNING_MINUTES in const.py!")
             return # Avoid invalid logic
    except AttributeError:
        logger.error("Missing THREAD_INACTIVITY constants in const.py! Timeout task cannot run.")
        return

    threads_to_remove = [] # Keep track of threads to remove after iteration

    for row in rows:
        thread_id = row['thread_id']
        last_activity_str = row['last_activity']
        warning_sent_at_str = row['warning_sent_at']

        try:
            # SQLite returns strings for TIMESTAMP unless detect_types is used correctly
            # Let's parse manually just in case detect_types isn't working perfectly
            if isinstance(last_activity_str, str):
                 last_activity_dt = datetime.datetime.strptime(last_activity_str, '%Y-%m-%d %H:%M:%S')
            elif isinstance(last_activity_str, datetime.datetime): # If detect_types worked
                 last_activity_dt = last_activity_str
            else:
                 logger.error(f"Unexpected type for last_activity T:{thread_id}: {type(last_activity_str)}")
                 continue # Skip this thread if type is wrong

            # Ensure timezone aware comparison
            last_activity_aware = last_activity_dt.replace(tzinfo=datetime.timezone.utc) if last_activity_dt.tzinfo is None else last_activity_dt

            time_delta = now_aware - last_activity_aware
            logger.debug(f"Checking thread {thread_id}: Inactive for {time_delta}")

            thread = bot.get_channel(thread_id)
            if not thread or not isinstance(thread, discord.Thread) or thread.archived: # Also check if already archived
                logger.warning(f"Thread {thread_id} not found, not a Thread, or already archived. Scheduling for removal from DB.")
                threads_to_remove.append(thread_id)
                continue

            # Check for closure first
            if time_delta > close_delta:
                logger.info(f"Thread {thread_id} inactive for longer than {close_delta}. Closing.")
                close_time_fmt = discord.utils.format_dt(last_activity_aware, style='R') # Show when last activity was
                try:
                    await thread.send(f"🗑️ This chat thread has been inactive since {close_time_fmt} and is being automatically closed and archived.")
                    await asyncio.sleep(1)
                    await thread.edit(locked=True, archived=True, reason=f"Automatic closure due to inactivity ({time_delta}).")
                    logger.info(f"Successfully closed and archived thread {thread_id}.")
                    threads_to_remove.append(thread_id)
                except discord.Forbidden: logger.error(f"Failed to close thread {thread_id} (Forbidden)."); threads_to_remove.append(thread_id) # Remove anyway
                except discord.HTTPException as e: logger.error(f"Failed to close thread {thread_id} (HTTP {e.status}). Removing.", exc_info=True); threads_to_remove.append(thread_id)
                except Exception as e: logger.exception(f"Unexpected error closing thread {thread_id}. Removing."); threads_to_remove.append(thread_id)
                continue # Go to next thread

            # Check for warning (only if not closed and warning not already sent)
            # warning_sent_at_str will be None if warning_sent_at is NULL in DB
            elif time_delta > warning_delta and warning_sent_at_str is None:
                 logger.info(f"Thread {thread_id} inactive for longer than {warning_delta}. Sending warning.")
                 warning_time_fmt = discord.utils.format_dt(last_activity_aware, style='R')
                 close_timestamp_fmt = discord.utils.format_dt(last_activity_aware + close_delta, style='F')
                 try:
                     await thread.send(f"⚠️ This chat thread has been inactive since {warning_time_fmt}. It will be automatically closed and archived around {close_timestamp_fmt} if there is no further activity.")
                     await set_thread_warning_timestamp(thread_id) # Update DB *after* sending
                 except discord.Forbidden: logger.error(f"Failed send warning T:{thread_id} (Forbidden).")
                 except discord.HTTPException as e: logger.error(f"Failed send warning T:{thread_id} (HTTP {e.status}).", exc_info=True)
                 except Exception as e: logger.exception(f"Unexpected error sending warning T:{thread_id}.")

        except ValueError as e: # Catch specific parsing errors
            logger.error(f"Failed to parse timestamp for thread {thread_id}: last_activity='{last_activity_str}'. Error: {e}")
        except Exception as e:
             logger.exception(f"Unexpected error processing thread {thread_id} in timeout task.")

    # Remove threads that were closed or couldn't be found
    if threads_to_remove:
         logger.info(f"Removing {len(threads_to_remove)} inactive/invalid threads from DB: {threads_to_remove}")
         # Use DELETE FROM ... WHERE thread_id IN (...) for efficiency
         placeholders = ','.join('?' for _ in threads_to_remove)
         query = f"DELETE FROM active_threads WHERE thread_id IN ({placeholders})"
         await run_db_query_async(query, tuple(threads_to_remove), commit=True)


@check_thread_timeouts.before_loop
async def before_check_thread_timeouts():
    await bot.wait_until_ready()
    logger.info("Thread timeout checking task is ready.")

async def call_gemini_llm(system_prompt: str, history: list[dict], is_assistant_call: bool = True):
    """
    Calls the Google Gemini API using the google-generativeai library.
    Optionally appends global guidelines to the system prompt.
    Can work with empty history if system_prompt is provided (e.g., for title generation).
    History should be list of {'role': 'user'/'model', 'parts': ['message']}
    Returns (response_text, suggested_action)
    """
    # Determine the full system prompt based on context
    full_system_prompt = system_prompt # Start with the base prompt passed in
    if is_assistant_call: # Append global guidelines ONLY for assistant chat calls
        try:
            # Format the guidelines from const.py
            global_guidelines = const.ASSISTANT_GLOBAL_GUIDELINES.format(
                max_chars=const.DISCORD_MAX_MESSAGE_CHARS
            )
            # Ensure there's a separator if the original prompt exists
            full_system_prompt = f"{system_prompt}\n{global_guidelines}" if system_prompt else global_guidelines
        except AttributeError:
             logger.error("ASSISTANT_GLOBAL_GUIDELINES constant missing or malformed in const.py!")
             # Proceed without guidelines if constant is missing
        except Exception as e:
             logger.error(f"Error formatting ASSISTANT_GLOBAL_GUIDELINES: {e}")
             # Proceed without guidelines

    # Format message history if provided
    formatted_history = []
    last_role = None
    if history: # Only process if history is not None or empty
        for msg in history:
            role = msg.get("role")
            content_parts = msg.get("parts")
            # Ensure content exists and handle potential non-list parts gracefully
            content = content_parts[0] if content_parts and isinstance(content_parts, list) else msg.get("content", "")

            if role in ["user", "model"] and content:
                # Combine consecutive messages from the same role
                if role == last_role and formatted_history:
                    formatted_history[-1]['parts'][0] += f"\n{content}" # Append content
                    continue # Skip adding a new dict entry
                # Add new message entry
                formatted_history.append({"role": role, "parts": [content]})
                last_role = role
            else:
                 logger.warning(f"Skipping message with invalid role/content for Gemini: Role='{role}', Content='{content[:50]}...'")

    # --- MODIFIED: Ensure history is never empty for the call ---
    # If history was initially empty or became empty after processing,
    # AND we have a system prompt to work from, add a dummy starter message.
    if not formatted_history and full_system_prompt:
        logger.debug("History is empty, adding dummy starter message based on system prompt.")
        # Add a generic user message to kickstart generation based on system prompt
        formatted_history.append({'role': 'user', 'parts': ['Begin.']}) # Or "Start.", "Generate.", etc.
    elif not formatted_history and not full_system_prompt:
        # This case remains an error - nothing to generate from
        logger.error("Cannot call Gemini LLM with empty history AND no system prompt.")
        return "Error: No message history or system prompt provided.", None

    # --- Logging for Debug ---
    if DEBUG_LLM_CALLS:
        log_hist = formatted_history[-5:]
        logger.debug(f"--- Calling Google Gemini ({GEMINI_MODEL_ID}) ---")
        logger.debug(f"Assistant Call: {is_assistant_call}")
        logger.debug(f"Full System Prompt (first 100 chars): {full_system_prompt[:100] if full_system_prompt else 'None'}...")
        logger.debug(f"History (last {len(log_hist)}): {json.dumps(log_hist)}")
    # --- END Logging ---

    response_text = None
    error_message = None
    suggestion = None

    try:
        # Initialize the Generative Model
        model = genai.GenerativeModel(
            f'models/{GEMINI_MODEL_ID}',
            safety_settings=SAFETY_SETTINGS,
            generation_config=GENERATION_CONFIG,
            system_instruction=full_system_prompt # Pass the potentially combined prompt
        )

        # Generate content using the formatted history (can be empty)
        response = await model.generate_content_async(formatted_history)

        # --- Debug logging of raw response ---
        if DEBUG_LLM_CALLS:
             try:
                 logger.debug(f"--- Gemini Raw Response ---")
                 logger.debug(f"Text: {response.text[:100] if hasattr(response, 'text') else 'N/A'}...")
                 logger.debug(f"Finish Reason: {response.candidates[0].finish_reason if response.candidates else 'N/A'}")
                 logger.debug(f"Safety Ratings: {response.candidates[0].safety_ratings if response.candidates else 'N/A'}")
                 logger.debug(f"Prompt Feedback: {response.prompt_feedback if hasattr(response, 'prompt_feedback') else 'N/A'}")
             except Exception as log_e:
                  logger.error(f"Error logging Gemini raw response: {log_e}")

        # --- Parse response text and suggestions ---
        try:
            # Check for prompt/response blocking first
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                 block_reason = response.prompt_feedback.block_reason
                 logger.warning(f"Gemini blocked the prompt: {block_reason}")
                 error_message = f"AI blocked the prompt (Reason: {block_reason}). Please rephrase."
            elif response.candidates and response.candidates[0].finish_reason == 'SAFETY':
                 safety_ratings = response.candidates[0].safety_ratings
                 logger.warning(f"Gemini blocked the response due to safety settings: {safety_ratings}")
                 error_message = "AI response blocked by safety filter."
            else:
                # If not blocked, attempt to get text
                response_text = response.text # Accesses text safely, raises ValueError if blocked
                if response_text:
                    response_text = response_text.strip()
                    # Only parse suggestions if it's an assistant call
                    if is_assistant_call:
                        react_match = REACTION_PATTERN.search(response_text)
                        if response_text.lower() == DELETE_KEYWORD:
                             suggestion = "delete"; response_text = ""; logger.info("Gemini LLM suggested deletion.")
                        elif react_match:
                            suggestion = react_match.group(1); response_text = REACTION_PATTERN.sub("", response_text).strip(); logger.info(f"Gemini LLM suggested reaction: '{suggestion}'")
                    # If not an assistant call, suggestion remains None
                else:
                    # Model ran but produced no text (or only safety block)
                    finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
                    logger.warning(f"Gemini returned empty text. Finish Reason: {finish_reason}")
                    # Avoid setting generic error message if only text is empty
                    if finish_reason != 'STOP': # Only flag as error if finish reason isn't normal stop
                         error_message = f"AI returned empty content (Finish: {finish_reason})."
                    else:
                         response_text = "" # Treat normal stop with empty text as just empty string

        except ValueError: # Catches error from response.text access if blocked
            logger.warning(f"Gemini response access failed (likely blocked). Feedback: {response.prompt_feedback}, Candidates: {response.candidates}")
            error_message = "AI response blocked or unavailable."
        except IndexError: # Catches error if response.candidates is empty
            logger.warning(f"Gemini response missing candidates. Response: {response}")
            error_message = "AI response structure invalid (no candidates)."
        # --- End Parsing ---

    # --- Exception Handling for API Call ---
    except google_exceptions.ResourceExhausted as e:
        logger.error(f"Gemini rate limit exceeded: {e}")
        error_message = "AI rate limit hit. Try again later."
    except google_exceptions.PermissionDenied as e:
        logger.error(f"Gemini permission error (check API Key/Quota Project): {e}")
        error_message = "AI permission denied. Check API Key or Quota settings."
    except google_exceptions.InvalidArgument as e:
         logger.error(f"Gemini invalid argument error: {e}")
         error_message = f"AI rejected request (Invalid argument). Check logs."
    except google_exceptions.InternalServerError as e:
         logger.error(f"Gemini internal server error: {e}")
         error_message = "AI service encountered an internal error. Try again later."
    except google_exceptions.DeadlineExceeded as e:
        logger.warning(f"Gemini call timed out: {e}")
        error_message = "AI request timed out."
    except asyncio.TimeoutError: # Catch specific asyncio timeout from wait_for
        logger.warning("Gemini call timed out (asyncio).")
        error_message = "AI request timed out."
    except Exception as e: # Catch any other unexpected error
        logger.exception(f"Unexpected error during Gemini call: {e}")
        error_message = "Unexpected error calling AI."
    # --- END Exception Handling ---

    # --- Return results ---
    if error_message:
        # Return the specific error message for handling upstream
        return error_message, None
    elif response_text is not None:
        # Return the processed text (can be empty) and any suggestion
        return response_text, suggestion
    else:
        # Fallback if no text and no specific error was caught (should be rare)
        logger.warning("Gemini call finished with None text/error.")
        return "(AI error or empty response)", None


# --- Webhook Management (More Robust Logging) ---
async def get_webhook(parent_channel: discord.TextChannel) -> discord.Webhook | None:
    """Gets or creates a webhook named const.ASSISTANT_WEBHOOK_NAME in the parent channel."""
    if not isinstance(parent_channel, discord.TextChannel):
        logger.error(f"Non-TextChannel passed to get_webhook: {parent_channel}")
        return None
    bot_member = parent_channel.guild.me # Get bot member object for permission check
    if not parent_channel.permissions_for(bot_member).manage_webhooks:
         logger.error(f"Bot lacks 'Manage Webhooks' permission in channel #{parent_channel.name} ({parent_channel.id}).")
         return None # Cannot proceed without permission

    try:
        webhooks = await parent_channel.webhooks()
        for wh in webhooks:
            # Check if created by our bot and has the expected name
            if wh.name == const.ASSISTANT_WEBHOOK_NAME and wh.user == bot.user:
                logger.debug(f"Found existing webhook {wh.id} in #{parent_channel.name}")
                return wh

        # If not found, create one
        logger.info(f"Creating webhook '{const.ASSISTANT_WEBHOOK_NAME}' in #{parent_channel.name}")
        new_wh = await parent_channel.create_webhook(name=const.ASSISTANT_WEBHOOK_NAME, reason="Assistant Bot")
        return new_wh
    except discord.Forbidden: # Should be caught by permission check above, but double-check
        logger.error(f"Got Forbidden error managing webhooks in #{parent_channel.name} despite initial check.")
        return None
    except discord.HTTPException as e:
         logger.exception(f"HTTP Error get/create webhook in #{parent_channel.name}: {e.status} {e.text}")
         return None
    except Exception as e:
        logger.exception(f"Unexpected Error get/create webhook in #{parent_channel.name}: {e}")
        return None

async def send_webhook_message(thread: discord.Thread, parent_channel: discord.TextChannel, assistant: sqlite3.Row, content: str):
    """Sends message via webhook into the thread using assistant's persona."""
    webhook = await get_webhook(parent_channel) # Checks permissions internally now
    username = assistant['name'] if assistant else 'Assistant (Error)'

    # --- Fallback if webhook cannot be obtained ---
    if not webhook:
        logger.error(f"Failed get/create webhook for #{parent_channel.name}. Sending fallback message to thread {thread.id}.")
        try:
            # Send simple fallback message
            fallback_content = f"**(WH Setup Err)**\n**{username}**: {content[:1900]}"
            await thread.send(fallback_content)
        except Exception as e_fb:
            logger.error(f"Failed sending fallback message to thread {thread.id}: {e_fb}")
        return # Stop here if webhook failed

    # --- Proceed with sending if webhook obtained ---
    content = content[:2000] if content else "(Empty AI response)"
    avatar_url = assistant['avatar_url'] if assistant else None

    logger.debug(f"Attempting Send via Webhook: User='{username}', Avatar='{avatar_url}', Thread={thread.id}")
    if avatar_url and not avatar_url.startswith(('http://', 'https://')):
         logger.warning(f"Invalid avatar_url '{avatar_url}' assist {assistant['id'] if assistant else 'N/A'}. Sending without.")
         avatar_url = None

    try:
        async with aiohttp.ClientSession() as session:
            wh = discord.Webhook.from_url(webhook.url, session=session)
            await wh.send(
                content=content,
                username=username,
                avatar_url=avatar_url,
                thread=thread,
                allowed_mentions=discord.AllowedMentions.none()
            )
        logger.debug(f"Webhook message sent successfully to thread {thread.id}")
    except Exception as e: # Catch potential errors during send more broadly
        logger.exception(f"WH Send Error thr {thread.id}: {e}. URL='{avatar_url}' WH={webhook.id}")
        # --- Send different fallback message indicating SEND error ---
        try:
             fallback_content = f"**(WH Send Err)**\n**{username}**: {content[:1900]}" # Indicate send error
             await thread.send(fallback_content)
        except Exception as e_fb:
             logger.error(f"Failed sending SEND fallback message to thread {thread.id}: {e_fb}")

# --- Discord UI Components (Simplified for Text Commands) ---

# --- NEW View for Public/Private Choice ---

# --- NEW View for Public/Private Choice ---

class ThreadTypeSelectView(discord.ui.View):
    def __init__(self, user_id: int, assistant: sqlite3.Row, generated_title: str, original_interaction: discord.Interaction, timeout=120):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.assistant = assistant
        self.generated_title = generated_title
        self.original_interaction = original_interaction # Store the interaction that triggered the assistant select (might be useful)
        self.message: discord.InteractionMessage | None = None # To store the message this view is attached to

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Ensure only the original user can click
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This choice is for the user who started the chat.", ephemeral=True)
            return False
        return True

    def disable_buttons(self):
        """Disables all buttons in this view."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def _create_thread_and_start(self, interaction: discord.Interaction, channel_type: discord.ChannelType):
        """Handles thread creation, DB update, and sending the welcome embed."""
        # --- Defer the BUTTON interaction EPHEMERALLY ---
        # Acknowledge the button click quickly and hide the "Thinking..." state.
        await interaction.response.defer(ephemeral=True, thinking=True)

        target_channel = interaction.channel # The channel where the button was clicked
        if not isinstance(target_channel, discord.TextChannel):
            logger.error(f"Button clicked in non-TextChannel? {target_channel}")
            await interaction.followup.send("Cannot create threads here.", ephemeral=True)
            # Edit the button message to show error
            if self.message:
                try: await self.message.edit(content="Error: Cannot create threads in this channel.", view=None)
                except discord.HTTPException: pass
            return

        assistant_name = self.assistant['name']
        assistant_id = self.assistant['id']
        user = interaction.user

        logger.info(f"Attempting to create {channel_type.name} thread titled '{self.generated_title}' for U:{user.id} A:{assistant_id}")

        thread: discord.Thread | None = None # Initialize thread variable
        try:
            # Create the thread
            thread = await target_channel.create_thread(
                name=self.generated_title,
                type=channel_type
            )
            logger.info(f"Created {channel_type.name} thread {thread.id}")
        except discord.Forbidden:
            logger.error(f"Cannot create {channel_type.name} threads in #{target_channel.name} (Forbidden).")
            await interaction.followup.send(f"Error: I don't have permission to create {channel_type.name} threads here.", ephemeral=True)
            if self.message:
                 try: await self.message.edit(content="Thread creation failed (Permissions).", view=None)
                 except discord.HTTPException: pass
            return
        except discord.HTTPException as e:
            logger.exception(f"Failed thread create #{target_channel.name}: {e}")
            await interaction.followup.send(f"Error: Failed to create the thread ({e.status}).", ephemeral=True)
            if self.message:
                 try: await self.message.edit(content=f"Thread creation failed ({e.status}).", view=None)
                 except discord.HTTPException: pass
            return
        except Exception as e: # Catch any other potential error during creation
             logger.exception(f"Unexpected error creating thread #{target_channel.name}: {e}")
             await interaction.followup.send("An unexpected error occurred during thread creation.", ephemeral=True)
             if self.message:
                  try: await self.message.edit(content="Thread creation failed (Unexpected Error).", view=None)
                  except discord.HTTPException: pass
             return


        # Add thread to active database
        added = await add_active_thread(thread.id, user.id, assistant_id)
        if not added:
            logger.error(f"Failed to add thread {thread.id} to active_threads DB.")
            # Attempt to clean up the created thread if DB add failed
            try:
                logger.warning(f"Attempting to delete thread {thread.id} due to DB add failure.")
                await thread.delete(reason="DB add failed")
            except discord.HTTPException:
                logger.warning(f"Failed to delete thread {thread.id} after DB failure.")
            await interaction.followup.send("Error: Could not register the chat thread in the database.", ephemeral=True)
            if self.message:
                 try: await self.message.edit(content="Thread creation failed (Database Error).", view=None)
                 except discord.HTTPException: pass
            return

        # --- Send Welcome Embed ---
        try:
            welcome_embed = discord.Embed(
                title="Assistant Chat Started!",
                description=f"You are now chatting with **{discord.utils.escape_markdown(assistant_name)}**.\n\n*Conversation Limit: {const.MAX_THREAD_MESSAGES} messages.*\n*Use `{BOT_PREFIX}end` in this thread to close it.*",
                color=discord.Color.green()
            )
            # Add thumbnail if valid URL exists
            if self.assistant['avatar_url'] and self.assistant['avatar_url'].startswith(('http://', 'https://')):
                 welcome_embed.set_thumbnail(url=self.assistant['avatar_url'])
            welcome_embed.set_footer(text=f"Thread Type: {channel_type.name.replace('_', ' ').title()}")

            # Send embed to the new thread, ping the user in content for notification
            await thread.send(content=f"Hi {user.mention}!", embed=welcome_embed)
        except discord.HTTPException as e:
             logger.error(f"Failed to send welcome embed to thread {thread.id}: {e}")
             # Non-critical error, chat is still started

        # --- Confirm creation to user and EDIT THE BUTTON MESSAGE ---
        # Send ephemeral confirmation first
        await interaction.followup.send(f"✅ {channel_type.name.replace('_', ' ').title()} thread created: {thread.mention}", ephemeral=True)

        # Edit the original message that contained the buttons
        if self.message:
             try:
                 await self.message.edit(content=f"Chat started in {thread.mention}!", view=None) # Remove buttons
                 logger.debug(f"Successfully edited button message {self.message.id}")
             except discord.HTTPException as e:
                  logger.warning(f"Failed to edit original button message {self.message.id}: {e}")
        else:
             logger.warning("Could not find original button message object (self.message) to edit.")


    @discord.ui.button(label="Public Thread", style=discord.ButtonStyle.primary, custom_id="thread_type:public")
    async def public_thread(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"User {interaction.user.id} chose Public Thread for Assistant {self.assistant['id']}")
        self.disable_buttons() # Disable buttons immediately on click
        # Edit message immediately to show processing, maybe? Optional.
        # try: await interaction.response.edit_message(content="Creating public thread...", view=self)
        # except discord.HTTPException: pass # Ignore if edit fails quickly
        await self._create_thread_and_start(interaction, discord.ChannelType.public_thread)
        self.stop() # Stop the view listener

    @discord.ui.button(label="Private Thread", style=discord.ButtonStyle.secondary, custom_id="thread_type:private")
    async def private_thread(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"User {interaction.user.id} chose Private Thread for Assistant {self.assistant['id']}")
        self.disable_buttons() # Disable buttons immediately on click
        # try: await interaction.response.edit_message(content="Creating private thread...", view=self)
        # except discord.HTTPException: pass
        await self._create_thread_and_start(interaction, discord.ChannelType.private_thread)
        self.stop() # Stop the view listener

    async def on_timeout(self):
        if self.message:
            logger.debug(f"ThreadTypeSelectView timed out for user {self.user_id}")
            try:
                 self.disable_buttons()
                 # Edit the message the buttons were attached to
                 await self.message.edit(content="Thread type selection timed out.", view=self) # Keep view to show disabled buttons
            except discord.NotFound: pass # Message might have been deleted
            except discord.HTTPException as e:
                 logger.warning(f"Failed to edit button message {self.message.id} on timeout: {e}")
        self.stop()

# Select Menu for !chat Command
class AssistantSelectView(discord.ui.View):
    # --- MODIFIED: Accept assistants list in init ---
    def __init__(self, user_id: int, assistants_list: list[sqlite3.Row], timeout=180):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        # --- Pass the fetched list to _get_options ---
        options = self._get_options(assistants_list)
        self.select_menu = discord.ui.Select(
            placeholder="Choose an assistant...",
            options=options,
            disabled=not options or options[0].value == "_disabled_"
            )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    # --- MODIFIED: _get_options now takes the list as argument ---
    def _get_options(self, all_assistants: list[sqlite3.Row]) -> list[discord.SelectOption]:
        """Creates SelectOptions from a pre-fetched list of assistants."""
        options = []
        # The list is already fetched, just process it
        if not all_assistants:
            return [discord.SelectOption(label="No assistants available", value="_disabled_", default=True)]

        for a in all_assistants[:25]: # Limit to 25 options
            options.append(discord.SelectOption(
                label=a['name'][:100],
                description=(a['description'] or "No description")[:100],
                value=str(a['id'])
            ))
        return options

    async def interaction_check(self, i: discord.Interaction) -> bool:
        # ... (interaction_check remains the same) ...
        if i.user.id != self.user_id: await i.response.send_message("Not for you.", ephemeral=True); return False
        return True

        # Inside AssistantSelectView class

    async def select_callback(self, interaction: discord.Interaction):
        """Handles the selection of an assistant from the dropdown."""
        selected_id_str = self.select_menu.values[0]
        if selected_id_str == "_disabled_":
             # Edit the original message the dropdown was attached to
             await interaction.response.edit_message(content="No assistants selected or available.", view=None)
             return

        try: assistant_id = int(selected_id_str)
        except ValueError:
             # Respond ephemerally to the interaction
             await interaction.response.send_message("Invalid selection value.", ephemeral=True)
             return

        # --- Defer the Select Menu interaction EPHEMERALLY ---
        # Acknowledge the selection click quickly and hide the "Thinking..." state from others.
        await interaction.response.defer(thinking=True, ephemeral=True)

        # Fetch assistant data using the ID
        assistant_data = await get_assistant_by_id(assistant_id)

        # Check if assistant exists and belongs to the user
        if not assistant_data or assistant_data['user_id'] != self.user_id:
             # Send an ephemeral error message via followup
             await interaction.followup.send("Assistant not found or you don't own it.", ephemeral=True)
             # We cannot easily edit the original select message anymore because the initial response was ephemeral.
             return

        # --- Generate Thread Title ---
        logger.info(f"Generating title for chat: U:{self.user_id} A:{assistant_id}")
        # Provide a sensible fallback title
        generated_title = f"{interaction.user.display_name} & {assistant_data['name']}"[:100]
        title_prompt = ""
        try:
            # Format the prompt from const.py
            title_prompt = const.THREAD_TITLE_GENERATION_PROMPT.format(
                user_name=interaction.user.display_name,
                assistant_name=assistant_data['name'],
                assistant_desc=assistant_data['description'] or "No description"
            )
            # Call LLM (no assistant guidelines needed for title)
            title_text, _ = await asyncio.wait_for(
                 call_gemini_llm(title_prompt, [], is_assistant_call=False),
                 timeout=15.0 # Short timeout for title generation
                 )

            if title_text and not title_text.startswith("(AI error"):
                 # Clean up the title from LLM output
                 cleaned_title = re.sub(r'[\r\n"\']+', '', title_text).strip() # Remove newlines and quotes
                 if cleaned_title: # Ensure it's not empty after cleaning
                      generated_title = cleaned_title[:100] # Truncate to Discord limit
                 logger.info(f"Generated thread title: '{generated_title}'")
            else:
                 logger.warning(f"LLM failed to generate valid title. Response: '{title_text}'. Using fallback.")

        except AttributeError:
             logger.error("THREAD_TITLE_GENERATION_PROMPT missing/malformed in const.py. Using fallback title.")
        except asyncio.TimeoutError:
             logger.warning("LLM timed out generating thread title. Using fallback.")
        except Exception as e:
             logger.exception(f"Error generating thread title: {e}. Using fallback.")
        # --- END Title Generation ---

        # --- Send the Public/Private choice as a VISIBLE followup ---
        # This message effectively replaces the ephemeral "Thinking..." state for the user.
        try:
            view = ThreadTypeSelectView(self.user_id, assistant_data, generated_title, interaction)
            # Send the message with buttons, wait=True gets the message object
            followup_message = await interaction.followup.send(
                f"Starting chat with **{assistant_data['name']}**.\nChoose thread type:",
                view=view,
                ephemeral=False, # Make this message visible
                wait=True
            )
            view.message = followup_message # Store the message object in the view for later editing

            # No need to edit the original ephemeral response further.
            # If you wanted to edit the message the dropdown was attached to, you'd need to store it earlier.

        except Exception as e:
            logger.exception(f"Failed to send ThreadTypeSelectView for A:{assistant_id} U:{self.user_id}")
            # Try sending an ephemeral error if the followup failed
            try: await interaction.followup.send("An error occurred trying to set up the chat options.", ephemeral=True)
            except discord.HTTPException: pass # Ignore if even the error followup fails

    async def on_timeout(self): logger.debug(f"AssistantSelectView timed out user {self.user_id}")

# Confirmation View for !delete Command
class ConfirmDeleteView(discord.ui.View):
    def __init__(self, assistant_id: int, assistant_name: str, user_id: int, timeout=60):
        super().__init__(timeout=timeout); self.assistant_id = assistant_id; self.assistant_name = assistant_name; self.user_id = user_id; self.confirmed = False; self.message = None
    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.user_id: await i.response.send_message("Not for you.", ephemeral=True); return False
        return True
    def _disable_buttons(self):
        for item in self.children: item.disabled = True
    @discord.ui.button(label="Yes, Delete It", style=discord.ButtonStyle.danger, custom_id="confirm_delete:yes")
    async def confirm_button(self, interaction: discord.Interaction, b: discord.ui.Button):
        logger.debug(f"Confirm delete button clicked by {interaction.user.id}")
        try:
            self.confirmed = True; self._disable_buttons()
            # Respond immediately before DB call
            await interaction.response.edit_message(content=f"Attempting deletion of '{discord.utils.escape_markdown(self.assistant_name)}'...", embed=None, view=self)
            self.stop()
        except Exception as e:
            logger.exception(f"Error in confirm_button interaction response: {e}")
            self.stop() # Stop view even on error
    @discord.ui.button(label="No, Keep It", style=discord.ButtonStyle.secondary, custom_id="confirm_delete:no")
    async def cancel_button(self, interaction: discord.Interaction, b: discord.ui.Button):
        logger.debug(f"Cancel delete button clicked by {interaction.user.id}")
        try:
            self.confirmed = False; self._disable_buttons()
            # Respond immediately
            await interaction.response.edit_message(content="Deletion cancelled.", embed=None, view=self)
            self.stop()
        except Exception as e:
            logger.exception(f"Error in cancel_button interaction response: {e}")
            self.stop() # Stop view even on error
    async def on_timeout(self):
        logger.debug(f"Delete confirm timed out user {self.user_id}")
        if self.message:
            try: self._disable_buttons(); await self.message.edit(content="Deletion confirmation timed out.", embed=None, view=self)
            except discord.HTTPException: pass

# Button View for !create Command
class CreateButtonView(discord.ui.View):
    def __init__(self, author_id: int, timeout=120):
        super().__init__(timeout=timeout); self.author_id = author_id; self.message = None
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id: await interaction.response.send_message("Only command author can use.", ephemeral=True); return False
        return True
    @discord.ui.button(label="Start Creating Assistant", style=discord.ButtonStyle.success, custom_id="create_assistant_start_button")
    async def start_creation(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f"User {interaction.user.id} clicked start creation button.")
        # --- Respond IMMEDIATELY before doing anything else ---
        try:
            # Send the modal as the interaction response
            await interaction.response.send_modal(CreateAssistantModal())
            logger.info(f"Create modal sent successfully via button user {interaction.user.id}")
            # Optionally disable button on original message AFTER modal is sent
            try:
                button.disabled = True; button.label = "Creating..."
                await interaction.edit_original_response(view=self)
            except discord.HTTPException as e:
                 logger.warning(f"Failed to disable create button after modal send: {e}")
        except Exception as e:
            logger.exception(f"FAILED SEND MODAL user {interaction.user.id}: {e}")
            # Try to send an ephemeral followup if the initial response failed somehow (unlikely for send_modal)
            try:
                if not interaction.response.is_done(): # Should always be done after send_modal attempt
                     await interaction.response.send_message("Error opening creation form.", ephemeral=True)
                else:
                     await interaction.followup.send("Error opening the creation form.", ephemeral=True)
            except discord.HTTPException:
                logger.warning("Failed error followup modal send fail.")

    async def on_timeout(self):
        logger.debug(f"Create button timed out user {self.author_id}")
        if self.message:
            try:
                self.children[0].disabled = True;
                await self.message.edit(content="Creation request timed out.", view=self)
            except discord.HTTPException as e:
                logger.warning(f"Failed edit create button timeout: {e}")

# --- Modals ---

# Modal for !create command (launched by CreateButtonView)
# NO starter fields in this version
class CreateAssistantModal(discord.ui.Modal, title='Create New Assistant'):
    # ... (name, description, system_prompt, starter1, starter2 fields) ...
    name = discord.ui.TextInput(label='Assistant Name', placeholder='Unique name for your assistant', required=True, max_length=50)
    description = discord.ui.TextInput(label='Short Description', placeholder='What does this assistant do?', style=discord.TextStyle.short, required=True, max_length=100)
    system_prompt = discord.ui.TextInput(label='System Prompt / Instructions', placeholder='Define personality, task, constraints. React: [react: emoji], Delete user msg: "delete"', style=discord.TextStyle.paragraph, required=True, max_length=1500)
    # No starters in this simplified version

    async def on_submit(self, interaction: discord.Interaction):
        # --- Defer immediately after getting data ---
        user_id = interaction.user.id; logger.info(f"Create modal submitted user {user_id}.")
        temp_name=self.name.value.strip(); temp_desc=self.description.value.strip(); temp_prompt=self.system_prompt.value.strip()

        # --- Acknowledge interaction before potentially slow checks/uploads ---
        await interaction.response.defer(ephemeral=True, thinking=True)

        if not temp_name: await interaction.followup.send("Name empty.", ephemeral=True); return
        user_assistants = await get_assistants(user_id) # Async helper
        if any(a['name'].lower() == temp_name.lower() for a in user_assistants): await interaction.followup.send(f"Name '{temp_name}' used.", ephemeral=True); return

        target_channel = interaction.channel;
        if not target_channel: logger.error(f"Interaction channel None user {user_id}!"); await interaction.followup.send("Error: No channel.", ephemeral=True); return
        logger.info(f"Prompting image user {user_id} in #{target_channel.name}")
        await interaction.followup.send(f"Details for **{discord.utils.escape_markdown(temp_name)}** received! Now, **upload an image** in this channel in 60s.", ephemeral=True)

        msg_to_delete = None
        persistent_avatar_url = None # <--- Initialize variable for the new URL

        try:
            def check_image(m): return m.author.id == user_id and m.channel.id == target_channel.id and m.attachments
            img_msg = await bot.wait_for('message', check=check_image, timeout=60.0);
            msg_to_delete = img_msg # Still keep track to delete the user's message

            if not img_msg.attachments:
                await interaction.followup.send("No image attached.", ephemeral=True); return

            attachment = img_msg.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                await interaction.followup.send("Invalid file type. Please upload an image (PNG, JPG, GIF).", ephemeral=True); return

            # --- NEW: Download and Re-upload ---
            try:
                logger.debug(f"Downloading image from {attachment.url}...")
                image_bytes = await attachment.read()
                logger.debug(f"Image downloaded ({len(image_bytes)} bytes). Finding log channel...")

                # Get the logging channel (ensure it's configured correctly in const.py)
                log_channel = bot.get_channel(const.LOGGING_CHANNEL_ID)
                if not log_channel or not isinstance(log_channel, discord.TextChannel):
                    logger.error(f"Cannot find valid log channel (ID: {const.LOGGING_CHANNEL_ID}) for avatar storage.")
                    # Fallback: Use the original URL (less reliable)
                    # persistent_avatar_url = attachment.url # Keep this line if you want a fallback
                    # Or send an error and stop:
                    await interaction.followup.send("Error: Bot configuration issue (log channel). Cannot store avatar permanently.", ephemeral=True)
                    return # Stop if log channel isn't available

                # Send the image to the log channel as a file attachment
                logger.info(f"Uploading avatar for '{temp_name}' to log channel #{log_channel.name}")
                log_message = await log_channel.send(
                    f"Avatar backup for assistant '{temp_name}' (User: {user_id})",
                    file=discord.File(io.BytesIO(image_bytes), filename=attachment.filename)
                )

                # Get the URL from the *new* message's attachment
                if log_message.attachments:
                    persistent_avatar_url = log_message.attachments[0].url
                    logger.info(f"Avatar stored. Persistent URL: {persistent_avatar_url}")
                else:
                    logger.error(f"Failed to get attachment URL after uploading to log channel {log_channel.id}")
                    # Fallback or error handling
                    # persistent_avatar_url = attachment.url # Fallback?
                    await interaction.followup.send("Error saving avatar image.", ephemeral=True)
                    return # Stop if upload failed

            except discord.HTTPException as e:
                logger.exception(f"HTTP Error downloading/re-uploading avatar: {e}")
                await interaction.followup.send(f"Error processing image (download/upload failed): {e.status}", ephemeral=True)
                return
            except Exception as e:
                logger.exception(f"Unexpected error during avatar download/re-upload: {e}")
                await interaction.followup.send("An unexpected error occurred while processing the image.", ephemeral=True)
                return
            # --- END NEW SECTION ---


            # Check if we successfully got a persistent URL
            if not persistent_avatar_url:
                 logger.error(f"Failed to obtain a persistent avatar URL for assistant '{temp_name}'.")
                 await interaction.followup.send("Error: Could not secure a stable URL for the avatar image.", ephemeral=True)
                 # Optionally, you could decide to proceed without an avatar or use the original unreliable one
                 # persistent_avatar_url = attachment.url # If you want to proceed with the unreliable URL
                 return # Stop creation if avatar URL is critical

            # --- SAVE TO DB using the persistent_avatar_url ---
            logger.info(f"User {user_id} saving assistant '{temp_name}'. Using persistent URL.")
            success, db_message = await add_assistant(user_id, temp_name, temp_desc, temp_prompt, persistent_avatar_url) # Use async

            if success:
                await interaction.followup.send(f"✅ Assistant '{discord.utils.escape_markdown(temp_name)}' created!", ephemeral=True)
            else: await interaction.followup.send(f"❌ Error saving assistant details: {db_message}", ephemeral=True)

        except asyncio.TimeoutError: logger.info(f"Image upload timeout user {user_id}"); await interaction.followup.send("Image upload timed out.", ephemeral=True)
        except Exception as e: logger.exception(f"Outer error image processing user {user_id}: {e}"); await interaction.followup.send("Error processing image.", ephemeral=True)
        finally:
             # --- Delete the USER'S original upload message ---
             if msg_to_delete:
                # Keep the deletion, as the persistent URL is now stored elsewhere
                delete_delay = 10.0; # Shorten delay maybe? Or keep 60s
                logger.info(f"Scheduling deletion user message {msg_to_delete.id} in {delete_delay}s.")
                asyncio.create_task(CreateAssistantModal._delayed_delete(msg_to_delete, delete_delay))

    # Make delayed delete static or move outside if preferred
    @staticmethod
    async def _delayed_delete(message: discord.Message, delay: float):
        await asyncio.sleep(delay)
        try: await message.delete(); logger.info(f"Deleted image msg {message.id}.")
        except discord.HTTPException as e: logger.warning(f"Failed delayed delete {message.id}: {e}")

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception(f'Error CreateAssistantModal: {error}');
        # Use followup because on_submit likely deferred
        try:
            # Check if interaction already responded to or deferred
            if interaction.response.is_done():
                 await interaction.followup.send('Error processing form.', ephemeral=True)
            else:
                 await interaction.response.send_message('Error processing form.', ephemeral=True) # Should not happen if deferred
        except discord.HTTPException: pass

# --- Add near other View definitions ---

class ChangeAvatarView(discord.ui.View):
    def __init__(self, assistant_id: int, user_id: int, assistant_name: str, timeout=120):
        super().__init__(timeout=timeout)
        self.assistant_id = assistant_id
        self.user_id = user_id
        self.assistant_name = assistant_name
        self.message: discord.InteractionMessage | None = None # To store the message this view is attached to

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This button is not for you.", ephemeral=True)
            return False
        return True

    def disable_buttons(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    @discord.ui.button(label="Yes, Change Avatar", style=discord.ButtonStyle.success, custom_id="edit_avatar:yes")
    async def change_avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable_buttons()
        await interaction.response.edit_message(content=f"Okay, please upload the new avatar image for **{discord.utils.escape_markdown(self.assistant_name)}** in this channel (`#{interaction.channel.name}`) now (60s timeout).", view=self)

        msg_to_delete = None
        persistent_avatar_url = None
        try:
            def check_image(m): return m.author.id == self.user_id and m.channel.id == interaction.channel.id and m.attachments
            img_msg = await bot.wait_for('message', check=check_image, timeout=60.0)
            msg_to_delete = img_msg # Keep track to delete user's upload

            if not img_msg.attachments:
                 await interaction.followup.send("No image attached.", ephemeral=True); return # Followup needed after edit

            attachment = img_msg.attachments[0]
            if not attachment.content_type or not attachment.content_type.startswith('image/'):
                await interaction.followup.send("Invalid file type. Please upload an image (PNG, JPG, GIF).", ephemeral=True); return

            # --- Re-use Avatar Upload Logic ---
            try:
                image_bytes = await attachment.read()
                log_channel = bot.get_channel(const.LOGGING_CHANNEL_ID)
                if not log_channel or not isinstance(log_channel, discord.TextChannel):
                    logger.error(...) # Log error
                    await interaction.followup.send("Error: Bot configuration issue (log channel)...", ephemeral=True); return

                log_message = await log_channel.send(f"New avatar for assistant '{self.assistant_name}' (ID: {self.assistant_id}, User: {self.user_id})", file=discord.File(io.BytesIO(image_bytes), filename=attachment.filename))

                if log_message.attachments: persistent_avatar_url = log_message.attachments[0].url
                else: logger.error(...); await interaction.followup.send("Error saving new avatar image.", ephemeral=True); return

            except discord.HTTPException as e: logger.exception(...); await interaction.followup.send(f"Error processing image: {e.status}", ephemeral=True); return
            except Exception as e: logger.exception(...); await interaction.followup.send("Unexpected image error.", ephemeral=True); return
            # --- End Re-used Logic ---

            if not persistent_avatar_url:
                await interaction.followup.send("Error: Could not get new avatar URL.", ephemeral=True); return

            # Update only the avatar in DB
            success, msg = await update_assistant_avatar(self.assistant_id, self.user_id, persistent_avatar_url)

            if success:
                await interaction.followup.send(f"✅ Avatar updated successfully for '{discord.utils.escape_markdown(self.assistant_name)}'!", ephemeral=True)
                # Edit the prompt message to remove buttons
                await interaction.edit_original_response(content=f"Avatar for '{discord.utils.escape_markdown(self.assistant_name)}' updated!", view=None)
            else:
                await interaction.followup.send(f"❌ Failed to update avatar in database: {msg}", ephemeral=True)
                await interaction.edit_original_response(content=f"Failed to update avatar for '{discord.utils.escape_markdown(self.assistant_name)}'. Details not changed.", view=None)

        except asyncio.TimeoutError:
            logger.info(f"Avatar update timed out user {self.user_id} assist {self.assistant_id}")
            await interaction.followup.send("Avatar upload timed out. Other details were saved.", ephemeral=True)
            await interaction.edit_original_response(content="Avatar update timed out.", view=None) # Edit original prompt message
        except Exception as e:
             logger.exception(f"Error processing new avatar for assist {self.assistant_id}: {e}")
             await interaction.followup.send("An error occurred processing the new avatar.", ephemeral=True)
             await interaction.edit_original_response(content="Error during avatar update.", view=None)
        finally:
             # Delete user's upload message
             if msg_to_delete:
                delete_delay = 10.0;
                logger.info(f"Scheduling deletion user avatar upload msg {msg_to_delete.id} in {delete_delay}s.")
                asyncio.create_task(CreateAssistantModal._delayed_delete(msg_to_delete, delete_delay)) # Reuse static delete method

        self.stop() # Stop the view


    @discord.ui.button(label="No, Keep Current Avatar", style=discord.ButtonStyle.secondary, custom_id="edit_avatar:no")
    async def keep_avatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.disable_buttons()
        await interaction.response.edit_message(content=f"Okay, the current avatar for **{discord.utils.escape_markdown(self.assistant_name)}** will be kept. Details updated.", view=None)
        self.stop()

    async def on_timeout(self):
        if self.message: # Check if message exists
             logger.debug(f"ChangeAvatarView timed out user {self.user_id} assist {self.assistant_id}")
             try:
                 self.disable_buttons()
                 await self.message.edit(content="Avatar change prompt timed out. Details were saved.", view=None)
             except discord.NotFound: pass # Original message might have been deleted
             except discord.HTTPException: pass # Ignore other errors editing on timeout
        self.stop()
        
# --- Add near other View definitions ---

class EditAssistantSelectView(discord.ui.View):
    def __init__(self, user_id: int, assistants_list: list[sqlite3.Row], timeout=180):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        options = self._get_options(assistants_list)
        self.select_menu = discord.ui.Select(
            placeholder="Select an assistant to edit...", # Hardcoded placeholder
            options=options,
            disabled=not options or options[0].value == "_disabled_"
        )
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)

    def _get_options(self, user_assistants: list[sqlite3.Row]) -> list[discord.SelectOption]:
        """Creates SelectOptions from the user's assistants."""
        options = []
        if not user_assistants:
            return [discord.SelectOption(label="You have no assistants to edit", value="_disabled_", default=True)] # Hardcoded label

        for a in user_assistants[:25]:
            options.append(discord.SelectOption(
                label=a['name'][:100],
                description=(a['description'] or "No description")[:100],
                value=str(a['id'])
            ))
        return options

    async def interaction_check(self, i: discord.Interaction) -> bool:
        if i.user.id != self.user_id:
            await i.response.send_message("Not for you.", ephemeral=True); return False # Hardcoded error
        return True

    async def select_callback(self, interaction: discord.Interaction):
        selected_id_str = self.select_menu.values[0]
        if selected_id_str == "_disabled_":
             # Edit the original message (since we didn't defer, this works)
             await interaction.response.edit_message(content="No assistants selected or available.", view=None)
             return

        try: assistant_id = int(selected_id_str)
        except ValueError:
             # Send error as initial response
             await interaction.response.send_message("Invalid selection.", ephemeral=True)
             return

        # --- MODIFIED: Fetch data BEFORE responding ---
        # This DB call needs to be fast (under 3 seconds)
        assistant_data = await get_assistant_by_id(assistant_id)

        if not assistant_data or assistant_data['user_id'] != self.user_id:
             # Send error as initial response
             await interaction.response.send_message("Assistant not found or you don't own it.", ephemeral=True)
             # Optionally edit the original select message to remove the view
             try:
                 await interaction.edit_original_response(content="Assistant not found.", view=None)
             except discord.HTTPException: pass # Ignore if editing original fails
             return

        try:
            # This is now the first response to the select interaction
            await interaction.response.send_modal(EditAssistantModal(assistant_data))
            # Optionally edit the original message containing the select view *after* modal sent
            try:
                 await interaction.edit_original_response(content=f"Editing '{assistant_data['name']}'...", view=None)
            except discord.HTTPException as e:
                 logger.warning(f"Failed to edit original select message after modal send: {e}")
        except Exception as e:
             # Catch errors during modal send itself
             logger.exception(f"Failed to send EditAssistantModal for {assistant_id}: {e}")
             # If send_modal fails, we might not be able to respond further easily
             # Try an ephemeral follow-up IF the initial response failed somehow (less likely here)
             try:
                 if not interaction.response.is_done(): # Should be done after send_modal attempt
                     await interaction.response.send_message("Failed to open the assistant editor.", ephemeral=True)
                 else: # Can only use followup if initial response was somehow completed despite error
                     await interaction.followup.send("Failed to open the assistant editor.", ephemeral=True)
             except discord.HTTPException:
                 logger.error("Failed even to send error followup after modal send failure.")

    async def on_timeout(self):
         logger.debug(f"EditAssistantSelectView timed out user {self.user_id}")
         # Optionally edit original message

class EditAssistantModal(discord.ui.Modal):
    # Define fields at class level - they are added automatically
    name_input = discord.ui.TextInput(label="Assistant Name", placeholder="Cannot be empty", required=True, max_length=50)
    desc_input = discord.ui.TextInput(label="Short Description", style=discord.TextStyle.short, required=True, max_length=100)
    prompt_input = discord.ui.TextInput(label="System Prompt / Instructions", style=discord.TextStyle.paragraph, required=True, max_length=1500)

    def __init__(self, assistant_data: sqlite3.Row):
        # Set title FIRST
        super().__init__(title=f"Edit Assistant: {assistant_data['name'][:50]}")
        self.assistant_id = assistant_data['id']
        self.user_id = assistant_data['user_id']
        self.original_name = assistant_data['name']

        # Pre-fill fields with existing data using .default
        self.name_input.default = assistant_data['name']
        self.desc_input.default = assistant_data['description']
        self.prompt_input.default = assistant_data['system_prompt']


    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        new_name = self.name_input.value.strip()
        new_desc = self.desc_input.value.strip()
        new_prompt = self.prompt_input.value.strip()

        if not new_name:
            await interaction.followup.send("Assistant name cannot be empty.", ephemeral=True)
            return

        success, message = await update_assistant(
            self.assistant_id, self.user_id, new_name, new_desc, new_prompt
        )

        if success:
            view = ChangeAvatarView(self.assistant_id, self.user_id, new_name)
            await interaction.followup.send(f"✅ Details for '{discord.utils.escape_markdown(new_name)}' updated!\nDo you also want to change the avatar?", view=view, ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Update failed: {message}", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.exception(f'Error in EditAssistantModal: {error}')
        try:
            # Use followup because on_submit likely deferred before error, or interaction failed
             if interaction.response.is_done():
                 await interaction.followup.send('An error occurred processing the edit form.', ephemeral=True)
             else: # Should not happen if defer is first thing in on_submit
                 await interaction.response.send_message('An error occurred processing the edit form.', ephemeral=True)
        except discord.HTTPException: pass

# --- Global State for Monitor Cooldown ---
monitor_cooldowns = {} # Still needed for mention monitor

# --- Command Channel Check ---
def command_in_control_channel():
    """Check decorator for text commands."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild: return False
        if ctx.channel.id == const.TARGET_CHANNEL_ID: return True
        else:
            target_channel = bot.get_channel(const.TARGET_CHANNEL_ID)
            channel_mention = f"<#{const.TARGET_CHANNEL_ID}>" if target_channel else f"`ID: {const.TARGET_CHANNEL_ID}`"
            try: await ctx.reply(f"Please use bot commands only in {channel_mention}", delete_after=20, mention_author=False)
            except discord.HTTPException: pass
            logger.warning(f"Cmd '{ctx.command.name}' blocked user {ctx.author.id} wrong channel {ctx.channel.id}.")
            return False
    return commands.check(predicate)

# --- Bot Events ---
@bot.event
async def on_ready():
    """Event runs when bot is ready."""
    global db_conn
    logger.info(f'Logged in as {bot.user.name} ({bot.user.id}) | Discord.py {discord.__version__}')
    logger.info(f'Monitoring {len(bot.guilds)} Guilds.')
    logger.info(f'Target Cmd Channel: {const.TARGET_CHANNEL_ID}')
    logger.info(f'Log Channel: {const.LOGGING_CHANNEL_ID}, Mod Role: {const.MOD_ROLE_ID}')
    logger.info(f'LLM Model (GOOGLE): {const.GEMINI_FLASH_MODEL_NAME}') # Name is historical

    # Initialize Database connection if not already done
    if not db_conn:
        await init_db()

    if not db_conn:
        logger.critical("CRITICAL: DB init failed on ready. Functionality limited.")
        return

    # Set up Discord logging handler
    if discord_log_handler and isinstance(discord_log_handler, DiscordHandler):
        try:
            await asyncio.sleep(5)
            discord_log_handler.set_ready(True)
            logger.info("Discord logging handler is ready.")
        except Exception as e:
             logger.error(f"Error setting Discord log handler ready: {e}")

    # Ensure Target Channel exists
    target_channel = bot.get_channel(const.TARGET_CHANNEL_ID)
    if not target_channel: logger.error(f"FATAL: Target command channel {const.TARGET_CHANNEL_ID} not found.")
    elif not isinstance(target_channel, discord.TextChannel): logger.error(f"FATAL: Target command channel {const.TARGET_CHANNEL_ID} not text.")
    else: logger.info(f"Target command channel configured: #{target_channel.name}")

    if not check_thread_timeouts.is_running():
            logger.info("Starting thread timeout check loop...")
            check_thread_timeouts.start()

    logger.info("Bot is ready.")


@bot.event
async def setup_hook():
    """Runs asynchronous setup after login but before connecting to gateway."""
    # --- Initialize DB Here ---
    await init_db()
    if not db_conn:
        logger.critical("Database connection failed during setup_hook. Bot may not function.")
    # --------------------------

    # No command syncing needed for text commands
    logger.info("Setup hook completed.")

@bot.event
async def on_message(message: discord.Message):
    """Handles incoming messages for assistant threads, mention questions, and potential questions within the target channel."""
    # --- Ignore Conditions ---
    if message.author == bot.user or message.author.bot or not message.guild:
        return # Ignore self, other bots, or DMs

    # --- Process Commands First ---
    if message.content.startswith(bot.command_prefix):
        # Let the commands framework handle it (channel check is in decorator)
        await bot.process_commands(message)
        return

    # --- === Block 1: Handle Active Assistant Threads === ---
    if isinstance(message.channel, discord.Thread):
         # Check if this thread is an active assistant chat
         thread_info = await get_active_thread(message.channel.id)
         if thread_info: # It's an active thread we manage
            # Check message limit *before* processing
            if thread_info['message_count'] >= const.MAX_THREAD_MESSAGES:
                logger.debug(f"Thread {message.channel.id} limit reached ({thread_info['message_count']}). Ignoring msg {message.id}.")
                return # Limit reached, do nothing further

            # Fetch assistant details
            assistant = await get_assistant_by_id(thread_info['assistant_id'])
            if not assistant:
                logger.error(f"Thread {message.channel.id} bad assistant {thread_info['assistant_id']}. Removing.")
                await remove_active_thread(message.channel.id)
                try: # Attempt to notify and close the thread
                    await message.channel.send("This assistant seems to have been deleted. Closing this chat thread.")
                    await message.channel.edit(locked=True, archived=True, reason="Assistant deleted")
                except discord.HTTPException as e:
                     logger.warning(f"Failed to notify/close thread {message.channel.id} after assistant deletion: {e}")
                return # Assistant gone

            # Log processing start
            logger.info(f"Processing msg {message.id} in thread {message.channel.id} for '{assistant['name']}' (Count Before: {thread_info['message_count']})")
            ai_response_text = None; history_messages = []; llm_error_occurred = False; suggestion = None; start_time = time.monotonic()

            # Increment count & reset warning timestamp
            incremented_ok = await increment_message_count(message.channel.id)
            if not incremented_ok:
                logger.error(f"Failed increment count thread {message.channel.id}. Aborting msg {message.id}.")
                return # DB error

            current_count = thread_info['message_count'] + 1 # Get updated count for limit check later

            # --- Start Typing Indicator Context Manager ---
            # This will cover history fetch, LLM call, and response sending/actions
            async with message.channel.typing():
                try: # --- Main processing block within typing context ---
                    try: # Fetch History
                        raw_history = [m async for m in message.channel.history(limit=const.MAX_THREAD_MESSAGES + 15, oldest_first=True)]
                        logger.debug(f"Fetched {len(raw_history)} raw messages T:{message.channel.id}")
                    except discord.HTTPException as e:
                        logger.exception(f"Hist fetch fail T:{message.channel.id}: {e}")
                        await message.channel.send("An error occurred while fetching chat history.")
                        llm_error_occurred = True # Mark error to prevent further processing below
                        # Raise or return here if you want to exit the 'async with' block immediately
                        raise e # Re-raise to be caught by the outer exception handler

                    # --- Format History ---
                    history_messages = []
                    bot_id=bot.user.id; assistant_name=assistant['name'];
                    for msg in raw_history:
                         if msg.author.id==bot_id and msg.content.startswith(f"Hi {message.guild.me.mention}") and "Chatting with" in msg.content: continue
                         if msg.author.id==bot_id and msg.content.startswith("**(WH"): continue
                         role=None; content=msg.content.strip();
                         if not content: continue
                         is_assistant_webhook=(msg.webhook_id and msg.author.display_name==assistant_name)
                         is_assistant_fallback=(not msg.webhook_id and msg.author.id==bot_id and content.startswith(f"**{assistant_name}**:"))
                         if is_assistant_webhook or is_assistant_fallback: role='model'; content=content.split(":",1)[1].strip() if is_assistant_fallback and ':' in content else content
                         elif not msg.author.bot: role='user'
                         if role and content: history_messages.append({'role':role,'parts':[content]})
                    current_msg_fmt={'role':'user','parts':[message.content.strip()]}
                    if not history_messages or history_messages[-1].get('parts')!=current_msg_fmt['parts']: history_messages.append(current_msg_fmt)
                    # --- History Pruning ---
                    if history_messages:
                       corrected_history = []; first_user_idx = -1
                       if history_messages[0]['role'] == 'model':
                            first_user_idx = next((i for i, msg in enumerate(history_messages) if msg['role'] == 'user'), -1)
                            if first_user_idx != -1: history_messages = history_messages[first_user_idx:]
                            else: logger.warning(f"History only model messages? T:{message.channel.id}"); history_messages = []
                       if history_messages:
                           corrected_history.append(history_messages[0])
                           for i in range(1, len(history_messages)):
                               current_msg = history_messages[i]; last_added_msg = corrected_history[-1]
                               if current_msg['role'] == last_added_msg['role']: last_added_msg['parts'][0] += "\n" + current_msg['parts'][0]
                               elif current_msg['role'] in ['user', 'model']: corrected_history.append(current_msg)
                           history_messages = corrected_history[-(const.MAX_THREAD_MESSAGES * 2):]
                    if not history_messages or history_messages[-1]['role'] != 'user':
                        logger.warning(f"Invalid history state T:{message.channel.id}. Hist: {history_messages[-3:]}")
                        raise ValueError("Invalid history state for LLM call") # Raise error to exit typing context

                    # --- Call LLM ---
                    llm_timeout = 45.0; assistant_prompt = assistant['system_prompt']
                    if not assistant_prompt:
                        logger.error(f"Assistant {assistant['id']} missing prompt!")
                        await message.channel.send("Error: Assistant configured incorrectly.")
                        raise ValueError("Missing assistant prompt") # Raise error to exit typing context

                    logger.debug(f"Calling Assistant LLM T:{message.channel.id} C:{current_count}")
                    ai_response_text, suggestion = await asyncio.wait_for(
                        call_gemini_llm(assistant_prompt, history_messages, is_assistant_call=True),
                        timeout=llm_timeout
                    )
                    if suggestion: logger.debug(f"Assistant LLM suggestion: '{suggestion}' T:{message.channel.id}")

                    # --- Handle LLM Response / Suggestions ---
                    # Still inside the 'async with' block
                    if suggestion == DELETE_KEYWORD: # Handle delete first
                       logger.info(f"LLM suggested delete msg {message.id} T:{message.channel.id}")
                       try:
                           await message.delete()
                           # Send confirmation (also inside typing block)
                           await message.channel.send(f"_{assistant['name']} deleted the previous message._", delete_after=15)
                       except discord.Forbidden: logger.warning(f"Failed delete msg {message.id} (Forbidden)")
                       except discord.HTTPException as e: logger.warning(f"Failed delete msg {message.id} (HTTP {e.status})")
                       # No further action needed if delete was successful
                    elif suggestion != DELETE_KEYWORD: # Handle text/reaction if not delete
                        parent_channel = message.channel.parent
                        if parent_channel and isinstance(parent_channel, discord.TextChannel):
                            if ai_response_text: # Send text if present
                                 await send_webhook_message(message.channel, parent_channel, assistant, ai_response_text)
                            if suggestion: # Handle reaction if present
                               logger.info(f"LLM suggested reaction '{suggestion}' msg {message.id}")
                               try: await message.add_reaction(suggestion)
                               except discord.HTTPException as e: logger.warning(f"Failed add reaction '{suggestion}' msg {message.id}: {e}")
                        else:
                            logger.error(f"No parent channel T:{message.channel.id} for webhook.")
                            # If no parent, maybe send a fallback message here?
                            # if ai_response_text: await message.channel.send(f"**(WH Err)** {assistant['name']}: {ai_response_text}")
                    else: # Suggestion was DELETE (handled) or suggestion was None
                        if not ai_response_text: # Log if really nothing happened
                            logger.warning(f"LLM call T:{message.channel.id} no actionable output. Text:'{ai_response_text}', Suggest:'{suggestion}'")
                    # --- END Response Handling ---

                except asyncio.TimeoutError:
                    logger.warning(f"LLM timed out T:{message.channel.id}.")
                    await message.channel.send("⏱️ AI response timed out.")
                    llm_error_occurred = True # Mark error
                    # Typing indicator stops automatically as context exits
                except ValueError as e: # Catch specific errors raised above
                     logger.error(f"Processing error T:{message.channel.id}: {e}")
                     llm_error_occurred = True
                     # Typing indicator stops automatically
                except Exception as e: # Catch any other unexpected error
                    logger.exception(f"Unexpected error processing T:{message.channel.id}: {e}")
                    await message.channel.send("⚠️ An unexpected error occurred.")
                    llm_error_occurred = True
                    # Typing indicator stops automatically
            # --- End Typing Indicator Context ---

            processing_time = time.monotonic() - start_time;
            logger.debug(f"[T:{message.channel.id}] Proc finished: {processing_time:.4f}s. Err:{llm_error_occurred}. Suggest:'{suggestion}'.")

            # --- Check Message Limit (After processing and typing indicator stops) ---
            if current_count >= const.MAX_THREAD_MESSAGES:
                logger.info(f"Thread {message.channel.id} reached limit C:{current_count}.")
                try: await message.channel.send(f"---\n**Limit Reached** ({const.MAX_THREAD_MESSAGES} msgs).\nUse `{BOT_PREFIX}end` to close.\n---")
                except discord.HTTPException: pass # Ignore failure to send limit msg

            return # --- IMPORTANT: End processing for assistant thread ---


    # --- === Blocks 2 & 3: Handle TARGET CHANNEL Interactions (Mentions / Q-Helper) === ---
    elif message.channel.id == const.TARGET_CHANNEL_ID:

        # --- Block 2a: @Mention Question Handler (TARGET CHANNEL ONLY) ---
        if bot.user.mentioned_in(message) and message.reference is None:
            channel_id = message.channel.id; now = time.monotonic(); cooldown = getattr(const, 'MONITOR_COOLDOWN_SECONDS', 5)
            last_call_key = f"mention_{channel_id}"; last_call_time = monitor_cooldowns.get(last_call_key, 0)
            if now - last_call_time > cooldown:
                logger.info(f"Direct mention detected in TARGET CHANNEL M:{message.id}. Processing.")
                monitor_cooldowns[last_call_key] = now
                target_channel_mention = f"<#{const.TARGET_CHANNEL_ID}>"
                try: # Format prompt
                    mention_system_prompt = const.MENTION_QA_SYSTEM_PROMPT.format(
                        bot_name=bot.user.name,
                        command_prefix=BOT_PREFIX,
                        target_channel_mention=target_channel_mention,
                        max_user_assistants=getattr(const, 'MAX_USER_ASSISTANTS', 'a certain number'),
                        max_thread_messages=getattr(const, 'MAX_THREAD_MESSAGES', 'many')
                    )
                except AttributeError: logger.error("MENTION_QA_SYSTEM_PROMPT missing/malformed!"); mention_system_prompt = f"You are {bot.user.name}..." # Fallback
                except KeyError as e: logger.error(f"MENTION_QA_SYSTEM_PROMPT missing placeholder: {e}"); mention_system_prompt = f"You are {bot.user.name}..." # Fallback

                bot_mention_pattern = f"<@!?{bot.user.id}>"
                question_text = re.sub(bot_mention_pattern, "", message.content).strip()
                logger.debug(f"MENTION_HANDLER: Extracted question_text='{question_text}' (Length: {len(question_text)})")

                if not question_text or len(question_text) < 3:
                    logger.info(f"Mention question empty/short M:{message.id}. Ignoring.")
                    monitor_cooldowns[last_call_key] = last_call_time # Reset cooldown
                    return # Stop

                question_history = [{'role': 'user', 'parts': [question_text]}]
                monitor_timeout = 25.0; ai_response_text = None; suggestion = None; llm_error_occurred = False
                try: # Call LLM with Typing Indicator
                    async with message.channel.typing(): # <<< Typing for mentions too
                         logger.debug(f"Calling Mention LLM M:{message.id}")
                         ai_response_text, suggestion = await asyncio.wait_for(
                             call_gemini_llm(mention_system_prompt, question_history, is_assistant_call=False), # Pass False
                             timeout=monitor_timeout
                         )
                         if suggestion: logger.warning(f"Mention LLM unexpectedly returned suggestion: '{suggestion}' M:{message.id}")
                except asyncio.TimeoutError: logger.warning(f"Mention LLM timeout M:{message.id}"); llm_error_occurred = True; monitor_cooldowns[last_call_key] = last_call_time
                except Exception as e: logger.exception(f"Error LLM mention M:{message.id}: {e}"); llm_error_occurred = True; monitor_cooldowns[last_call_key] = last_call_time

                # Handle Response (Typing stops automatically)
                if not llm_error_occurred:
                    if ai_response_text:
                        try:
                            await message.reply(ai_response_text[:1950], mention_author=False)
                            if suggestion: logger.info(f"Ignored suggestion '{suggestion}' from mention LLM M:{message.id}") # Ignore suggestion
                        except Exception as e:
                            logger.error(f"Failed reply mention C:{channel_id}: {e}")
                            monitor_cooldowns[last_call_key] = last_call_time # Reset cooldown on send failure
                    elif not suggestion: # Only log warning if NO text AND NO suggestion was returned
                        logger.warning(f"Mention LLM M:{message.id} returned no text/suggestion.")
                        monitor_cooldowns[last_call_key] = last_call_time # Reset cooldown as nothing happened
                return # --- Handled mention ---
            else: # Cooldown Active for Mention
                logger.debug(f"Direct mention C:{channel_id} ignored (cooldown).")
                return # Return if on cooldown for mention

        # --- Block 2b: Question Helper Logic (TARGET CHANNEL ONLY, if not a handled mention) ---
        # Runs ONLY if it's in the target channel AND was NOT a mention handled above
        elif not bot.user.mentioned_in(message) and message.reference is None:
            logger.debug(f"Q-HELPER: Checking Msg {message.id} in TARGET Channel {message.channel.id}")
            content_lower = message.content.lower().strip()
            min_length = 15
            is_potential_question = False
            # Improved Question Detection
            if len(content_lower) >= min_length:
                if content_lower.endswith('?'): is_potential_question = True; logger.debug(f"Q-HELPER: Ends with '?'")
                else:
                    question_keywords = ["how", "what", "why", "when", "where", "who", "which","explain", "define"]
                    aux_verbs = ["is", "are", "am", "was", "were", "do", "does", "did","can", "could", "will", "would", "should", "may", "might", "must"]
                    start_words_to_check = question_keywords + aux_verbs
                    keyword_match = False
                    for word in start_words_to_check:
                        if content_lower.startswith(word + " "):
                            is_potential_question = True; logger.debug(f"Q-HELPER: Starts with '{word} '"); break
                    if not keyword_match: logger.debug(f"Q-HELPER: No '?' or start keyword match.")

            if is_potential_question:
                logger.debug(f"Q-HELPER: Msg {message.id} IS potential question. Checking cooldown.")
                channel_id = message.channel.id # Should be TARGET_CHANNEL_ID
                now = time.monotonic(); cooldown = getattr(const, 'QUESTION_HELPER_COOLDOWN', 600)
                last_call_key = f"q_helper_{channel_id}"; last_call_time = question_helper_cooldowns.get(last_call_key, 0)
                logger.debug(f"Q-HELPER: Cooldown Check C:{channel_id} - Now={now:.2f}, Last={last_call_time:.2f}, Diff={now - last_call_time:.2f}, Required={cooldown}")
                if now - last_call_time > cooldown:
                    logger.info(f"Q-HELPER: Cooldown Passed C:{channel_id}. Attempting send.")
                    question_helper_cooldowns[last_call_key] = now
                    embed = discord.Embed(description=f"It looks like you might be asking a question! If you'd like me ({bot.user.name}) to try and answer it, please mention me directly using `@{bot.user.name}` followed by your question.", color=discord.Color.blue())
                    embed.set_footer(text="This is an automated message.")
                    try:
                        logger.debug(f"Q-HELPER: Attempting message.reply for M:{message.id}")
                        await message.reply(embed=embed, mention_author=True, delete_after=90)
                        logger.info(f"Q-HELPER: Helper sent successfully C:{message.channel.id}.")
                    except discord.Forbidden: logger.warning(f"Q-HELPER: Failed send C:{channel_id} - Forbidden."); question_helper_cooldowns[last_call_key] = last_call_time # Reset CD on perm fail
                    except discord.HTTPException as e: logger.warning(f"Q-HELPER: Failed send C:{channel_id} - HTTP {e.status} {e.text}")
                    except Exception as e: logger.exception(f"Q-HELPER: Unexpected error sending helper C:{channel_id}")
                else: logger.debug(f"Q-HELPER: Cooldown Active for C:{channel_id}. Helper message skipped.")
            else: logger.debug(f"Q-HELPER: Msg {message.id} was NOT flagged as potential question.")
            # No return needed here, function will end naturally after this block

    # --- Block 4: Message was NOT in target channel and NOT in a handled thread ---
    else:
         # Implicitly ignore messages in other channels (no action taken)
         # logger.debug(f"Ignoring message {message.id} in non-target/non-thread channel {message.channel.id}")
         pass

# --- Command Error Handler ---
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Handles errors for text commands."""
    if isinstance(error, commands.CheckFailure):
        # Check failure (e.g., wrong channel) message is now sent by the check decorator itself
        logger.warning(f"CheckFailure handled for command '{ctx.command.name}' by {ctx.author.id}. User notified by check.")
        pass
    elif isinstance(error, commands.CommandNotFound):
         pass # Ignore silently
    elif isinstance(error, commands.MissingRequiredArgument):
         await ctx.reply(f"Missing argument: `{error.param.name}`. Check command usage.", mention_author=False)
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"Slow down! Try again in {error.retry_after:.1f}s.", delete_after=10, mention_author=False)
    elif isinstance(error, commands.CommandInvokeError):
         logger.exception(f"Error executing command '{ctx.command.name}' by {ctx.author.id}: {error.original}", exc_info=error.original)
         await ctx.reply("An error occurred executing that command.", mention_author=False)
    elif isinstance(error, commands.BadArgument):
         await ctx.reply(f"Invalid argument provided. {error}", mention_author=False)
    else:
        logger.error(f"Unhandled command error for '{ctx.command.name}' by {ctx.author.id}: {error}", exc_info=error)
        try: await ctx.reply("An unknown error occurred.", mention_author=False)
        except discord.HTTPException: pass


# --- Text Commands ---

# Decorator for channel check
def command_in_control_channel():
    """Check decorator for text commands."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild: return False
        if ctx.channel.id == const.TARGET_CHANNEL_ID: return True
        else:
            target_channel = bot.get_channel(const.TARGET_CHANNEL_ID)
            channel_mention = f"<#{const.TARGET_CHANNEL_ID}>" if target_channel else f"`ID: {const.TARGET_CHANNEL_ID}`"
            try: await ctx.reply(f"Please use bot commands only in {channel_mention}", delete_after=20, mention_author=False)
            except discord.HTTPException: pass
            logger.warning(f"Cmd '{ctx.command.name}' blocked user {ctx.author.id} wrong channel {ctx.channel.id}.")
            return False
    return commands.check(predicate)

@bot.command(name="edit", aliases=["modify", "change"])
@commands.guild_only()
@command_in_control_channel()
@commands.cooldown(1, 10, commands.BucketType.user)
async def edit_assistant_cmd(ctx: commands.Context):
    """Starts the process to edit an assistant's details."""
    user_id = ctx.author.id
    logger.info(f"User {user_id} initiated !edit in #{ctx.channel.name}")

    # Fetch user's assistants
    my_assistants = await get_assistants(user_id=user_id)

    if not my_assistants:
        await ctx.reply(f"You have no assistants to edit. Use `{BOT_PREFIX}create` first.", mention_author=False) # Hardcoded message
        return

    # Create and send the selection view
    view = EditAssistantSelectView(user_id=user_id, assistants_list=my_assistants)
    await ctx.reply("Which assistant would you like to edit?", view=view, mention_author=False) # Hardcoded message


@bot.command(name="chat", aliases=["talk", "ask"])
@commands.guild_only()
@command_in_control_channel() # Use text command check
@commands.cooldown(1, 5, commands.BucketType.user)
async def start_chat_cmd(ctx: commands.Context):
    """Starts a new chat session via assistant selection."""
    logger.info(f"User {ctx.author.id} initiated !chat in #{ctx.channel.name}")
    # --- MODIFIED: Fetch assistants list first ---
    assistants_list = await get_assistants() # Async helper call
    if not assistants_list:
        await ctx.reply("No assistants available. Use `!create`.", mention_author=False)
        return

    # --- MODIFIED: Pass the fetched list to the view ---
    view = AssistantSelectView(user_id=ctx.author.id, assistants_list=assistants_list)

    # Check if options were generated correctly (view init already did this)
    if view.select_menu.disabled: # Check if disabled flag was set in init
         await ctx.reply("Error creating assistant list or none available.", mention_author=False)
    else:
         # Send message publicly, view interaction is ephemeral
         await ctx.reply("Choose an assistant to start a chat thread:", view=view, mention_author=False)

@bot.command(name="create", aliases=["new", "makeassistant", "addassistant"])
@commands.guild_only()
@command_in_control_channel()
# @commands.cooldown(1, 300, commands.BucketType.user)
async def create_assistant_cmd(ctx: commands.Context):
    """Sends a button to start creating a new assistant."""
    user_id = ctx.author.id
    count = await get_user_assistant_count(user_id) # Async helper
    if count >= const.MAX_USER_ASSISTANTS: await ctx.reply(f"Max {const.MAX_USER_ASSISTANTS} assistants reached.", mention_author=False); return

    logger.info(f"User {user_id} initiated !create in #{ctx.channel.name}. Sending button.")
    try: view = CreateButtonView(author_id=user_id); message = await ctx.reply("Click button to start:", view=view, mention_author=False); view.message = message
    except Exception as e: logger.exception(f"Failed send create button user {user_id}: {e}"); await ctx.reply("Error starting creation.", mention_author=False)

@bot.command(name="delete", aliases=["remove", "delassistant", "rmassistant"])
@commands.guild_only()
@command_in_control_channel()
# @commands.cooldown(1, 10, commands.BucketType.user)
async def delete_assistant_cmd(ctx: commands.Context, *, assistant_name: str = None):
    """Deletes one of your assistants. Lists if no name given."""
    user_id = ctx.author.id
    if not assistant_name:
        my_assistants = await get_assistants(user_id); # Async helper
        if not my_assistants: await ctx.reply("No assistants created.", mention_author=False); return
        embed = discord.Embed(title="Your Assistants", description="Run `!delete \"Name\"`", color=discord.Color.blue()); [embed.add_field(name=a['name'], value=(a['description'] or "*No desc*")[:150], inline=False) for i, a in enumerate(my_assistants[:25])];
        if len(my_assistants) > 25: embed.set_footer(text=f"...and {len(my_assistants)-25} more.")
        await ctx.reply(embed=embed, mention_author=False); return

    assistant_name = assistant_name.strip(); logger.info(f"User {user_id} !delete request for '{assistant_name}'.")
    user_assistants = await get_assistants(user_id); # Async helper
    target_assistant = next((a for a in user_assistants if a['name'].lower() == assistant_name.lower()), None)
    if not target_assistant: await ctx.reply(f"Assistant '{discord.utils.escape_markdown(assistant_name)}' not found.", mention_author=False); return

    view = ConfirmDeleteView(target_assistant['id'], target_assistant['name'], user_id)
    embed = discord.Embed(title="Confirm Deletion", description=f"Delete **{discord.utils.escape_markdown(target_assistant['name'])}**?", color=discord.Color.red());
    if target_assistant['description']: embed.add_field(name="Desc", value=discord.utils.escape_markdown(target_assistant['description']), inline=False)
    embed.set_footer(text="Cannot be undone.")
    confirmation_msg = await ctx.reply(embed=embed, view=view, mention_author=False)
    view.message = confirmation_msg
    await view.wait()

    if view.confirmed:
        logger.info(f"User {user_id} confirmed delete {target_assistant['id']}.")
        deleted = await delete_assistant_by_id(target_assistant['id'], user_id) # Async helper
        if deleted: await confirmation_msg.edit(content=f"✅ Deleted '{discord.utils.escape_markdown(target_assistant['name'])}'.", embed=None, view=None)
        else: await confirmation_msg.edit(content=f"❌ Failed delete.", embed=None, view=None); logger.error(f"Failed DB delete user {user_id} assist {target_assistant['id']}.")
    # Timeout/Cancel handled by view

@bot.command(name="end")
@commands.guild_only()
# NO channel check - must work in threads
async def end_chat_cmd(ctx: commands.Context):
    """Ends the current assistant chat thread."""
    if not isinstance(ctx.channel, discord.Thread):
        if ctx.channel.id == const.TARGET_CHANNEL_ID: await ctx.reply("Use `!end` inside the chat thread.", delete_after=15, mention_author=False)
        else: await ctx.reply("This command only works inside assistant chat threads.", delete_after=10);
        return

    thread_info = await get_active_thread(ctx.channel.id) # Async helper
    if not thread_info: await ctx.reply("This isn't an active assistant chat.", delete_after=10); return

    is_owner=ctx.author.id == thread_info['user_id']; is_mod=False
    if isinstance(ctx.author, discord.Member): mod_role=ctx.guild.get_role(const.MOD_ROLE_ID); is_mod=mod_role and mod_role in ctx.author.roles
    if not is_owner and not is_mod: await ctx.reply("Only starter or mod can end.", ephemeral=True, delete_after=15); return

    logger.info(f"User {ctx.author.id} ending thread {ctx.channel.id} (Owner:{is_owner}, Mod:{is_mod})."); removed = await remove_active_thread(ctx.channel.id) # Async helper
    if not removed: logger.warning(f"Thread {ctx.channel.id} already removed from DB before !end.")

    try: await ctx.send(f"Chat ended by {ctx.author.mention}. Archiving..."); await asyncio.sleep(2); await ctx.channel.edit(locked=True, archived=True, reason=f"Ended by {ctx.author.id}")
    except discord.Forbidden: logger.error(f"Cannot lock/archive thread {ctx.channel.id} (Perms)."); await ctx.send("Chat ended, couldn't archive (perms).")
    except discord.HTTPException as e: logger.exception(f"Failed lock/archive thread {ctx.channel.id}: {e}"); await ctx.send("Chat ended, couldn't archive (error).")

@bot.command(name="myassistants")
@commands.guild_only()
@command_in_control_channel()
@commands.cooldown(1, 3, commands.BucketType.user)
async def my_assistants_cmd(ctx: commands.Context):
    """Lists the assistants created by the command author."""
    user_id = ctx.author.id
    logger.info(f"User {user_id} requested their assistant list in #{ctx.channel.name}")

    # Fetch assistants specifically for this user
    my_assistants = await get_assistants(user_id=user_id)

    if not my_assistants:
        await ctx.reply(f"You haven't created any assistants yet. Use `{BOT_PREFIX}create` to make one!", mention_author=False)
        return

    # Create the embed
    embed = discord.Embed(
        title="Your Assistants",
        description=f"Here are the assistants you've created.\nUse `{BOT_PREFIX}viewassistant <name>` for details or `{BOT_PREFIX}delete <name>` to remove.",
        color=discord.Color.blue() # Or ctx.author.color
    )
    # Set the author of the embed to the user who ran the command
    embed.set_author(name=f"{ctx.author.display_name}'s Assistants", icon_url=ctx.author.display_avatar.url)

    # Set the thumbnail to the avatar of the *first* assistant in the list
    if my_assistants[0]['avatar_url']:
         embed.set_thumbnail(url=my_assistants[0]['avatar_url'])

    # Add fields for each assistant (up to Discord's limit of 25)
    displayed_count = 0
    for assistant in my_assistants[:25]:
        embed.add_field(
            name=f"🤖 {assistant['name'][:50]}", # Limit name length shown
            value=(assistant['description'] or "*No description provided*")[:150], # Limit description length, provide fallback
            inline=False # Show each assistant on a new line
        )
        displayed_count += 1

    # Add a footer if there are more assistants than displayed
    if len(my_assistants) > displayed_count:
        embed.set_footer(text=f"Displaying {displayed_count} of {len(my_assistants)} assistants. More commands coming soon!")

    # Send the embed
    try:
        await ctx.reply(embed=embed, mention_author=False)
    except discord.HTTPException as e:
        logger.error(f"Failed to send 'myassistants' embed for user {user_id}: {e}")
        await ctx.reply("Sorry, I couldn't display your assistants right now.", mention_author=False)

@bot.command(name="viewassistant", aliases=["view", "info", "details"])
@commands.guild_only()
@command_in_control_channel()
@commands.cooldown(1, 5, commands.BucketType.user) # Cooldown: 1 use per 5 sec per user
async def view_assistant_cmd(ctx: commands.Context, *, assistant_name: str = None):
    """Displays detailed information about a specific assistant owned by the user."""
    user_id = ctx.author.id

    if not assistant_name:
        await ctx.reply(f"Please provide the name of the assistant you want to view. Example: `{BOT_PREFIX}viewassistant \"My Assistant\"`\nUse `{BOT_PREFIX}myassistants` to see your list.", mention_author=False)
        return

    assistant_name = assistant_name.strip()
    logger.info(f"User {user_id} requested to view assistant '{assistant_name}' in #{ctx.channel.name}")

    # Fetch only the user's assistants
    my_assistants = await get_assistants(user_id=user_id)

    if not my_assistants:
        await ctx.reply(f"You haven't created any assistants yet. Use `{BOT_PREFIX}create` first.", mention_author=False)
        return

    # Find the specific assistant (case-insensitive)
    target_assistant = None
    for assistant in my_assistants:
        if assistant['name'].lower() == assistant_name.lower():
            target_assistant = assistant
            break # Found it

    if not target_assistant:
        await ctx.reply(f"Could not find an assistant named '{discord.utils.escape_markdown(assistant_name)}' that you own. Check the name using `{BOT_PREFIX}myassistants`.", mention_author=False)
        return

    # Create the details embed
    embed = discord.Embed(
        title=f"🤖 Assistant Details: {target_assistant['name']}",
        color=discord.Color.green() # Or fetch a color associated with the user/assistant
    )
    embed.set_author(name=f"Owned by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)

    # Add Description
    embed.add_field(
        name="Description",
        value=target_assistant['description'] or "*No description provided*",
        inline=False
    )

    # Add System Prompt (Truncate if too long for a field value)
    prompt_display_limit = 1000 # Discord embed field value limit is 1024
    system_prompt_display = target_assistant['system_prompt']
    if len(system_prompt_display) > prompt_display_limit:
        system_prompt_display = system_prompt_display[:prompt_display_limit] + "..."

    embed.add_field(
        name="System Prompt",
        value=f"```\n{system_prompt_display}\n```" if system_prompt_display else "*No prompt set (this shouldn't happen)*", # Use code block for readability
        inline=False
    )

    # Set the image to the assistant's avatar
    if target_assistant['avatar_url']:
        # Check if URL is valid looking before setting
        if target_assistant['avatar_url'].startswith(('http://', 'https://')):
             embed.set_image(url=target_assistant['avatar_url'])
             # Add URL as a separate field for easy access if image doesn't load
             embed.add_field(name="Avatar URL", value=f"[Link]({target_assistant['avatar_url']})", inline=True)
        else:
             embed.add_field(name="Avatar URL", value="*Invalid URL stored*", inline=True)
    else:
         embed.add_field(name="Avatar", value="*No avatar set*", inline=True)


    # Send the embed
    try:
        await ctx.reply(embed=embed, mention_author=False)
    except discord.HTTPException as e:
        logger.error(f"Failed to send 'viewassistant' embed for user {user_id}, assistant '{assistant_name}': {e}")
        await ctx.reply("Sorry, I couldn't display the assistant details right now.", mention_author=False)

# --- Graceful Shutdown ---
async def cleanup():
    logger.info("Shutting down...")
    if check_thread_timeouts.is_running():
        logger.info("Stopping thread timeout task...")
        check_thread_timeouts.cancel()
        # Optional: Wait for the task to actually finish if needed
        # try:
        #     await asyncio.wait_for(check_thread_timeouts.finished(), timeout=5.0)
        # except asyncio.TimeoutError:
        #     logger.warning("Thread timeout task did not finish closing within timeout.")
    await close_db()
    
async def on_close(): logger.info("Received close signal."); await cleanup()
# Signal handling can remain if desired, points to async cleanup
try: import signal; loop=asyncio.get_event_loop(); signals=(signal.SIGTERM, signal.SIGINT); [loop.add_signal_handler(s, lambda s=s: asyncio.create_task(cleanup())) for s in signals]; logger.info("Signal handlers set.")
except: logger.warning("Signal handlers not set (may be Windows).")


# --- Run ---
if __name__ == "__main__":
    # --- MODIFIED: Check different constants ---
    missing_constants = [c for c in [
        'LOGGING_CHANNEL_ID', 'MOD_ROLE_ID', 'TARGET_CHANNEL_ID',
        'GOOGLE_API_KEY_FILE', # New key file
        'GEMINI_FLASH_MODEL_NAME', # New model name
        'DATABASE_FILE', 'LOGGING_MODULE_PATH', 'MAX_USER_ASSISTANTS',
        'MAX_THREAD_MESSAGES', 'ASSISTANT_WEBHOOK_NAME',
        'MONITOR_COOLDOWN_SECONDS',
        'THREAD_INACTIVITY_WARNING_MINUTES',
        'THREAD_INACTIVITY_CLOSE_MINUTES'
        ] if not hasattr(const, c) or getattr(const, c) is None]

    if missing_constants:
         logger.critical(f"CRITICAL ERROR: Constants missing/None in const.py: {', '.join(missing_constants)}")
    elif not TOKEN or not GOOGLE_API_KEY:
         logger.critical("CRITICAL ERROR: Discord Token or Google API Key not loaded.")
    else:
        try:
            logger.info("Starting bot with Google Gemini API...")
            bot.run(TOKEN, log_handler=None, reconnect=True)
        except discord.PrivilegedIntentsRequired:
            logger.critical("CRITICAL: Intents Error - Enable required Privileged Intents.")
        except discord.LoginFailure:
            logger.critical("CRITICAL: Login Failed - Check bot token.")
        except Exception as e:
             logger.critical("CRITICAL: Unhandled error during bot run", exc_info=True)
        except KeyboardInterrupt:
            print("\nShutting down gracefully...")
            if bot:
                # Close the bot's session
                try:
                    bot.loop.run_until_complete(bot.close())
                except:
                    pass
            exit(0)
        finally:
             logger.info("Bot run ended or error occurred. Ensuring DB closed.")
             try: asyncio.run(cleanup()) # Try running async cleanup
             except RuntimeError: # Event loop might already be closed
                 logger.info("Event loop closed, attempting sync DB close.")
                 if db_conn: db_conn.close() # Attempt synchronous close
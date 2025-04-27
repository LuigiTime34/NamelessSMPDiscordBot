#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

PYTHON_EXECUTABLE="python3" # Or just "python" if that points to python3
VENV_DIR="venv"
PID_FILE="bots.pids" # File to store process IDs

# Function to clean up background processes
cleanup() {
    echo "Caught signal, stopping background bots..."
    if [ -f "$PID_FILE" ]; then
        # Read PIDs and kill them gracefully first (SIGTERM)
        while IFS= read -r pid; do
           echo "Stopping PID: $pid"
           kill -TERM "$pid" 2>/dev/null # SIGTERM first
        done < "$PID_FILE"

        # Give them a moment to shut down
        sleep 5

         # Force kill (SIGKILL) any remaining processes
        echo "Forcing shutdown for any remaining processes..."
        while IFS= read -r pid; do
           if ps -p $pid > /dev/null; then # Check if process still exists
               echo "Force killing PID: $pid"
               kill -KILL "$pid" 2>/dev/null # SIGKILL if still running
           fi
        done < "$PID_FILE"

        rm "$PID_FILE" # Remove the PID file
    else
        echo "PID file not found."
    fi
    echo "Cleanup finished."
    exit 0 # Exit script cleanly after cleanup
}

# --- Setup ---

# Check if virtual environment exists, create if not
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    $PYTHON_EXECUTABLE -m venv "$VENV_DIR"
    echo "Virtual environment created."
else
    echo "Virtual environment $VENV_DIR already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "Venv activated."

# Install/update requirements
echo "Installing/updating requirements from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt
echo "Requirements installed."

# --- Trap Signals for Cleanup (Problem 3) ---
# Call cleanup function on SIGINT (Ctrl+C) or SIGTERM
trap cleanup SIGINT SIGTERM

# --- Start Bots ---
echo "Starting bots in the background..."

# Clear previous PID file if it exists
> "$PID_FILE"

# Start each bot script in the background and store its PID
echo "Starting main.py..."
$PYTHON_EXECUTABLE main.py &
echo $! >> "$PID_FILE" # Append the PID of the last background process

echo "Starting run_bear.py..."
$PYTHON_EXECUTABLE run_bear.py &
echo $! >> "$PID_FILE"

echo "Starting run_henry.py..."
$PYTHON_EXECUTABLE run_henry.py &
echo $! >> "$PID_FILE"

echo "Starting trading_bot.py..."
$PYTHON_EXECUTABLE trading_bot.py &
echo $! >> "$PID_FILE"

echo "Starting ai_assistants.py..."
$PYTHON_EXECUTABLE ai_assistants.py &
echo $! >> "$PID_FILE"

echo "All bots started. PIDs stored in $PID_FILE."
echo "Press Ctrl+C to stop all bots."

# --- Wait ---
# Wait for all background processes to finish.
# The 'wait' command without arguments waits for all background jobs
# of the current shell. The trap will interrupt this wait.
wait
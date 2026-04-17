#!/bin/bash

echo "🚀 Starting Task Manager in background..."

# Create data directory if it doesn't exist
mkdir -p data

# Kill any existing process on port 8000
pkill -f "python3 card_task_manager.py" 2>/dev/null || true

# Start the application in background
nohup python3 card_task_manager.py > task_manager.log 2>&1 &

# Get the process ID
PID=$!
echo $PID > task_manager.pid

sleep 2

# Check if process is running
if ps -p $PID > /dev/null; then
    echo "✅ Task Manager started successfully!"
    echo "🆔 Process ID: $PID"
    echo "📝 Log file: task_manager.log"
    echo "🌐 Access at: http://localhost:8000"
    echo ""
    echo "To stop the server, run: ./stop.sh"
else
    echo "❌ Failed to start Task Manager"
    echo "Check task_manager.log for errors"
fi

#!/bin/bash

echo "🛑 Stopping Task Manager..."

# Kill process using PID file
if [ -f task_manager.pid ]; then
    PID=$(cat task_manager.pid)
    if ps -p $PID > /dev/null; then
        kill $PID
        echo "✅ Task Manager stopped (PID: $PID)"
    else
        echo "⚠️  Process not running"
    fi
    rm -f task_manager.pid
else
    # Fallback: kill by process name
    pkill -f "python3 card_task_manager.py"
    echo "✅ Task Manager processes stopped"
fi

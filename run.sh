#!/bin/bash

echo "🚀 Starting Task Manager..."

# Create data directory if it doesn't exist
mkdir -p data

# Start the application
echo "✅ Task Manager starting on port 8000"
echo "🌐 Access at: http://localhost:8000"
echo "📊 Dashboard: http://localhost:8000/"
echo "📋 Tasks: http://localhost:8000/tasks"
echo "📁 Projects: http://localhost:8000/projects"
echo "👥 Team: http://localhost:8000/members"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python3 card_task_manager.py

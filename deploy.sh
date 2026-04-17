#!/bin/bash

echo "🚀 Deploying Task Manager..."

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Please install Docker first."
    echo "💡 Alternative: Use ./start.sh to run without Docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found. Please install Docker Compose first."
    echo "💡 Alternative: Use 'docker build -t task-manager . && docker run -d -p 8000:8000 task-manager'"
    exit 1
fi

# Create data directory if it doesn't exist
mkdir -p data

# Stop existing containers
echo "🛑 Stopping existing containers..."
docker-compose down

# Build and start with Docker Compose
echo "🔨 Building application..."
docker-compose build

echo "🚀 Starting application..."
docker-compose up -d

# Wait for container to be ready
echo "⏳ Waiting for application to start..."
sleep 5

# Check if container is running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Task Manager deployed successfully!"
    echo "🌐 Access at: http://localhost:8000"
    echo "📊 Dashboard: http://localhost:8000/"
    echo "📋 Tasks: http://localhost:8000/tasks"
    echo "📁 Projects: http://localhost:8000/projects"
    echo "👥 Team: http://localhost:8000/members"
    echo ""
    echo "📝 View logs: docker-compose logs -f"
    echo "🛑 Stop: docker-compose down"
else
    echo "❌ Deployment failed!"
    echo "📝 Check logs: docker-compose logs"
fi

# Show container status
echo ""
echo "📊 Container Status:"
docker-compose ps

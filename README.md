# Task Manager with JIRA Integration

A responsive web-based task management application with JIRA integration capabilities.

## Features

- ✅ Task Management (Create, Update, Complete, Delete)
- 📊 Project Organization
- 👥 Team Member Management
- 🔗 JIRA Integration (Import tickets)
- 📱 Mobile Responsive Design
- ⚙️ Settings Panel for JIRA Configuration

## Quick Start

### Option 1: Simple Run (No Docker Required)

```bash
# Navigate to TaskManagement directory
cd TaskManagement

# Start the application
./run.sh

# Access the application
open http://localhost:8000
```

### Option 2: Direct Python Run

```bash
# Navigate to TaskManagement directory
cd TaskManagement

# Start the application
python3 card_task_manager.py

# Access the application
open http://localhost:8000
```

### Option 3: Docker (If Docker is installed)

```bash
# Navigate to TaskManagement directory
cd TaskManagement

# Start with Docker Compose
docker-compose up -d

# Or build and run manually
docker build -t task-manager .
docker run -d -p 8000:8000 task-manager
```

## JIRA Integration Setup

1. Go to the Dashboard and click the ⚙️ settings icon
2. Fill in your JIRA credentials:
   - **Server URL**: `https://your-company.atlassian.net`
   - **Username**: Your JIRA email
   - **API Token**: Generate at https://id.atlassian.com/manage-profile/security/api-tokens
3. Save the configuration
4. Use "Import JIRA" on the Tasks page to import tickets

## Usage

- **Dashboard**: Overview of tasks and quick actions
- **Tasks**: Manage tasks, import from JIRA
- **Projects**: Create and organize projects
- **Team**: Manage team members

## Data Persistence

Task data is stored in JSON files in the `data/` directory.

## Requirements

- Python 3.6 or higher
- No additional dependencies required (uses only Python standard library)

## Port Configuration

Default port: 8000
To change port, edit the `card_task_manager.py` file and modify the port number in the last line.

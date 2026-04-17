#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import html
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timedelta
import urllib.request
import urllib.error
import base64
import psycopg2
from psycopg2.extras import RealDictCursor

class JiraIntegration:
    def __init__(self, server_url="", username="", api_token=""):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.auth = base64.b64encode(f"{username}:{api_token}".encode()).decode() if username and api_token else ""
    
    def get_ticket_details(self, ticket_id):
        if not all([self.server_url, self.username, self.api_token]):
            # Return mock data for testing when credentials not configured
            return {
                "key": ticket_id.upper(),
                "summary": f"Sample JIRA ticket {ticket_id}",
                "description": f"This is a test import of JIRA ticket {ticket_id}. Configure JIRA credentials in Team page for real imports.",
                "status": "To Do",
                "priority": "Medium",
                "assignee": "Unassigned",
                "created": datetime.now().strftime("%Y-%m-%d"),
                "updated": datetime.now().strftime("%Y-%m-%d")
            }
        
        try:
            url = f"{self.server_url}/rest/api/2/issue/{ticket_id}"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Basic {self.auth}")
            req.add_header("Content-Type", "application/json")
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return {
                    "key": data["key"],
                    "summary": data["fields"]["summary"],
                    "description": data["fields"].get("description", ""),
                    "status": data["fields"]["status"]["name"],
                    "priority": data["fields"]["priority"]["name"] if data["fields"].get("priority") else "Medium",
                    "assignee": data["fields"]["assignee"]["displayName"] if data["fields"].get("assignee") else "Unassigned",
                    "created": data["fields"]["created"][:10],
                    "updated": data["fields"]["updated"][:10]
                }
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP Error {e.code}: {e.reason}"}
        except Exception as e:
            return {"error": f"JIRA API error: {str(e)}"}

# Import configuration
try:
    from config import DATABASE_URL, HOST, PORT
except ImportError:
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    HOST = '0.0.0.0'
    PORT = int(os.getenv('PORT', 8000))

class TaskManager:
    def __init__(self):
        self.db_url = DATABASE_URL
        if self.db_url:
            self._init_db()
        else:
            self.file_path = "card_tasks.json"
            if not os.path.exists(self.file_path):
                with open(self.file_path, 'w') as f:
                    json.dump({"projects": [], "members": [], "tasks": []}, f)
                    
    def _get_conn(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
        
    def _init_db(self):
        with self._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS projects (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        description TEXT
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS members (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        role VARCHAR(255)
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        description TEXT,
                        project_id INTEGER REFERENCES projects(id),
                        assigned_to INTEGER REFERENCES members(id),
                        due_date VARCHAR(20),
                        priority VARCHAR(20),
                        completed BOOLEAN DEFAULT FALSE,
                        created VARCHAR(30),
                        assigned_date VARCHAR(30),
                        completed_date VARCHAR(30)
                    )
                ''')
            conn.commit()

    def get_all_data(self):
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM projects")
                    projects = [dict(row) for row in cur.fetchall()]
                    cur.execute("SELECT * FROM members")
                    members = [dict(row) for row in cur.fetchall()]
                    cur.execute("SELECT * FROM tasks")
                    tasks = [dict(row) for row in cur.fetchall()]
                    return {"projects": projects, "members": members, "tasks": tasks}
        else:
            with open(self.file_path, 'r') as f:
                return json.load(f)
                
    def _save_data(self, data):
        if not self.db_url:
            with open(self.file_path, 'w') as f:
                json.dump(data, f, indent=2)

    def add_member(self, name, role="Member"):
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO members (name, role) VALUES (%s, %s) RETURNING id", (name, role))
                    return {"id": cur.fetchone()['id'], "name": name, "role": role}
        data = self.get_all_data()
        member = {"id": len(data["members"]) + 1, "name": name, "role": role}
        data["members"].append(member)
        self._save_data(data)
        return member

    def add_project(self, name, description=""):
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO projects (name, description) VALUES (%s, %s) RETURNING id", (name, description))
                    return {"id": cur.fetchone()['id'], "name": name, "description": description}
        data = self.get_all_data()
        project = {"id": len(data["projects"]) + 1, "name": name, "description": description}
        data["projects"].append(project)
        self._save_data(data)
        return project

    def add_task(self, title, description, project_id, assigned_to=None, due_date=None, priority="medium"):
        created = datetime.now().isoformat()
        assigned_date = datetime.now().isoformat() if assigned_to else None
        
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO tasks (title, description, project_id, assigned_to, due_date, priority, completed, created, assigned_date) 
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """, (title, description, int(project_id) if project_id else None, int(assigned_to) if assigned_to else None, due_date, priority, False, created, assigned_date))
                    return {"id": cur.fetchone()['id']}
                    
        data = self.get_all_data()
        task_data = {
            "id": len(data["tasks"]) + 1,
            "title": title, "description": description, "project_id": int(project_id),
            "assigned_to": int(assigned_to) if assigned_to else None, "due_date": due_date,
            "priority": priority, "completed": False, "created": created, "assigned_date": assigned_date
        }
        data["tasks"].append(task_data)
        self._save_data(data)
        return task_data

    def update_task(self, task_id, title, description, project_id, assigned_to, due_date, priority="medium"):
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT assigned_to FROM tasks WHERE id = %s", (task_id,))
                    old_assigned = cur.fetchone()['assigned_to']
                    assigned_date = datetime.now().isoformat() if str(old_assigned) != str(assigned_to) and assigned_to else None
                    if assigned_date:
                        cur.execute("""
                            UPDATE tasks SET title=%s, description=%s, project_id=%s, assigned_to=%s, due_date=%s, priority=%s, assigned_date=%s WHERE id=%s
                        """, (title, description, int(project_id) if project_id else None, int(assigned_to) if assigned_to else None, due_date, priority, assigned_date, task_id))
                    else:
                        cur.execute("""
                            UPDATE tasks SET title=%s, description=%s, project_id=%s, assigned_to=%s, due_date=%s, priority=%s WHERE id=%s
                        """, (title, description, int(project_id) if project_id else None, int(assigned_to) if assigned_to else None, due_date, priority, task_id))
            return True
            
        data = self.get_all_data()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["title"] = title
                task["description"] = description
                task["project_id"] = int(project_id)
                if str(task.get("assigned_to")) != str(assigned_to) and assigned_to:
                    task["assigned_date"] = datetime.now().isoformat()
                task["assigned_to"] = int(assigned_to) if assigned_to else None
                task["due_date"] = due_date if due_date else None
                task["priority"] = priority
                self._save_data(data)
                return True
        return False

    def complete_task(self, task_id):
        completed_date = datetime.now().isoformat()
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE tasks SET completed=TRUE, completed_date=%s WHERE id=%s", (completed_date, task_id))
            return True
            
        data = self.get_all_data()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["completed"] = True
                task["completed_date"] = completed_date
                self._save_data(data)
                return True
        return False

    def uncomplete_task(self, task_id):
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE tasks SET completed=FALSE, completed_date=NULL WHERE id=%s", (task_id,))
            return True
            
        data = self.get_all_data()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["completed"] = False
                if "completed_date" in task: del task["completed_date"]
                self._save_data(data)
                return True
        return False

    def delete_task(self, task_id):
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
            return True
            
        data = self.get_all_data()
        data["tasks"] = [task for task in data["tasks"] if task["id"] != task_id]
        self._save_data(data)
        return True
    
    def get_project_name(self, project_id):
        data = self.get_all_data()
        for project in data["projects"]:
            if project["id"] == project_id:
                return project["name"]
        return "Unknown"
    
    def get_member_name(self, member_id):
        data = self.get_all_data()
        for member in data["members"]:
            if member["id"] == member_id:
                return member["name"]
        return "Unassigned"
    
    def get_queue_days(self, task):
        if not task.get("assigned_date"):
            return 0
        assigned = datetime.fromisoformat(task["assigned_date"])
        return (datetime.now() - assigned).days
    
    def is_overdue(self, task):
        if not task.get("due_date") or task.get("completed"):
            return False
        due = datetime.fromisoformat(task["due_date"])
        return datetime.now() > due
    
    def group_tasks(self, group_by, layout="horizontal"):
        data = self.get_all_data()
        groups = {}
        for task in data["tasks"]:
            if group_by == "assignee":
                key = self.get_member_name(task.get("assigned_to"))
            elif group_by == "project":
                key = self.get_project_name(task["project_id"])
            elif group_by == "status":
                key = "Completed" if task.get("completed") else "Pending"
            elif group_by == "priority":
                if self.is_overdue(task):
                    key = "Overdue"
                elif task.get("due_date"):
                    key = "Due Soon"
                else:
                    key = "No Deadline"
            else:
                key = "All Tasks"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(task)
        return groups
    
    def get_task_summary(self):
        data = self.get_all_data()
        tasks = data["tasks"]
        total = len(tasks)
        completed = len([t for t in tasks if t.get("completed")])
        pending = len([t for t in tasks if not t.get("completed")])
        overdue = len([t for t in tasks if self.is_overdue(t) and not t.get("completed")])
        
        # Recent activity
        recent_completed = [t for t in tasks if t.get("completed") and t.get("completed_date")]
        recent_completed.sort(key=lambda x: x["completed_date"], reverse=True)
        
        # Upcoming deadlines - only non-completed, non-overdue tasks
        upcoming = [t for t in tasks if t.get("due_date") and not t.get("completed") and not self.is_overdue(t)]
        upcoming.sort(key=lambda x: x["due_date"])
        
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "overdue": overdue,
            "recent_completed": recent_completed[:3],
            "upcoming": upcoming[:5]
        }

tm = TaskManager()
jira = JiraIntegration()

class TaskHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        group_by = query.get('group_by', ['assignee'])[0]
        layout = query.get('layout', ['vertical'])[0]
        filter_type = query.get('filter', ['all'])[0]
        
        if path == '/':
            self.render_dashboard()
        elif path == '/tasks':
            self.render_tasks(group_by, layout, filter_type)
        elif path == '/projects':
            self.render_projects()
        elif path == '/members':
            self.render_members()
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)
        
        if self.path == '/add_member':
            name = params.get('name', [''])[0]
            role = params.get('role', ['Member'])[0]
            if name:
                tm.add_member(name, role)
        elif self.path == '/add_project':
            name = params.get('name', [''])[0]
            description = params.get('description', [''])[0]
            if name:
                tm.add_project(name, description)
        elif self.path == '/import_jira':
            ticket_id = params.get('ticket_id', [''])[0]
            project_id = params.get('project_id', [''])[0]
            if ticket_id and project_id:
                jira_data = jira.get_ticket_details(ticket_id)
                if "error" not in jira_data:
                    # Create task from JIRA data
                    task_id = tm.add_task(
                        title=f"[{jira_data['key']}] {jira_data['summary']}",
                        description=jira_data['description'],
                        project_id=project_id,
                        priority=jira_data['priority'].lower() if jira_data['priority'].lower() in ['low', 'medium', 'high'] else 'medium',
                        assigned_to="",
                        due_date=""
                    )
                    print(f"✅ JIRA ticket {jira_data['key']} imported successfully as task {task_id}")
                else:
                    print(f"❌ JIRA Import Error: {jira_data['error']}")
        elif self.path == '/config_jira':
            server_url = params.get('server_url', [''])[0]
            username = params.get('username', [''])[0]
            api_token = params.get('api_token', [''])[0]
            if server_url and username and api_token:
                jira.server_url = server_url.rstrip('/')
                jira.username = username
                jira.api_token = api_token
                jira.auth = base64.b64encode(f"{username}:{api_token}".encode()).decode()
        elif self.path == '/add_task':
            title = params.get('title', [''])[0]
            description = params.get('description', [''])[0]
            project_id = params.get('project_id', [''])[0]
            assigned_to = params.get('assigned_to', [''])[0]
            due_date = params.get('due_date', [''])[0]
            priority = params.get('priority', ['medium'])[0]
            if title and project_id:
                tm.add_task(title, description, project_id, assigned_to if assigned_to else None, due_date if due_date else None, priority)
        elif self.path == '/update_task':
            task_id = int(params.get('id', [0])[0])
            title = params.get('title', [''])[0]
            description = params.get('description', [''])[0]
            project_id = params.get('project_id', [''])[0]
            assigned_to = params.get('assigned_to', [''])[0]
            due_date = params.get('due_date', [''])[0]
            priority = params.get('priority', ['medium'])[0]
            if title and project_id:
                tm.update_task(task_id, title, description, project_id, assigned_to if assigned_to else None, due_date if due_date else None, priority)
        elif self.path == '/complete':
            task_id = int(params.get('id', [0])[0])
            tm.complete_task(task_id)
        elif self.path == '/uncomplete':
            task_id = int(params.get('id', [0])[0])
            tm.uncomplete_task(task_id)
        elif self.path == '/delete':
            task_id = int(params.get('id', [0])[0])
            tm.delete_task(task_id)
        
        self.send_response(302)
        self.send_header('Location', self.headers.get('Referer', '/'))
        self.end_headers()
    
    def render_dashboard(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        summary = tm.get_task_summary()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Task Manager Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .nav {{ background: #333; color: white; padding: 10px 20px; position: fixed; top: 0; left: 0; right: 0; z-index: 1000; display: flex; justify-content: space-between; align-items: center; }}
        .nav-left {{ display: flex; }}
        .nav a {{ color: white; text-decoration: none; margin: 0 15px; }}
        .nav-right {{ position: relative; }}
        .settings-icon {{ color: white; font-size: 18px; cursor: pointer; padding: 8px; }}
        .settings-dropdown {{ display: none; position: absolute; top: 100%; right: 0; background: white; border: 1px solid #ddd; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); min-width: 300px; z-index: 1001; }}
        .settings-dropdown.show {{ display: block; }}
        .settings-content {{ padding: 15px; }}
        .settings-content h4 {{ margin: 0 0 10px 0; color: #333; }}
        .dashboard {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }}
        .main-layout {{ display: flex; gap: 20px; }}
        .sidebar {{ width: 10%; min-width: 150px; }}
        .content {{ flex: 1; }}
        .card-link {{ text-decoration: none; color: inherit; }}
        .card-link:hover .card {{ transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.15); }}
        .card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center; transition: all 0.2s; cursor: pointer; }}
        .card h3 {{ margin: 0 0 10px 0; color: #333; font-size: 12px; }}
        .card .number {{ font-size: 1.8em; font-weight: bold; color: #007bff; }}
        .overdue {{ color: #dc3545; }}
        .inline-form {{ display: flex; gap: 8px; align-items: center; background: white; padding: 12px; border-radius: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
        .inline-form input, .inline-form select {{ padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; }}
        .inline-form button {{ padding: 8px 12px; border: none; border-radius: 4px; background: #007bff; color: white; cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 4px; }}
        .inline-form button:hover {{ background: #0056b3; }}
        .header-with-forms {{ display: flex; align-items: center; gap: 15px; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; flex-wrap: wrap; }}
        .header-forms {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .header-form {{ display: flex; gap: 4px; align-items: center; background: #f8f9fa; padding: 4px 6px; border-radius: 4px; border: 1px solid #dee2e6; flex-wrap: wrap; }}
        .header-form input, .header-form select {{ padding: 3px 4px; border: none; border-radius: 3px; font-size: 13px; min-width: 80px; }}
        .header-form button {{ padding: 3px 6px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 13px; display: flex; align-items: center; gap: 2px; }}
        .header-form button:hover {{ background: #0056b3; }}
        @media (max-width: 768px) {{ 
            .header-with-forms {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
            .header-forms {{ width: 100%; }}
            .header-form {{ width: 100%; justify-content: space-between; }}
            .header-form input, .header-form select {{ flex: 1; min-width: 60px; }}
            .main-layout {{ flex-direction: column; }}
            .sidebar {{ width: 100%; min-width: auto; }}
            .dashboard {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }}
            .summary-grid {{ flex-direction: column; gap: 15px; }}
            .nav {{ padding: 8px 15px; }}
            .nav a {{ margin: 0 8px; font-size: 14px; }}
            body {{ padding: 15px 10px; }}
        }}
        .summary-section {{ background: white; padding: 8px; border-radius: 6px; margin-bottom: 10px; }}
        .summary-grid {{ display: flex; gap: 10px; }}
        .summary-column {{ flex: 1; }}
        .summary-column h4 {{ margin: 0 0 5px 0; padding-bottom: 4px; border-bottom: 1px solid #007bff; }}
        .summary-grid > div {{ display: flex; flex-direction: column; }}
        .recent-item, .upcoming-item, .overdue-item {{ margin-bottom: 4px; }}
        .recent-item {{ padding: 8px; border-left: 3px solid #28a745; margin: 5px 0; background: #f8f9fa; cursor: pointer; }}
        .recent-item:hover {{ background: #e9ecef; }}
        .upcoming-item {{ padding: 8px; border-left: 3px solid #ffc107; margin: 5px 0; background: #fff3cd; cursor: pointer; }}
        .upcoming-item:hover {{ background: #ffeaa7; }}
        .overdue-item {{ border-left-color: #dc3545; background: #f8d7da; }}
        .overdue-item:hover {{ background: #f1b0b7; }}
    </style>
</head>
<body>
    <div class="nav">
        <div class="nav-left">
            <a href="/">Dashboard</a>
            <a href="/tasks">Tasks</a>
            <a href="/projects">Projects</a>
            <a href="/members">Team</a>
        </div>
        <div class="nav-right">
            <i class="fas fa-cog settings-icon" onclick="toggleSettings()"></i>
            <div class="settings-dropdown" id="settingsDropdown">
                <div class="settings-content">
                    <h4><i class="fas fa-link"></i> JIRA Integration</h4>
                    <form method="POST" action="/config_jira" style="display: flex; flex-direction: column; gap: 8px;">
                        <input type="text" name="server_url" placeholder="JIRA Server URL" value="{jira.server_url}" style="padding: 6px; border: 1px solid #ddd; border-radius: 4px;">
                        <input type="text" name="username" placeholder="Username" value="{jira.username}" style="padding: 6px; border: 1px solid #ddd; border-radius: 4px;">
                        <input type="password" name="api_token" placeholder="API Token" style="padding: 6px; border: 1px solid #ddd; border-radius: 4px;">
                        <button type="submit" style="padding: 8px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;"><i class="fas fa-save"></i> Save JIRA Config</button>
                    </form>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function toggleSettings() {{
            const dropdown = document.getElementById('settingsDropdown');
            dropdown.classList.toggle('show');
        }}
        
        // Close dropdown when clicking outside
        document.addEventListener('click', function(event) {{
            const dropdown = document.getElementById('settingsDropdown');
            const icon = document.querySelector('.settings-icon');
            if (!dropdown.contains(event.target) && !icon.contains(event.target)) {{
                dropdown.classList.remove('show');
            }}
        }});
    </script>
    
    <div class="header-with-forms">
        <h1>Dashboard</h1>
        <div class="header-forms">
            <form method="POST" action="/add_task" class="header-form">
                <input type="text" name="title" placeholder="Task title" required>
                <input type="text" name="description" placeholder="Description">
                <select name="project_id" required>
                    <option value="">Project</option>
                    {self.render_project_options(select_first=True)}
                </select>
                <select name="assigned_to">
                    <option value="">Assignee</option>
                    {self.render_member_options(select_first=True)}
                </select>
                <input type="date" name="due_date" value="{tomorrow}">
                <button type="submit"><i class="fas fa-plus"></i> Task</button>
            </form>
            <form method="POST" action="/add_project" class="header-form">
                <input type="text" name="name" placeholder="Project name" required>
                <input type="text" name="description" placeholder="Description">
                <button type="submit"><i class="fas fa-plus"></i> Project</button>
            </form>
        </div>
    </div>
    
    <div class="main-layout">
        <div class="sidebar">
            <div class="dashboard">
                <a href="/tasks" class="card-link">
                    <div class="card">
                        <h3>Total Tasks</h3>
                        <div class="number">{summary['total']}</div>
                    </div>
                </a>
                <a href="/tasks?filter=completed" class="card-link">
                    <div class="card">
                        <h3>Completed</h3>
                        <div class="number">{summary['completed']}</div>
                    </div>
                </a>
                <a href="/tasks?filter=pending" class="card-link">
                    <div class="card">
                        <h3>Pending</h3>
                        <div class="number">{summary['pending']}</div>
                    </div>
                </a>
                <a href="/tasks?filter=overdue" class="card-link">
                    <div class="card">
                        <h3>Overdue</h3>
                        <div class="number overdue">{summary['overdue']}</div>
                    </div>
                </a>
                <a href="/projects" class="card-link">
                    <div class="card">
                        <h3>Projects</h3>
                        <div class="number">{len(tm.get_all_data()["projects"])}</div>
                    </div>
                </a>
                <a href="/members" class="card-link">
                    <div class="card">
                        <h3>Team Members</h3>
                        <div class="number">{len(tm.get_all_data()["members"])}</div>
                    </div>
                </a>
            </div>
        </div>
        
        <div class="content">
            <div class="summary-section">
                <h3>Activity Summary</h3>
                <div class="summary-grid">
                    <div class="summary-column">
                        <h4>Completed Tasks</h4>
                        {self.render_recent_tasks(summary['recent_completed'])}
                    </div>
                    <div class="summary-column">
                        <h4>Pending Tasks</h4>
                        {self.render_pending_tasks()}
                    </div>
                    <div class="summary-column">
                        <h4>Overdue Tasks</h4>
                        {self.render_overdue_tasks()}
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
        """
        self.wfile.write(html.encode())
    
    def render_tasks(self, group_by, layout, filter_type="all"):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        layout_style = "flex-direction: column;" if layout == "vertical" else "flex-direction: row; flex-wrap: wrap;"
        grid_style = "display: flex; flex-direction: column; gap: 15px;" if layout == "vertical" else "display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px;"
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Tasks</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .nav {{ background: #333; color: white; padding: 10px 20px; position: fixed; top: 0; left: 0; right: 0; z-index: 1000; }}
        .nav a {{ color: white; text-decoration: none; margin: 0 15px; }}
        .header-with-forms {{ display: flex; align-items: center; gap: 15px; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; flex-wrap: wrap; }}
        .header-forms {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .header-form {{ display: flex; gap: 4px; align-items: center; background: #f8f9fa; padding: 4px 6px; border-radius: 4px; border: 1px solid #dee2e6; flex-wrap: wrap; }}
        .header-form input, .header-form select {{ padding: 3px 4px; border: none; border-radius: 3px; font-size: 13px; min-width: 80px; }}
        .header-form button {{ padding: 3px 6px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 13px; display: flex; align-items: center; gap: 2px; }}
        .header-form button:hover {{ background: #0056b3; }}
        @media (max-width: 768px) {{ 
            .header-with-forms {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
            .header-form {{ width: 100%; justify-content: space-between; }}
            .header-form input, .header-form select {{ flex: 1; min-width: 60px; }}
            .nav {{ padding: 8px 15px; }}
            .nav a {{ margin: 0 8px; font-size: 14px; }}
            body {{ padding: 15px 10px; }}
            .controls {{ flex-direction: column; gap: 10px; }}
            .controls .section {{ width: 100%; }}
        }}
        .inline-form {{ display: flex; gap: 8px; align-items: center; background: white; padding: 12px; border-radius: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
        .inline-form input, .inline-form select {{ padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; }}
        .inline-form button {{ padding: 8px 12px; border: none; border-radius: 4px; background: #007bff; color: white; cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 4px; }}
        .inline-form button:hover {{ background: #0056b3; }}
        .controls {{ background: white; padding: 12px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
        .controls .section {{ display: flex; align-items: center; gap: 10px; }}
        .controls .section strong {{ margin-right: 5px; }}
        .controls a {{ text-decoration: none; color: #007bff; padding: 4px 8px; border-radius: 4px; }}
        .controls a:hover {{ background: #e7f3ff; }}
        .controls a.active {{ background: #007bff; color: white; font-weight: bold; }}
        .task-grid {{ {grid_style} }}
        .task-grid.vertical {{ display: flex; flex-direction: column; gap: 10px; }}
        .task-card {{ background: white; padding: 12px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #007bff; }}
        .task-card.completed {{ border-left-color: #28a745; background: #f8f9fa; }}
        .task-card.overdue {{ border-left-color: #dc3545; }}
        .task-title {{ font-weight: bold; margin-bottom: 8px; font-size: 14px; }}
        .task-desc {{ color: #666; font-size: 12px; margin-bottom: 8px; }}
        .task-meta {{ font-size: 11px; color: #888; margin-bottom: 8px; }}
        .task-actions {{ display: flex; gap: 5px; }}
        .task-actions button {{ padding: 6px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 11px; display: flex; align-items: center; gap: 4px; transition: all 0.2s; }}
        .task-actions button:hover {{ transform: translateY(-1px); }}
        .btn-edit {{ background: #ffc107; color: black; }}
        .btn-edit:hover {{ background: #e0a800; }}
        .btn-complete {{ background: #28a745; color: white; }}
        .btn-complete:hover {{ background: #1e7e34; }}
        .btn-undo {{ background: #6c757d; color: white; }}
        .btn-undo:hover {{ background: #545b62; }}
        .btn-delete {{ background: #dc3545; color: white; }}
        .btn-delete:hover {{ background: #c82333; }}
        .edit-form {{ display: none; }}
        .edit-form input, .edit-form select, .edit-form textarea {{ width: 100%; padding: 4px; margin: 2px 0; border: 1px solid #ddd; border-radius: 3px; font-size: 11px; }}
        .edit-form textarea {{ height: 40px; resize: vertical; }}
        .group {{ margin-bottom: 30px; }}
        .group h3 {{ background: #e9ecef; padding: 8px; margin: 0 0 15px 0; border-radius: 4px; font-size: 14px; }}
        .group.vertical {{ display: flex; flex-direction: column; }}
        .group.vertical .task-grid {{ {layout_style} }}
        .overdue-text {{ color: #dc3545; font-weight: bold; }}
        .vertical-layout {{ display: flex; gap: 20px; }}
        .vertical-column {{ flex: 1; min-width: 300px; }}
    </style>
    <script>
        function toggleEdit(uniqueId) {{
            const viewDiv = document.getElementById('view-' + uniqueId);
            const editDiv = document.getElementById('edit-' + uniqueId);
            const isHidden = window.getComputedStyle(editDiv).display === 'none';
            if (isHidden) {{
                viewDiv.style.display = 'none';
                editDiv.style.display = 'block';
            }} else {{
                viewDiv.style.display = 'block';
                editDiv.style.display = 'none';
            }}
        }}
    </script>
</head>
<body>
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/tasks">Tasks</a>
        <a href="/projects">Projects</a>
        <a href="/members">Team</a>
    </div>
    
    <div class="header-with-forms">
        <h1>Tasks</h1>
        <div class="header-forms">
            <form method="POST" action="/add_task" class="header-form">
                <input type="text" name="title" placeholder="Task title" required>
                <input type="text" name="description" placeholder="Description">
                <select name="project_id" required>
                    <option value="">Project</option>
                    {self.render_project_options(select_first=True)}
                </select>
                <select name="assigned_to">
                    <option value="">Assignee</option>
                    {self.render_member_options(select_first=True)}
                </select>
                <input type="date" name="due_date" value="{tomorrow}">
                <button type="submit"><i class="fas fa-plus"></i> Add Task</button>
            </form>
            <form method="POST" action="/import_jira" class="header-form">
                <input type="text" name="ticket_id" placeholder="JIRA Ticket ID" required>
                <select name="project_id" required>
                    <option value="">Project</option>
                    {self.render_project_options(select_first=True)}
                </select>
                <button type="submit"><i class="fas fa-download"></i> Import JIRA</button>
            </form>
        </div>
    </div>
    
    <div class="controls">
        <div class="section">
            <strong>Filter:</strong>
            <a href="/tasks?group_by={group_by}&layout={layout}" class="{'active' if filter_type == 'all' else ''}">All</a>
            <a href="/tasks?group_by={group_by}&layout={layout}&filter=pending" class="{'active' if filter_type == 'pending' else ''}">Pending</a>
            <a href="/tasks?group_by={group_by}&layout={layout}&filter=completed" class="{'active' if filter_type == 'completed' else ''}">Completed</a>
            <a href="/tasks?group_by={group_by}&layout={layout}&filter=overdue" class="{'active' if filter_type == 'overdue' else ''}">Overdue</a>
        </div>
        <div class="section">
            <strong>Group by:</strong>
            <a href="/tasks?group_by=none&layout={layout}&filter={filter_type}" class="{'active' if group_by == 'none' else ''}">None</a>
            <a href="/tasks?group_by=assignee&layout={layout}&filter={filter_type}" class="{'active' if group_by == 'assignee' else ''}">Assignee</a>
            <a href="/tasks?group_by=project&layout={layout}&filter={filter_type}" class="{'active' if group_by == 'project' else ''}">Project</a>
            <a href="/tasks?group_by=status&layout={layout}&filter={filter_type}" class="{'active' if group_by == 'status' else ''}">Status</a>
            <a href="/tasks?group_by=priority&layout={layout}&filter={filter_type}" class="{'active' if group_by == 'priority' else ''}">Priority</a>
        </div>
        <div class="section">
            <strong>Layout:</strong>
            <a href="/tasks?group_by={group_by}&layout=horizontal&filter={filter_type}" class="{'active' if layout == 'horizontal' else ''}">Horizontal</a>
            <a href="/tasks?group_by={group_by}&layout=vertical&filter={filter_type}" class="{'active' if layout == 'vertical' else ''}">Vertical</a>
        </div>
    </div>
    
    <div>
        {self.render_grouped_tasks(group_by, layout, filter_type)}
    </div>
</body>
</html>
        """
        self.wfile.write(html.encode())
    
    def render_projects(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Projects</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .nav {{ background: #333; color: white; padding: 10px 20px; position: fixed; top: 0; left: 0; right: 0; z-index: 1000; }}
        .nav a {{ color: white; text-decoration: none; margin: 0 15px; }}
        .header-with-forms {{ display: flex; align-items: center; gap: 15px; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; flex-wrap: wrap; }}
        .header-forms {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .header-form {{ display: flex; gap: 4px; align-items: center; background: #f8f9fa; padding: 4px 6px; border-radius: 4px; border: 1px solid #dee2e6; flex-wrap: wrap; }}
        .header-form input, .header-form select {{ padding: 3px 4px; border: none; border-radius: 3px; font-size: 13px; min-width: 80px; }}
        .header-form button {{ padding: 3px 6px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 13px; display: flex; align-items: center; gap: 2px; }}
        .header-form button:hover {{ background: #0056b3; }}
        .inline-form {{ display: flex; gap: 8px; align-items: center; background: white; padding: 12px; border-radius: 8px; margin-bottom: 20px; }}
        .inline-form input {{ padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; }}
        .inline-form button {{ padding: 8px 12px; border: none; border-radius: 4px; background: #007bff; color: white; cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 4px; }}
        .inline-form button:hover {{ background: #0056b3; }}
        .project-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 15px; }}
        .project-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        @media (max-width: 768px) {{ 
            .header-with-forms {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
            .header-form {{ width: 100%; justify-content: space-between; }}
            .header-form input, .header-form select {{ flex: 1; min-width: 60px; }}
            .nav {{ padding: 8px 15px; }}
            .nav a {{ margin: 0 8px; font-size: 14px; }}
            body {{ padding: 15px 10px; }}
            .project-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/tasks">Tasks</a>
        <a href="/projects">Projects</a>
        <a href="/members">Team</a>
    </div>
    
    <div class="header-with-forms">
        <h1>Projects</h1>
        <div class="header-forms">
            <form method="POST" action="/add_project" class="header-form">
                <input type="text" name="name" placeholder="Project name" required>
                <input type="text" name="description" placeholder="Description">
                <button type="submit"><i class="fas fa-plus"></i> Add Project</button>
            </form>
        </div>
    </div>
    
    <div class="project-grid">
        {self.render_all_projects()}
    </div>
</body>
</html>
        """
        self.wfile.write(html.encode())
    
    def render_members(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Team Members</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .nav {{ background: #333; color: white; padding: 10px 20px; position: fixed; top: 0; left: 0; right: 0; z-index: 1000; }}
        .nav a {{ color: white; text-decoration: none; margin: 0 15px; }}
        .header-with-forms {{ display: flex; align-items: center; gap: 15px; margin-bottom: 10px; padding: 8px 0; border-bottom: 1px solid #f0f0f0; flex-wrap: wrap; }}
        .header-forms {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .header-form {{ display: flex; gap: 4px; align-items: center; background: #f8f9fa; padding: 4px 6px; border-radius: 4px; border: 1px solid #dee2e6; flex-wrap: wrap; }}
        .header-form input, .header-form select {{ padding: 3px 4px; border: none; border-radius: 3px; font-size: 13px; min-width: 80px; }}
        .header-form button {{ padding: 3px 6px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 13px; display: flex; align-items: center; gap: 2px; }}
        .header-form button:hover {{ background: #0056b3; }}
        .inline-form {{ display: flex; gap: 8px; align-items: center; background: white; padding: 12px; border-radius: 8px; margin-bottom: 20px; }}
        .inline-form input, .inline-form select {{ padding: 6px; border: 1px solid #ddd; border-radius: 4px; font-size: 12px; }}
        .inline-form button {{ padding: 8px 12px; border: none; border-radius: 4px; background: #007bff; color: white; cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 4px; }}
        .inline-form button:hover {{ background: #0056b3; }}
        .member-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }}
        .member-card {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        @media (max-width: 768px) {{ 
            .header-with-forms {{ flex-direction: column; align-items: flex-start; gap: 8px; }}
            .header-form {{ width: 100%; justify-content: space-between; }}
            .header-form input, .header-form select {{ flex: 1; min-width: 60px; }}
            .nav {{ padding: 8px 15px; }}
            .nav a {{ margin: 0 8px; font-size: 14px; }}
            body {{ padding: 15px 10px; }}
            .member-grid {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/tasks">Tasks</a>
        <a href="/projects">Projects</a>
        <a href="/members">Team</a>
    </div>
    
    <h1>Team Members</h1>
    
    <div class="inline-form">
        <form method="POST" action="/add_member" style="display: flex; gap: 8px; align-items: center;">
            <input type="text" name="name" placeholder="Member name" required style="width: 150px;">
            <select name="role" style="width: 100px;">
                <option value="Member">Member</option>
                <option value="Lead">Lead</option>
                <option value="Manager">Manager</option>
            </select>
            <button type="submit"><i class="fas fa-plus"></i> Add Member</button>
        </form>
    </div>
    
    <div class="member-grid">
        {self.render_all_members()}
    </div>
</body>
</html>
        """
        self.wfile.write(html.encode())
    
    def render_recent_tasks(self, tasks):
        if not tasks:
            return "<p>No recent activity</p>"
        html_content = ""
        for task in tasks:
            if task.get("completed_date"):
                completed_date = datetime.fromisoformat(task["completed_date"]).strftime("%m/%d")
                html_content += f'<div class="recent-item" onclick="window.location.href=\'/tasks?filter=completed\'"><strong>{html.escape(task["title"])}</strong><br><small>Completed on {completed_date}</small></div>'
        return html_content if html_content else "<p>No recent activity</p>"
    
    def render_upcoming_tasks(self, tasks):
        if not tasks:
            return "<p>No upcoming deadlines</p>"
        html_content = ""
        for task in tasks:
            if task.get("due_date") and not tm.is_overdue(task):
                due_date = datetime.fromisoformat(task["due_date"]).strftime("%m/%d")
                html_content += f'<div class="upcoming-item" onclick="window.location.href=\'/tasks?filter=upcoming\'"><strong>{html.escape(task["title"])}</strong><br><small>Due: {due_date}</small></div>'
        return html_content if html_content else "<p>No upcoming deadlines</p>"
    
    def render_pending_tasks(self):
        data = tm.get_all_data()
        pending_tasks = [t for t in data["tasks"] if not t.get("completed")]
        if not pending_tasks:
            return "<p>No pending tasks</p>"
        html_content = ""
        for task in pending_tasks[:5]:
            assigned_name = tm.get_member_name(task.get("assigned_to")) if task.get("assigned_to") else "Unassigned"
            html_content += f'<div class="upcoming-item" onclick="window.location.href=\'/tasks?filter=pending\'"><strong>{html.escape(task["title"])}</strong><br><small>Assigned to: {assigned_name}</small></div>'
        return html_content
    
    def render_overdue_tasks(self):
        data = tm.get_all_data()
        overdue_tasks = [t for t in data["tasks"] if t.get("due_date") and tm.is_overdue(t) and not t.get("completed")]
        if not overdue_tasks:
            return "<p>No overdue tasks</p>"
        html_content = ""
        for task in overdue_tasks[:5]:
            due_date = datetime.fromisoformat(task["due_date"]).strftime("%m/%d")
            assigned_name = tm.get_member_name(task.get("assigned_to")) if task.get("assigned_to") else "Unassigned"
            html_content += f'<div class="overdue-item" onclick="window.location.href=\'/tasks?filter=overdue\'"><strong>{html.escape(task["title"])}</strong><br><small>Due: {due_date} | {assigned_name}</small></div>'
        return html_content
    
        data = tm.get_all_data()
        overdue_tasks = [t for t in data["tasks"] if tm.is_overdue(t) and not t.get("completed")]
        if not overdue_tasks:
            return "<p>No overdue tasks</p>"
        html_content = ""
        for task in overdue_tasks[:5]:
            due_date = datetime.fromisoformat(task["due_date"]).strftime("%m/%d")
            html_content += f'<div class="overdue-item" onclick="window.location.href=\'/tasks?filter=overdue\'"><strong>{html.escape(task["title"])}</strong><br><small>OVERDUE: {due_date}</small></div>'
        return html_content
    
    def render_grouped_tasks(self, group_by, layout, filter_type="all"):
        data = tm.get_all_data()
        tasks = data["tasks"]
        
        # Apply filters
        if filter_type == "completed":
            tasks = [t for t in tasks if t.get("completed")]
        elif filter_type == "pending":
            tasks = [t for t in tasks if not t.get("completed")]
        elif filter_type == "overdue":
            tasks = [t for t in tasks if tm.is_overdue(t) and not t.get("completed")]
        elif filter_type == "upcoming":
            tasks = [t for t in tasks if t.get("due_date") and not t.get("completed") and not tm.is_overdue(t)]
        
        if group_by == "none":
            grid_class = "task-grid vertical" if layout == "vertical" else "task-grid"
            return f'<div class="{grid_class}">{self.render_filtered_tasks(tasks)}</div>'
        
        groups = {}
        for task in tasks:
            if group_by == "assignee":
                key = tm.get_member_name(task.get("assigned_to"))
            elif group_by == "project":
                key = tm.get_project_name(task["project_id"])
            elif group_by == "status":
                key = "Completed" if task.get("completed") else "Pending"
            elif group_by == "priority":
                if tm.is_overdue(task):
                    key = "Overdue"
                elif task.get("due_date"):
                    key = "Due Soon"
                else:
                    key = "No Deadline"
            else:
                key = "All Tasks"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(task)
        
        if not groups:
            return "<p>No tasks match the current filter.</p>"
        
        if layout == "vertical":
            html_content = '<div class="vertical-layout">'
            for group_name, group_tasks in groups.items():
                group_prefix = group_name.lower().replace(" ", "-") + "-"
                html_content += f'<div class="vertical-column"><div class="group"><h3>{group_name} ({len(group_tasks)})</h3><div class="task-grid vertical">'
                for task in group_tasks:
                    html_content += self.render_single_task(task, group_prefix)
                html_content += '</div></div></div>'
            html_content += '</div>'
        else:
            html_content = ""
            for group_name, group_tasks in groups.items():
                group_prefix = group_name.lower().replace(" ", "-") + "-"
                html_content += f'<div class="group"><h3>{group_name} ({len(group_tasks)})</h3><div class="task-grid">'
                for task in group_tasks:
                    html_content += self.render_single_task(task, group_prefix)
                html_content += '</div></div>'
        return html_content
    
    def render_filtered_tasks(self, tasks):
        if not tasks:
            return "<p>No tasks match the current filter.</p>"
        
        html_content = ""
        for task in tasks:
            html_content += self.render_single_task(task)
        return html_content
    
    def render_single_task(self, task, prefix=""):
        status_class = "completed" if task.get("completed") else ""
        if tm.is_overdue(task):
            status_class += " overdue"
        
        # Create unique ID prefix to avoid conflicts
        unique_id = f"{prefix}task-{task['id']}" if prefix else f"task-{task['id']}"
        
        project_name = html.escape(tm.get_project_name(task["project_id"]))
        assigned_name = html.escape(tm.get_member_name(task.get("assigned_to")) if task.get("assigned_to") else "Unassigned")
        queue_days = tm.get_queue_days(task)
        priority = task.get("priority", "medium").upper()
        priority_color = {"LOW": "#28a745", "MEDIUM": "#ffc107", "HIGH": "#dc3545"}.get(priority, "#6c757d")
        
        due_info = ""
        if task.get("due_date"):
            due_date = datetime.fromisoformat(task["due_date"]).strftime("%m/%d")
            if tm.is_overdue(task):
                due_info = f'<span class="overdue-text">Due: {due_date} (OVERDUE)</span>'
            else:
                due_info = f'Due: {due_date}'
        
        complete_btn = f'<button class="btn-undo" onclick="document.getElementById(\'uncomplete-{unique_id}\').submit()"><i class="fas fa-undo"></i> Undo</button>' if task.get("completed") else f'<button class="btn-complete" onclick="document.getElementById(\'complete-{unique_id}\').submit()"><i class="fas fa-check"></i> Done</button>'
        
        completion_info = ""
        if task.get("completed") and task.get("completed_date"):
            completed_date = datetime.fromisoformat(task["completed_date"]).strftime("%m/%d")
            completion_info = f' - Completed: {completed_date}'
        
        return f'''
        <div class="task-card {status_class}">
            <div id="view-{unique_id}">
                <div class="task-title">{html.escape(task["title"])}</div>
                <div class="task-desc">{html.escape(task.get("description", ""))}</div>
                <div class="task-meta">
                    {project_name} | {assigned_name} | {queue_days}d | <span style="color: {priority_color}; font-weight: bold;">{priority}</span> | {due_info}{completion_info}
                </div>
                <div class="task-actions">
                    <button class="btn-edit" onclick="toggleEdit('{unique_id}')"><i class="fas fa-edit"></i> Edit</button>
                    {complete_btn}
                    <button class="btn-delete" onclick="document.getElementById('delete-{unique_id}').submit()"><i class="fas fa-trash"></i> Delete</button>
                </div>
            </div>
            <div id="edit-{unique_id}" class="edit-form" style="display: none;">
                <form method="POST" action="/update_task">
                    <input type="hidden" name="id" value="{task["id"]}">
                    <input type="text" name="title" value="{html.escape(task["title"])}" required>
                    <textarea name="description">{html.escape(task.get("description", ""))}</textarea>
                    <select name="project_id" required>
                        {self.render_project_options(task["project_id"])}
                    </select>
                    <select name="assigned_to">
                        <option value="">Unassigned</option>
                        {self.render_member_options(task.get("assigned_to"))}
                    </select>
                    <select name="priority">
                        <option value="low" {'selected' if task.get("priority") == "low" else ''}>Low</option>
                        <option value="medium" {'selected' if task.get("priority", "medium") == "medium" else ''}>Medium</option>
                        <option value="high" {'selected' if task.get("priority") == "high" else ''}>High</option>
                    </select>
                    <input type="date" name="due_date" value="{task.get("due_date", "")}">
                    <div style="margin-top: 8px;">
                        <button type="submit" style="background: #28a745; color: white; border: none; padding: 6px 10px; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;"><i class="fas fa-save"></i> Save</button>
                        <button type="button" onclick="toggleEdit('{unique_id}')" style="background: #6c757d; color: white; border: none; padding: 6px 10px; border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; margin-left: 5px;"><i class="fas fa-times"></i> Cancel</button>
                    </div>
                </form>
            </div>
            <form id="complete-{unique_id}" method="POST" action="/complete" style="display: none;">
                <input type="hidden" name="id" value="{task["id"]}">
            </form>
            <form id="uncomplete-{unique_id}" method="POST" action="/uncomplete" style="display: none;">
                <input type="hidden" name="id" value="{task["id"]}">
            </form>
            <form id="delete-{unique_id}" method="POST" action="/delete" style="display: none;">
                <input type="hidden" name="id" value="{task["id"]}">
            </form>
        </div>
        '''
    
    def render_all_projects(self):
        data = tm.get_all_data()
        if not data["projects"]:
            return "<p>No projects yet.</p>"
        
        html_content = ""
        for project in data["projects"]:
            task_count = len([t for t in data["tasks"] if t["project_id"] == project["id"]])
            html_content += f'''
            <div class="project-card">
                <h4 style="margin: 0 0 8px 0;">{html.escape(project["name"])}</h4>
                <p style="margin: 0 0 8px 0; color: #666; font-size: 12px;">{html.escape(project.get("description", ""))}</p>
                <small style="color: #888;">{task_count} tasks</small>
            </div>
            '''
        return html_content
    
    def render_all_members(self):
        data = tm.get_all_data()
        if not data["members"]:
            return "<p>No team members yet.</p>"
        
        html_content = ""
        for member in data["members"]:
            task_count = len([t for t in data["tasks"] if t.get("assigned_to") == member["id"]])
            html_content += f'''
            <div class="member-card">
                <h4 style="margin: 0 0 8px 0;">{html.escape(member["name"])}</h4>
                <p style="margin: 0 0 8px 0; color: #666; font-size: 12px;">Role: {html.escape(member.get("role", "Member"))}</p>
                <small style="color: #888;">{task_count} assigned tasks</small>
            </div>
            '''
        return html_content
    
    def render_project_options(self, selected_id=None, select_first=False):
        data = tm.get_all_data()
        html_content = ""
        for i, project in enumerate(data["projects"]):
            selected = "selected" if (selected_id == project["id"]) or (select_first and i == 0 and selected_id is None) else ""
            html_content += f'<option value="{project["id"]}" {selected}>{html.escape(project["name"])}</option>'
        return html_content
    
    def render_member_options(self, selected_id=None, select_first=False):
        data = tm.get_all_data()
        html_content = ""
        for i, member in enumerate(data["members"]):
            selected = "selected" if (selected_id == member["id"]) or (select_first and i == 0 and selected_id is None) else ""
            html_content += f'<option value="{member["id"]}" {selected}>{html.escape(member["name"])}</option>'
        return html_content

if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TaskHandler)
    db_type = "PostgreSQL" if DATABASE_URL else "Local JSON"
    print(f"Card Task Manager running at http://{HOST}:{PORT}")
    print(f"Database: {db_type}")
    if not DATABASE_URL:
        print("Warning: DATABASE_URL not set, falling back to ephemeral local JSON.")
    server.serve_forever()

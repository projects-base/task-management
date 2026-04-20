#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import posixpath
from urllib.parse import parse_qs, urlparse

# Import modular components
from database import tm
from jira_api import jira
import ui_templates
import threading
import time
import re

try:
    from config import DATABASE_URL, HOST, PORT
except ImportError:
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    HOST = '0.0.0.0'
    PORT = int(os.getenv('PORT', 8000))

class TaskHandler(BaseHTTPRequestHandler):
    def serve_static(self, path):
        # Prevent path traversal
        clean_path = posixpath.normpath(path)
        file_path = os.path.join(os.getcwd(), clean_path.lstrip('/'))
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            if file_path.endswith('.css'):
                self.send_header('Content-type', 'text/css')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        group_by = query.get('group_by', ['assignee'])[0]
        layout = query.get('layout', ['vertical'])[0]
        filter_type = query.get('filter', ['all'])[0]
        
        if path.startswith('/static/'):
            return self.serve_static(path)
        
        if path == '/':
            html = ui_templates.build_dashboard()
        elif path == '/tasks':
            html = ui_templates.build_tasks(group_by, layout, filter_type)
        elif path == '/projects':
            html = ui_templates.build_projects()
        elif path == '/members':
            html = ui_templates.build_members()
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)
        
        if self.path == '/add_member':
            name = params.get('name', [''])[0]
            role = params.get('role', ['Member'])[0]
            if name: tm.add_member(name, role)
        
        elif self.path == '/add_project':
            name = params.get('name', [''])[0]
            description = params.get('description', [''])[0]
            if name: tm.add_project(name, description)
            
        elif self.path == '/import_jira':
            ticket_id = params.get('ticket_id', [''])[0]
            project_id = params.get('project_id', [''])[0]
            if ticket_id and project_id:
                jira_data = jira.get_ticket_details(ticket_id)
                if "error" not in jira_data:
                    task_id = tm.add_task(
                        title=f"[{jira_data['key']}] {jira_data['summary']}",
                        description=jira_data['description'], project_id=project_id,
                        priority=jira_data['priority'].lower() if jira_data['priority'].lower() in ['low', 'medium', 'high'] else 'medium'
                    )
                    
        elif self.path == '/config_jira':
            server_url = params.get('server_url', [''])[0]
            username = params.get('username', [''])[0]
            api_token = params.get('api_token', [''])[0]
            if server_url and username and api_token:
                import base64
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

def background_sync():
    print("Background sync worker started (3s interval)")
    jira_key_regex = re.compile(r'\[([A-Z]+-\d+)\]')
    
    while True:
        try:
            # Check if JIRA is configured
            if not all([jira.server_url, jira.username, jira.api_token]):
                # Silently skip if not configured, or log once
                time.sleep(10) # Wait longer if not configured
                continue
                
            data = tm.get_all_data()
            tasks = data.get('tasks', [])
            
            for task in tasks:
                title = task.get('title', '')
                match = jira_key_regex.search(title)
                if match:
                    jira_key = match.group(1)
                    # print(f"Polling JIRA for {jira_key}...")
                    jira_data = jira.get_ticket_details(jira_key)
                    
                    if "error" not in jira_data:
                        # Sync status
                        jira_status = jira_data.get('status', '').lower()
                        is_completed = task.get('completed', False)
                        
                        # Logic: If JIRA says Done/Closed, mark as completed
                        if jira_status in ['done', 'closed', 'resolved', 'finished'] and not is_completed:
                            print(f"Sync: Marking {jira_key} as completed based on JIRA status.")
                            tm.complete_task(task['id'])
                        elif jira_status not in ['done', 'closed', 'resolved', 'finished'] and is_completed:
                            # print(f"Sync: Unmarking {jira_key} as completed based on JIRA status.")
                            # tm.uncomplete_task(task['id'])
                            pass # Usually safer to not uncomplete automatically without confirmation
                            
                        # Sync priority
                        jira_priority = jira_data.get('priority', 'medium').lower()
                        current_priority = task.get('priority', 'medium').lower()
                        if jira_priority != current_priority and jira_priority in ['low', 'medium', 'high']:
                            print(f"Sync: Updating priority for {jira_key} to {jira_priority}.")
                            tm.update_task_priority(task['id'], jira_priority)

        except Exception as e:
            print(f"Background sync error: {e}")
            
        time.sleep(3)

if __name__ == "__main__":
    server = HTTPServer((HOST, PORT), TaskHandler)
    db_type = "PostgreSQL" if DATABASE_URL else "Local JSON"
    print(f"Card Task Manager running at http://{HOST}:{PORT}")
    print(f"Database: {db_type}")
    if not DATABASE_URL:
        print("Warning: DATABASE_URL not set, falling back to ephemeral local JSON.")
    
    # Start background scheduler
    threading.Thread(target=background_sync, daemon=True).start()
    
    server.serve_forever()

#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import os
import gzip
import json
import mimetypes
from urllib.parse import parse_qs, urlparse

# Import modular components
from database import tm
from jira_api import jira
import ui_templates
import threading
import time
import re
import urllib.request

try:
    from config import DATABASE_URL, HOST, PORT
except ImportError:
    DATABASE_URL = os.getenv('DATABASE_URL', '')
    HOST = '0.0.0.0'
    PORT = int(os.getenv('PORT', 8000))

# Global to store the host URL for self-pinging
DETECTED_URL = None

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
# Writes are serialized so the JSON-file backend can't lose concurrent updates
WRITE_LOCK = threading.Lock()

class TaskHandler(BaseHTTPRequestHandler):
    def is_ajax(self):
        return self.headers.get('X-Requested-With') == 'fetch'

    def send_body(self, status, body, content_type, cache_control='no-store'):
        if 'gzip' in self.headers.get('Accept-Encoding', '') and len(body) > 1024 and not content_type.startswith('image/'):
            body = gzip.compress(body, compresslevel=5)
            encoding = 'gzip'
        else:
            encoding = None
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache_control)
        if encoding:
            self.send_header('Content-Encoding', encoding)
            self.send_header('Vary', 'Accept-Encoding')
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path):
        # Resolve inside STATIC_DIR only (blocks /static/../card_tasks.json etc.)
        file_path = os.path.realpath(os.path.join(STATIC_DIR, path[len('/static/'):]))
        if not file_path.startswith(STATIC_DIR + os.sep) or not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            return
        with open(file_path, 'rb') as f:
            content = f.read()
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        if content_type.startswith('text/'):
            content_type += '; charset=utf-8'
        self.send_body(200, content, content_type, 'public, max-age=86400')

    def do_GET(self):
        global DETECTED_URL
        if not DETECTED_URL:
            # Detect public URL from Host header
            proto = self.headers.get('X-Forwarded-Proto', 'http')
            DETECTED_URL = f"{proto}://{self.headers.get('Host')}"
            print(f"Detected Public URL: {DETECTED_URL}")

        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        group_by = query.get('group_by', ['assignee'])[0]
        layout = query.get('layout', ['vertical'])[0]
        filter_type = query.get('filter', ['all'])[0]
        assignee = query.get('assignee', [''])[0]
        status = query.get('status', [''])[0]

        if path.startswith('/static/'):
            return self.serve_static(path)

        if path == '/':
            html = ui_templates.build_dashboard()
        elif path == '/tasks':
            html = ui_templates.build_tasks(group_by, layout, filter_type, assignee, status)
        elif path == '/projects':
            html = ui_templates.build_projects()
        elif path == '/members':
            html = ui_templates.build_members()
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_body(200, html.encode('utf-8'), 'text/html; charset=utf-8')

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length') or 0)
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = parse_qs(post_data)

        try:
            with WRITE_LOCK:
                error = self.handle_action(params)
        except Exception as e:
            print(f"POST {self.path} failed: {e}")
            error = "Something went wrong while saving. Please try again."

        if self.is_ajax():
            # In-page actions: reply with JSON, the browser re-renders only the page content
            payload = {"ok": not error, "error": error} if error else {"ok": True}
            self.send_body(400 if error else 200, json.dumps(payload).encode(), 'application/json')
        else:
            self.send_response(302)
            self.send_header('Location', self.headers.get('Referer', '/'))
            self.end_headers()

    def handle_action(self, params):
        """Apply a POST action. Returns an error message, or None on success."""
        if self.path == '/add_member':
            name = params.get('name', [''])[0]
            role = params.get('role', ['Member'])[0]
            if not name.strip(): return "Member name is required."
            tm.add_member(name.strip(), role)

        elif self.path == '/add_project':
            name = params.get('name', [''])[0]
            description = params.get('description', [''])[0]
            if not name.strip(): return "Project name is required."
            tm.add_project(name.strip(), description)

        elif self.path == '/import_jira':
            ticket_id = params.get('ticket_id', [''])[0]
            project_id = params.get('project_id', [''])[0]
            if not (ticket_id and project_id):
                return "JIRA ID and project are required."
            jira_data = jira.get_ticket_details(ticket_id)
            if "error" in jira_data:
                return jira_data["error"]
            tm.add_task(
                title=f"[{jira_data['key']}] {jira_data['summary']}",
                description=jira_data['description'] or "", project_id=project_id,
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
            status = params.get('status', ['todo'])[0]
            if not (title.strip() and project_id):
                return "Title and project are required."
            tm.add_task(title.strip(), description, project_id, assigned_to if assigned_to else None, due_date if due_date else None, priority, status)

        elif self.path == '/update_task':
            task_id = int(params.get('id', [0])[0])
            title = params.get('title', [''])[0]
            description = params.get('description', [''])[0]
            project_id = params.get('project_id', [''])[0]
            assigned_to = params.get('assigned_to', [''])[0]
            due_date = params.get('due_date', [''])[0]
            priority = params.get('priority', ['medium'])[0]
            status = params.get('status', [''])[0]
            if not (title.strip() and project_id):
                return "Title and project are required."
            tm.update_task(task_id, title.strip(), description, project_id, assigned_to if assigned_to else None, due_date if due_date else None, priority, status or None)

        elif self.path == '/set_status':
            task_id = int(params.get('id', [0])[0])
            tm.set_status(task_id, params.get('status', ['todo'])[0])

        elif self.path == '/complete':
            task_id = int(params.get('id', [0])[0])
            tm.complete_task(task_id)

        elif self.path == '/uncomplete':
            task_id = int(params.get('id', [0])[0])
            tm.uncomplete_task(task_id)

        elif self.path == '/delete':
            task_id = int(params.get('id', [0])[0])
            tm.delete_task(task_id)

        else:
            return "Unknown action."
        return None

    def log_message(self, format, *args):
        # Skip logging the 45s keep-alive self-pings
        if 'keepalive' not in self.headers.get('User-Agent', ''):
            super().log_message(format, *args)

def background_sync():
    global DETECTED_URL
    print("Background worker: Waiting for first request to detect public URL...")

    jira_key_regex = re.compile(r'\[([A-Z]+-\d+)\]')

    while True:
        try:
            # 1. Keep-Alive Heartbeat (Self-Ping)
            effective_url = DETECTED_URL or os.getenv('RENDER_EXTERNAL_URL') or os.getenv('PUBLIC_URL')

            if effective_url:
                try:
                    # print(f"Heartbeat: Pinging {effective_url}...")
                    req = urllib.request.Request(effective_url, headers={'User-Agent': 'keepalive'})
                    with urllib.request.urlopen(req, timeout=10) as response:
                        if response.status == 200:
                            # print("Heartbeat: SUCCESS")
                            pass
                except Exception as ping_err:
                    print(f"Heartbeat error: {ping_err}")

            # 2. Jira Sync (Disabled as per user request)
            # if all([jira.server_url, jira.username, jira.api_token]):
            #     data = tm.get_all_data()
            #     ... (logic omitted or commented out)

        except Exception as e:
            print(f"Background sync error: {e}")

        # Poll every 45 seconds to stay within potential 50s activity window
        time.sleep(45)

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), TaskHandler)
    db_type = "PostgreSQL" if DATABASE_URL else "Local JSON"
    print(f"Card Task Manager running at http://{HOST}:{PORT}")
    print(f"Database: {db_type}")
    if not DATABASE_URL:
        print("Warning: DATABASE_URL not set, falling back to ephemeral local JSON.")

    # Start background scheduler
    threading.Thread(target=background_sync, daemon=True).start()

    server.serve_forever()

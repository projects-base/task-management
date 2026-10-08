import os
import json
from datetime import datetime
import time
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

# Import configuration
try:
    from config import DATABASE_URL
except ImportError:
    DATABASE_URL = os.getenv('DATABASE_URL', '')

# Ordered (key, label) pairs; "done" is kept in sync with the legacy `completed` flag
STATUSES = [("todo", "To Do"), ("in_progress", "In Progress"), ("blocked", "Blocked"), ("done", "Done")]
STATUS_LABELS = dict(STATUSES)

class TaskManager:
    def __init__(self):
        self._cached_data = None
        self._cache_time = 0
        # The server is multi-threaded; serialize JSON-file reads/writes
        self._lock = threading.RLock()
        self.db_url = DATABASE_URL
        if self.db_url:
            self.pool = ThreadedConnectionPool(1, 20, self.db_url, cursor_factory=RealDictCursor)
            self._init_db()
        else:
            self.file_path = "card_tasks.json"
            if not os.path.exists(self.file_path):
                with open(self.file_path, 'w') as f:
                    json.dump({"projects": [], "members": [], "tasks": []}, f)

    @contextmanager
    def _get_conn(self):
        conn = self.pool.getconn()
        try:
            yield conn
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            self.pool.putconn(conn)

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
                # Migration: workflow status column, backfilled from the completed flag
                cur.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status VARCHAR(20)")
                cur.execute("UPDATE tasks SET status = CASE WHEN completed THEN 'done' ELSE 'todo' END WHERE status IS NULL")
            conn.commit()

    def get_all_data(self):
        if time.time() - self._cache_time < 1 and self._cached_data:
            return self._cached_data

        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM projects")
                    projects = [dict(row) for row in cur.fetchall()]
                    cur.execute("SELECT * FROM members")
                    members = [dict(row) for row in cur.fetchall()]
                    cur.execute("SELECT * FROM tasks")
                    tasks = [dict(row) for row in cur.fetchall()]
                    self._cached_data = {"projects": projects, "members": members, "tasks": tasks}
                    self._cache_time = time.time()
                    return self._cached_data
        else:
            with self._lock:
                with open(self.file_path, 'r') as f:
                    self._cached_data = json.load(f)
                    self._cache_time = time.time()
                    return self._cached_data

    def _save_data(self, data):
        self._cached_data = None
        self._cache_time = 0
        if not self.db_url:
            with self._lock:
                with open(self.file_path, 'w') as f:
                    json.dump(data, f, indent=2)

    @staticmethod
    def _next_id(items):
        # len()+1 reuses ids after a delete; use max()+1 instead
        return max((item["id"] for item in items), default=0) + 1

    @staticmethod
    def normalize_status(status):
        return status if status in STATUS_LABELS else "todo"

    def get_status(self, task):
        if task.get("completed"):
            return "done"
        status = task.get("status")
        return status if status in STATUS_LABELS and status != "done" else "todo"

    def add_member(self, name, role="Member"):
        self._cache_time = 0
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO members (name, role) VALUES (%s, %s) RETURNING id", (name, role))
                    return {"id": cur.fetchone()['id'], "name": name, "role": role}
        data = self.get_all_data()
        member = {"id": self._next_id(data["members"]), "name": name, "role": role}
        data["members"].append(member)
        self._save_data(data)
        return member

    def add_project(self, name, description=""):
        self._cache_time = 0
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO projects (name, description) VALUES (%s, %s) RETURNING id", (name, description))
                    return {"id": cur.fetchone()['id'], "name": name, "description": description}
        data = self.get_all_data()
        project = {"id": self._next_id(data["projects"]), "name": name, "description": description}
        data["projects"].append(project)
        self._save_data(data)
        return project

    def add_task(self, title, description, project_id, assigned_to=None, due_date=None, priority="medium", status="todo"):
        self._cache_time = 0
        now = datetime.now().isoformat()
        created = now
        assigned_date = now if assigned_to else None
        status = self.normalize_status(status)
        completed = status == "done"
        completed_date = now if completed else None

        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO tasks (title, description, project_id, assigned_to, due_date, priority, completed, created, assigned_date, status, completed_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """, (title, description, int(project_id) if project_id else None, int(assigned_to) if assigned_to else None, due_date, priority, completed, created, assigned_date, status, completed_date))
                    return {"id": cur.fetchone()['id']}

        with self._lock:
            data = self.get_all_data()
            task_data = {
                "id": self._next_id(data["tasks"]),
                "title": title, "description": description, "project_id": int(project_id),
                "assigned_to": int(assigned_to) if assigned_to else None, "due_date": due_date,
                "priority": priority, "completed": completed, "created": created, "assigned_date": assigned_date,
                "status": status
            }
            if completed_date:
                task_data["completed_date"] = completed_date
            data["tasks"].append(task_data)
            self._save_data(data)
            return task_data

    def update_task(self, task_id, title, description, project_id, assigned_to, due_date, priority="medium", status=None):
        self._cache_time = 0
        if status:
            self.set_status(task_id, status)
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

    def set_status(self, task_id, status):
        """Set workflow status; keeps `completed`/`completed_date` consistent with it."""
        self._cache_time = 0
        status = self.normalize_status(status)
        completed = status == "done"
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    if completed:
                        # Keep the original completion date if it was already done
                        cur.execute("UPDATE tasks SET status=%s, completed=TRUE, completed_date=COALESCE(completed_date, %s) WHERE id=%s",
                                    (status, datetime.now().isoformat(), task_id))
                    else:
                        cur.execute("UPDATE tasks SET status=%s, completed=FALSE, completed_date=NULL WHERE id=%s", (status, task_id))
            return True

        with self._lock:
            data = self.get_all_data()
            for task in data["tasks"]:
                if task["id"] == task_id:
                    task["status"] = status
                    task["completed"] = completed
                    if completed:
                        task.setdefault("completed_date", datetime.now().isoformat())
                    else:
                        task.pop("completed_date", None)
                    self._save_data(data)
                    return True
        return False

    def complete_task(self, task_id):
        return self.set_status(task_id, "done")

    def uncomplete_task(self, task_id):
        return self.set_status(task_id, "todo")

    def delete_task(self, task_id):
        self._cache_time = 0
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM tasks WHERE id=%s", (task_id,))
            return True

        data = self.get_all_data()
        data["tasks"] = [task for task in data["tasks"] if task["id"] != task_id]
        self._save_data(data)
        return True

    def update_task_priority(self, task_id, priority):
        self._cache_time = 0
        if self.db_url:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE tasks SET priority=%s WHERE id=%s", (priority.lower(), task_id))
            return True

        data = self.get_all_data()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["priority"] = priority.lower()
                self._save_data(data)
                return True
        return False

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
        try:
            due_str = task["due_date"]
            if 'T' in due_str:
                due_str = due_str.split('T')[0]
            due_date = datetime.strptime(due_str[:10], "%Y-%m-%d").date()
            return datetime.now().date() > due_date
        except Exception:
            return False

    def group_tasks(self, group_by, layout="horizontal"):
        data = self.get_all_data()
        groups = {}
        for task in data["tasks"]:
            if group_by == "assignee":
                key = self.get_member_name(task.get("assigned_to"))
            elif group_by == "project":
                key = self.get_project_name(task["project_id"])
            elif group_by == "status":
                key = STATUS_LABELS[self.get_status(task)]
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
        overdue = len([t for t in tasks if self.is_overdue(t) and not t.get("completed")])
        # Overdue tasks are still pending work, so they count in both buckets
        pending = len([t for t in tasks if not t.get("completed")])

        recent_completed = [t for t in tasks if t.get("completed") and t.get("completed_date")]
        recent_completed.sort(key=lambda x: x["completed_date"], reverse=True)

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

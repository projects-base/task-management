import html
from datetime import datetime, timedelta
from database import tm
from jira_api import jira

def get_base_html(title, body_content):
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="nav">
        <div class="nav-left">
            <a href="/" class="{'active' if title == 'Dashboard' else ''}">Dashboard</a>
            <a href="/tasks" class="{'active' if title == 'Tasks' else ''}">Tasks</a>
            <a href="/projects" class="{'active' if title == 'Projects' else ''}">Projects</a>
            <a href="/members" class="{'active' if title == 'Team Members' else ''}">Team</a>
        </div>
        <div class="nav-right">
            <i class="fas fa-cog settings-icon" onclick="toggleSettings()"></i>
            <div class="settings-dropdown" id="settingsDropdown">
                <div class="settings-content">
                    <h4><i class="fas fa-link"></i> JIRA Integration</h4>
                    <form method="POST" action="/config_jira" style="display: flex; flex-direction: column; gap: 8px;">
                        <input type="text" name="server_url" placeholder="JIRA Server URL" value="{jira.server_url}">
                        <input type="text" name="username" placeholder="Username" value="{jira.username}">
                        <input type="password" name="api_token" placeholder="API Token">
                        <button type="submit" class="btn btn-complete"><i class="fas fa-save"></i> Save Config</button>
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
        document.addEventListener('click', function(event) {{
            const dropdown = document.getElementById('settingsDropdown');
            const icon = document.querySelector('.settings-icon');
            if (dropdown && icon && !dropdown.contains(event.target) && !icon.contains(event.target)) {{
                dropdown.classList.remove('show');
            }}
        }});
        function toggleEdit(uniqueId) {{
            const viewDiv = document.getElementById('view-' + uniqueId);
            const editDiv = document.getElementById('edit-' + uniqueId);
            if (viewDiv && editDiv) {{
                const isHidden = window.getComputedStyle(editDiv).display === 'none';
                viewDiv.style.display = isHidden ? 'none' : 'block';
                editDiv.style.display = isHidden ? 'block' : 'none';
            }}
        }}
        function toggleQuickAdd() {{
            const modal = document.getElementById('quickAddModal');
            modal.classList.toggle('show');
        }}
        function closeQuickAdd(event) {{
            if (event.target.id === 'quickAddModal') {{
                toggleQuickAdd();
            }}
        }}
    </script>
    
    {body_content}
    
    <div class="fab" onclick="toggleQuickAdd()">
        <i class="fas fa-plus"></i>
    </div>
    
    <div id="quickAddModal" class="modal-overlay" onclick="closeQuickAdd(event)">
        <div class="modal-content">
            <div class="modal-header">
                <h3 style="margin: 0;">Quick Add Task</h3>
                <button class="modal-close" onclick="toggleQuickAdd()">&times;</button>
            </div>
            <form method="POST" action="/add_task" style="display: flex; flex-direction: column; gap: 15px;">
                <input type="text" name="title" placeholder="What needs to be done?" required style="width: 100%; font-size: 16px;">
                <textarea name="description" placeholder="Optional details..." rows="3" style="width: 100%;"></textarea>
                <div style="display: flex; gap: 10px;">
                    <select name="project_id" required style="flex: 1;">
                        <option value="">Select Project</option>
                        {render_project_options(select_first=True)}
                    </select>
                    <select name="assigned_to" style="flex: 1;">
                        <option value="">Unassigned</option>
                        {render_member_options(select_first=True)}
                    </select>
                </div>
                <div style="display: flex; gap: 10px; align-items: center;">
                    <select name="priority" style="flex: 1;">
                        <option value="low">Low Priority</option>
                        <option value="medium" selected>Medium Priority</option>
                        <option value="high">High Priority</option>
                    </select>
                    <input type="date" name="due_date" style="flex: 1;" value="{(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')}">
                </div>
                <button type="submit" class="btn btn-complete" style="width: 100%; justify-content: center; margin-top: 10px; font-size: 16px; padding: 12px;">
                    <i class="fas fa-bolt"></i> Add Task Instantly
                </button>
            </form>
        </div>
    </div>
</body>
</html>
    """

def render_project_options(selected_id=None, select_first=False):
    data = tm.get_all_data()
    html_content = ""
    for i, project in enumerate(data["projects"]):
        selected = "selected" if (selected_id == project["id"]) or (select_first and i == 0 and selected_id is None) else ""
        html_content += f'<option value="{project["id"]}" {selected}>{html.escape(project["name"])}</option>'
    return html_content

def render_member_options(selected_id=None, select_first=False):
    data = tm.get_all_data()
    html_content = ""
    for i, member in enumerate(data["members"]):
        selected = "selected" if (selected_id == member["id"]) or (select_first and i == 0 and selected_id is None) else ""
        html_content += f'<option value="{member["id"]}" {selected}>{html.escape(member["name"])}</option>'
    return html_content

def render_recent_tasks(tasks):
    if not tasks: return "<p style='color: var(--text-muted);'>No recent activity</p>"
    html_content = ""
    for task in tasks:
        if task.get("completed_date"):
            completed_date = datetime.fromisoformat(task["completed_date"]).strftime("%m/%d")
            html_content += f'<div class="recent-item" onclick="window.location.href=\'/tasks?filter=completed\'"><strong>{html.escape(task["title"])}</strong><br><small>Completed on {completed_date}</small></div>'
    return html_content if html_content else "<p style='color: var(--text-muted);'>No recent activity</p>"

def render_pending_tasks():
    data = tm.get_all_data()
    pending_tasks = [t for t in data["tasks"] if not t.get("completed")]
    if not pending_tasks: return "<p style='color: var(--text-muted);'>No pending tasks</p>"
    html_content = ""
    for task in pending_tasks[:5]:
        assigned_name = tm.get_member_name(task.get("assigned_to")) if task.get("assigned_to") else "Unassigned"
        html_content += f'<div class="upcoming-item" onclick="window.location.href=\'/tasks?filter=pending\'"><strong>{html.escape(task["title"])}</strong><br><small>Assigned to: {assigned_name}</small></div>'
    return html_content

def render_overdue_tasks():
    data = tm.get_all_data()
    overdue_tasks = [t for t in data["tasks"] if t.get("due_date") and tm.is_overdue(t) and not t.get("completed")]
    if not overdue_tasks: return "<p style='color: var(--text-muted);'>No overdue tasks</p>"
    html_content = ""
    for task in overdue_tasks[:5]:
        due_date = datetime.fromisoformat(task["due_date"]).strftime("%m/%d")
        assigned_name = tm.get_member_name(task.get("assigned_to")) if task.get("assigned_to") else "Unassigned"
        html_content += f'<div class="overdue-item" onclick="window.location.href=\'/tasks?filter=overdue\'"><strong>{html.escape(task["title"])}</strong><br><small>Due: {due_date} | {assigned_name}</small></div>'
    return html_content

def render_single_task(task, prefix=""):
    status_class = "completed" if task.get("completed") else ""
    if tm.is_overdue(task): status_class += " overdue"
    
    unique_id = f"{prefix}task-{task['id']}" if prefix else f"task-{task['id']}"
    project_name = html.escape(tm.get_project_name(task["project_id"]))
    assigned_name = html.escape(tm.get_member_name(task.get("assigned_to")) if task.get("assigned_to") else "Unassigned")
    queue_days = tm.get_queue_days(task)
    priority = task.get("priority", "medium").upper()
    priority_color = {"LOW": "#10b981", "MEDIUM": "#f59e0b", "HIGH": "#ef4444"}.get(priority, "var(--text-muted)")
    
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
                <span><i class="fas fa-folder"></i> {project_name}</span>
                <span><i class="fas fa-user"></i> {assigned_name}</span>
                <span><i class="fas fa-clock"></i> {queue_days}d</span>
                <span style="color: {priority_color}; font-weight: bold;"><i class="fas fa-flag"></i> {priority}</span>
                <span>{due_info}{completion_info}</span>
            </div>
            <div class="task-actions">
                <button class="btn-edit" onclick="toggleEdit('{unique_id}')"><i class="fas fa-edit"></i> Edit</button>
                {complete_btn}
                <button class="btn-delete" onclick="document.getElementById('delete-{unique_id}').submit()"><i class="fas fa-trash"></i> Delete</button>
            </div>
        </div>
        <div id="edit-{unique_id}" class="edit-form" style="display: none; margin-top: 15px;">
            <form method="POST" action="/update_task" style="display: flex; flex-direction: column; gap: 8px;">
                <input type="hidden" name="id" value="{task["id"]}">
                <input type="text" name="title" value="{html.escape(task["title"])}" required>
                <textarea name="description" rows="3">{html.escape(task.get("description", ""))}</textarea>
                <select name="project_id" required>
                    {render_project_options(task["project_id"])}
                </select>
                <select name="assigned_to">
                    <option value="">Unassigned</option>
                    {render_member_options(task.get("assigned_to"))}
                </select>
                <select name="priority">
                    <option value="low" {'selected' if task.get("priority") == "low" else ''}>Low</option>
                    <option value="medium" {'selected' if task.get("priority", "medium") == "medium" else ''}>Medium</option>
                    <option value="high" {'selected' if task.get("priority") == "high" else ''}>High</option>
                </select>
                <input type="date" name="due_date" value="{task.get("due_date", "")}">
                <div style="display: flex; gap: 10px; margin-top: 10px;">
                    <button type="submit" class="btn-complete"><i class="fas fa-save"></i> Save</button>
                    <button type="button" class="btn-edit" onclick="toggleEdit('{unique_id}')"><i class="fas fa-times"></i> Cancel</button>
                </div>
            </form>
        </div>
        <form id="complete-{unique_id}" method="POST" action="/complete" style="display: none;"><input type="hidden" name="id" value="{task["id"]}"></form>
        <form id="uncomplete-{unique_id}" method="POST" action="/uncomplete" style="display: none;"><input type="hidden" name="id" value="{task["id"]}"></form>
        <form id="delete-{unique_id}" method="POST" action="/delete" style="display: none;"><input type="hidden" name="id" value="{task["id"]}"></form>
    </div>
    '''

def render_filtered_tasks(tasks):
    if not tasks: return "<p style='color: var(--text-muted);'>No tasks match the current filter.</p>"
    return "".join(render_single_task(task) for task in tasks)

def build_dashboard():
    summary = tm.get_task_summary()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    body = f"""
    <div class="header-with-forms">
        <h1>Dashboard</h1>
        <div class="header-forms">
            <form method="POST" action="/add_task" class="header-form">
                <input type="text" name="title" placeholder="Task title" required>
                <input type="text" name="description" placeholder="Description">
                <select name="project_id" required>
                    <option value="">Project</option>
                    {render_project_options(select_first=True)}
                </select>
                <select name="assigned_to">
                    <option value="">Assignee</option>
                    {render_member_options(select_first=True)}
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
                        <div class="number" style="color: var(--success);">{summary['completed']}</div>
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
                        <div class="number" style="color: var(--danger);">{summary['overdue']}</div>
                    </div>
                </a>
            </div>
        </div>
        <div class="content">
            <div class="summary-section">
                <h3 style="margin-bottom: 20px;">Activity Summary</h3>
                <div class="summary-grid">
                    <div class="summary-column">
                        <h4>Completed Tasks</h4>
                        {render_recent_tasks(summary['recent_completed'])}
                    </div>
                    <div class="summary-column">
                        <h4>Pending Tasks</h4>
                        {render_pending_tasks()}
                    </div>
                    <div class="summary-column">
                        <h4>Overdue Tasks</h4>
                        {render_overdue_tasks()}
                    </div>
                </div>
            </div>
        </div>
    </div>
    """
    return get_base_html("Dashboard", body)

def build_tasks(group_by, layout, filter_type):
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    layout_class = "vertical" if layout == "vertical" else ""
    
    data = tm.get_all_data()
    tasks = data["tasks"]
    if filter_type == "completed": tasks = [t for t in tasks if t.get("completed")]
    elif filter_type == "pending": tasks = [t for t in tasks if not t.get("completed")]
    elif filter_type == "overdue": tasks = [t for t in tasks if tm.is_overdue(t) and not t.get("completed")]
    elif filter_type == "upcoming": tasks = [t for t in tasks if t.get("due_date") and not t.get("completed") and not tm.is_overdue(t)]
    
    grid_content = ""
    if group_by == "none":
        grid_content = f'<div class="task-grid {layout_class}">{render_filtered_tasks(tasks)}</div>'
    else:
        groups = {}
        for task in tasks:
            if group_by == "assignee": key = tm.get_member_name(task.get("assigned_to"))
            elif group_by == "project": key = tm.get_project_name(task["project_id"])
            elif group_by == "status": key = "Completed" if task.get("completed") else "Pending"
            elif group_by == "priority": 
                if tm.is_overdue(task): key = "Overdue"
                elif task.get("due_date"): key = "Due Soon"
                else: key = "No Deadline"
            else: key = "All Tasks"
            
            if key not in groups: groups[key] = []
            groups[key].append(task)
            
        if not groups:
            grid_content = "<p style='color: var(--text-muted);'>No tasks match the current filter.</p>"
        else:
            if layout == "vertical":
                grid_content = '<div style="display: flex; gap: 30px; flex-wrap: wrap;">'
                for g_name, g_tasks in groups.items():
                    pref = g_name.replace(" ", "-") + "-"
                    grid_content += f'<div style="flex: 1; min-width: 350px;"><h3>{g_name} ({len(g_tasks)})</h3><br><div class="task-grid vertical">'
                    grid_content += "".join(render_single_task(t, pref) for t in g_tasks)
                    grid_content += '</div></div>'
                grid_content += '</div>'
            else:
                for g_name, g_tasks in groups.items():
                    pref = g_name.replace(" ", "-") + "-"
                    grid_content += f'<div style="margin-bottom: 40px;"><h3>{g_name} ({len(g_tasks)})</h3><br><div class="task-grid">'
                    grid_content += "".join(render_single_task(t, pref) for t in g_tasks)
                    grid_content += '</div></div>'
    
    body = f"""
    <div class="header-with-forms">
        <h1>Tasks</h1>
        <div class="header-forms">
            <form method="POST" action="/add_task" class="header-form">
                <input type="text" name="title" placeholder="Task title" required>
                <input type="text" name="description" placeholder="Description">
                <select name="project_id" required><option value="">Project</option>{render_project_options(select_first=True)}</select>
                <select name="assigned_to"><option value="">Assignee</option>{render_member_options(select_first=True)}</select>
                <input type="date" name="due_date" value="{tomorrow}">
                <button type="submit"><i class="fas fa-plus"></i> Add Task</button>
            </form>
            <form method="POST" action="/import_jira" class="header-form">
                <input type="text" name="ticket_id" placeholder="JIRA ID" required>
                <select name="project_id" required><option value="">Project</option>{render_project_options(select_first=True)}</select>
                <button type="submit" class="btn-edit"><i class="fas fa-download"></i> JIRA</button>
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
    
    {grid_content}
    """
    return get_base_html("Tasks", body)

def build_projects():
    data = tm.get_all_data()
    grid_content = ""
    for project in data["projects"]:
        task_count = len([t for t in data["tasks"] if t["project_id"] == project["id"]])
        grid_content += f'''
        <div class="card">
            <h3 style="color: #fff; font-size: 18px; text-transform: none;">{html.escape(project["name"])}</h3>
            <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 15px;">{html.escape(project.get("description", ""))}</p>
            <small style="color: var(--accent); font-weight: 600;">{task_count} associated tasks</small>
        </div>
        '''
    if not grid_content: grid_content = "<p style='color: var(--text-muted);'>No projects defined yet.</p>"
    
    body = f"""
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
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px;">
        {grid_content}
    </div>
    """
    return get_base_html("Projects", body)

def build_members():
    data = tm.get_all_data()
    grid_content = ""
    for member in data["members"]:
        task_count = len([t for t in data["tasks"] if t.get("assigned_to") == member["id"]])
        grid_content += f'''
        <div class="card">
            <h3 style="color: #fff; font-size: 18px; text-transform: none;">{html.escape(member["name"])}</h3>
            <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 15px;">Role: {html.escape(member.get("role", "Member"))}</p>
            <small style="color: var(--accent); font-weight: 600;">{task_count} assigned tasks</small>
        </div>
        '''
    if not grid_content: grid_content = "<p style='color: var(--text-muted);'>No team members yet.</p>"
    
    body = f"""
    <div class="header-with-forms">
        <h1>Team Members</h1>
        <div class="header-forms">
            <form method="POST" action="/add_member" class="header-form">
                <input type="text" name="name" placeholder="Member name" required>
                <select name="role">
                    <option value="Member">Member</option>
                    <option value="Lead">Lead</option>
                    <option value="Manager">Manager</option>
                </select>
                <button type="submit"><i class="fas fa-user-plus"></i> Add Member</button>
            </form>
        </div>
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 20px;">
        {grid_content}
    </div>
    """
    return get_base_html("Team Members", body)

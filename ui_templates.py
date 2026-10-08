import html
import json
import os
from datetime import datetime, timedelta
from urllib.parse import urlencode
from database import tm, STATUSES, STATUS_LABELS
from jira_api import jira

esc = html.escape

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
PRIORITIES = [("high", "High"), ("medium", "Medium"), ("low", "Low")]
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
PRIORITY_COLORS = {"high": "var(--danger)", "medium": "var(--warning)", "low": "var(--success)"}
GROUP_OPTIONS = [("none", "None"), ("assignee", "Assignee"), ("project", "Project"), ("status", "Status"), ("priority", "Priority"), ("due", "Due date")]
BUCKETS = [("all", "All"), ("pending", "Pending"), ("overdue", "Overdue"), ("completed", "Completed")]


def asset_url(name):
    # Cache-bust static assets by mtime so the 1-day browser cache never serves stale JS/CSS
    try:
        version = int(os.path.getmtime(os.path.join(STATIC_DIR, name)))
    except OSError:
        version = 0
    return f"/static/{name}?v={version}"


def fmt_date(value):
    """Format a stored ISO date/datetime as e.g. 'Oct 08'; tolerant of bad data."""
    if not value:
        return ""
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").strftime("%b %d")
    except ValueError:
        return esc(str(value))


def lookups():
    """Id -> name maps, built once per render instead of a linear scan per task."""
    data = tm.get_all_data()
    projects = {p["id"]: p["name"] for p in data["projects"]}
    members = {m["id"]: m["name"] for m in data["members"]}
    return projects, members


def options(pairs, selected=None):
    return "".join(
        f'<option value="{esc(str(value))}" {"selected" if str(value) == str(selected) else ""}>{esc(str(label))}</option>'
        for value, label in pairs
    )


def project_pairs():
    return [(p["id"], p["name"]) for p in tm.get_all_data()["projects"]]


def member_pairs():
    return [(m["id"], m["name"]) for m in tm.get_all_data()["members"]]


def first_id(pairs):
    return pairs[0][0] if pairs else None


def in_bucket(task, bucket):
    if bucket == "completed":
        return bool(task.get("completed"))
    if bucket == "pending":
        # Overdue tasks are still pending work
        return not task.get("completed")
    if bucket == "overdue":
        return tm.is_overdue(task)
    if bucket == "upcoming":
        return bool(task.get("due_date")) and not task.get("completed") and not tm.is_overdue(task)
    return True


def task_sort_key(task):
    return (
        bool(task.get("completed")),
        not tm.is_overdue(task),
        (task.get("due_date") or "9999-12-31")[:10],
        PRIORITY_RANK.get(task.get("priority"), 1),
        task["id"],
    )


def get_base_html(title, body_content):
    nav_links = [("/", "Dashboard", "fa-gauge"), ("/tasks", "Tasks", "fa-list-check"),
                 ("/projects", "Projects", "fa-folder"), ("/members", "Team", "fa-users")]
    nav_html = "".join(
        f'<a href="{href}" class="{"active" if label == title or (label == "Team" and title == "Team Members") else ""}"><i class="fas {icon}"></i> {label}</a>'
        for href, label, icon in nav_links
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{esc(title)} · Task Manager</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link rel="stylesheet" href="{asset_url('style.css')}">
    <script src="{asset_url('app.js')}" defer></script>
</head>
<body>
    <div id="progress" aria-hidden="true"></div>
    <nav class="nav" id="nav">
        <a class="brand" href="/">
            <img src="/static/logo.png" alt="" class="logo-img">
            <span class="brand-name">Task Manager</span>
        </a>
        <div class="nav-links" id="navLinks">{nav_html}</div>
        <div class="nav-right">
            <button type="button" class="icon-btn settings-icon" data-toggle-settings aria-label="JIRA settings"><i class="fas fa-cog"></i></button>
            <button type="button" class="icon-btn nav-toggle" data-toggle-nav aria-label="Menu"><i class="fas fa-bars"></i></button>
            <div class="settings-dropdown" id="settingsDropdown">
                <h4><i class="fas fa-link"></i> JIRA Integration</h4>
                <form method="POST" action="/config_jira" class="stack" data-success="JIRA settings saved">
                    <input type="text" name="server_url" placeholder="JIRA Server URL" value="{esc(jira.server_url)}" required>
                    <input type="text" name="username" placeholder="Username" value="{esc(jira.username)}" required>
                    <input type="password" name="api_token" placeholder="API Token" required>
                    <button type="submit" class="btn-complete"><i class="fas fa-save"></i> Save Config</button>
                </form>
            </div>
        </div>
    </nav>

    <main id="page">
        {body_content}
        {render_quick_add_modal()}
        {render_edit_modal()}
    </main>

    <button type="button" class="fab" data-open-modal="quickAddModal" aria-label="Quick add task">
        <i class="fas fa-plus"></i>
    </button>
    <div id="toasts" aria-live="polite"></div>
</body>
</html>
"""


def render_quick_add_modal():
    projects, members = project_pairs(), member_pairs()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    return f"""
    <div id="quickAddModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="quickAddTitle">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="quickAddTitle">Quick Add Task</h3>
                <button type="button" class="modal-close" data-close-modal aria-label="Close">&times;</button>
            </div>
            <form method="POST" action="/add_task" class="stack" data-success="Task added">
                <input type="text" name="title" placeholder="What needs to be done?" required class="input-lg">
                <textarea name="description" placeholder="Optional details..." rows="3"></textarea>
                <div class="form-row">
                    <label>Project<select name="project_id" required><option value="">Select project</option>{options(projects, first_id(projects))}</select></label>
                    <label>Assignee<select name="assigned_to"><option value="">Unassigned</option>{options(members)}</select></label>
                </div>
                <div class="form-row">
                    <label>Status<select name="status">{options(STATUSES, "todo")}</select></label>
                    <label>Priority<select name="priority">{options(PRIORITIES, "medium")}</select></label>
                    <label>Due<input type="date" name="due_date" value="{tomorrow}"></label>
                </div>
                <button type="submit" class="btn-complete btn-block"><i class="fas fa-bolt"></i> Add Task</button>
            </form>
        </div>
    </div>"""


def render_edit_modal():
    # One shared edit form, filled from the card's data-task by app.js
    # (instead of a hidden form with every project/member option inside every card)
    return f"""
    <div id="editModal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="editTitle">
        <div class="modal-content">
            <div class="modal-header">
                <h3 id="editTitle">Edit Task</h3>
                <button type="button" class="modal-close" data-close-modal aria-label="Close">&times;</button>
            </div>
            <form method="POST" action="/update_task" class="stack" id="editForm" data-success="Task updated">
                <input type="hidden" name="id">
                <input type="text" name="title" placeholder="Title" required class="input-lg">
                <textarea name="description" placeholder="Description" rows="3"></textarea>
                <div class="form-row">
                    <label>Project<select name="project_id" required>{options(project_pairs())}</select></label>
                    <label>Assignee<select name="assigned_to"><option value="">Unassigned</option>{options(member_pairs())}</select></label>
                </div>
                <div class="form-row">
                    <label>Status<select name="status">{options(STATUSES)}</select></label>
                    <label>Priority<select name="priority">{options(PRIORITIES)}</select></label>
                    <label>Due<input type="date" name="due_date"></label>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn-edit" data-close-modal>Cancel</button>
                    <button type="submit" class="btn-complete"><i class="fas fa-save"></i> Save</button>
                </div>
            </form>
        </div>
    </div>"""


def render_add_task_form(button_label):
    projects, members = project_pairs(), member_pairs()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    return f"""
            <form method="POST" action="/add_task" class="header-form hide-mobile" data-success="Task added">
                <input type="text" name="title" placeholder="Task title" required class="grow">
                <input type="text" name="description" placeholder="Description" class="grow">
                <select name="project_id" required aria-label="Project"><option value="">Project</option>{options(projects, first_id(projects))}</select>
                <select name="assigned_to" aria-label="Assignee"><option value="">Unassigned</option>{options(members)}</select>
                <input type="date" name="due_date" value="{tomorrow}" aria-label="Due date">
                <button type="submit"><i class="fas fa-plus"></i> {button_label}</button>
            </form>"""


def status_badge(status):
    return f'<span class="badge status-{status}">{STATUS_LABELS[status]}</span>'


def render_list_item(task, kind, detail, href):
    return f'<a class="list-item {kind}" href="{href}"><strong>{esc(task["title"])}</strong><small>{detail}</small></a>'


def render_single_task(task, projects, members):
    status = tm.get_status(task)
    overdue = tm.is_overdue(task)
    classes = ["task-card", f"status-{status}"]
    if task.get("completed"): classes.append("completed")
    if overdue: classes.append("overdue")

    priority = (task.get("priority") or "medium").lower()
    assigned_name = members.get(task.get("assigned_to"), "Unassigned")
    project_name = projects.get(task.get("project_id"), "Unknown")

    meta = [
        f'<span><i class="fas fa-folder"></i> {esc(project_name)}</span>',
        f'<span><i class="fas fa-user"></i> {esc(assigned_name)}</span>',
        f'<span class="priority" style="color: {PRIORITY_COLORS.get(priority, "var(--text-muted)")}"><i class="fas fa-flag"></i> {priority.upper()}</span>',
    ]
    if task.get("due_date"):
        due = fmt_date(task["due_date"])
        meta.append(f'<span class="overdue-text"><i class="fas fa-triangle-exclamation"></i> Overdue · {due}</span>' if overdue
                    else f'<span><i class="fas fa-calendar"></i> Due {due}</span>')
    if task.get("completed") and task.get("completed_date"):
        meta.append(f'<span><i class="fas fa-check"></i> Done {fmt_date(task["completed_date"])}</span>')
    elif task.get("assigned_date"):
        meta.append(f'<span title="Days since assigned"><i class="fas fa-clock"></i> {tm.get_queue_days(task)}d</span>')

    task_json = json.dumps({
        "id": task["id"], "title": task["title"], "description": task.get("description") or "",
        "project_id": task.get("project_id"), "assigned_to": task.get("assigned_to"),
        "due_date": (task.get("due_date") or "")[:10], "priority": priority, "status": status,
    })
    toggle_action, toggle_btn = ("/uncomplete", '<button type="submit" class="btn-undo btn-sm"><i class="fas fa-undo"></i> Undo</button>') \
        if task.get("completed") else ("/complete", '<button type="submit" class="btn-complete btn-sm"><i class="fas fa-check"></i> Done</button>')
    desc = task.get("description") or ""

    return f'''
    <article class="{" ".join(classes)}" data-task="{esc(task_json)}">
        <div class="task-top">
            <div class="task-title">{esc(task["title"])}</div>
            {status_badge(status)}
        </div>
        {f'<div class="task-desc">{esc(desc)}</div>' if desc else ''}
        <div class="task-meta">{"".join(meta)}</div>
        <div class="task-actions">
            <form method="POST" action="/set_status" class="status-form" data-success="Status updated">
                <input type="hidden" name="id" value="{task["id"]}">
                <select name="status" aria-label="Status" data-autosubmit>{options(STATUSES, status)}</select>
            </form>
            <button type="button" class="btn-edit btn-sm" data-edit><i class="fas fa-pen"></i> Edit</button>
            <form method="POST" action="{toggle_action}" data-success="{'Task reopened' if task.get('completed') else 'Task completed'}">
                <input type="hidden" name="id" value="{task["id"]}">{toggle_btn}
            </form>
            <form method="POST" action="/delete" data-confirm="Delete this task?" data-success="Task deleted">
                <input type="hidden" name="id" value="{task["id"]}">
                <button type="submit" class="btn-delete btn-sm" aria-label="Delete"><i class="fas fa-trash"></i></button>
            </form>
        </div>
    </article>'''


def build_dashboard():
    summary = tm.get_task_summary()
    tasks = tm.get_all_data()["tasks"]
    _, members = lookups()

    pending_tasks = sorted([t for t in tasks if not t.get("completed")], key=task_sort_key)
    overdue_tasks = [t for t in pending_tasks if tm.is_overdue(t)]

    def assignee(t):
        return esc(members.get(t.get("assigned_to"), "Unassigned"))

    def pending_item(t):
        if tm.is_overdue(t):
            return render_list_item(t, "overdue-item", f"Overdue {fmt_date(t['due_date'])} · {assignee(t)}", "/tasks?filter=overdue")
        due = f"Due {fmt_date(t['due_date'])} · " if t.get("due_date") else ""
        return render_list_item(t, "upcoming-item", f"{due}{STATUS_LABELS[tm.get_status(t)]} · {assignee(t)}", "/tasks?filter=pending")

    def column(title, items, total, href, empty):
        more = f'<a class="view-all" href="{href}">View all ({total}) <i class="fas fa-arrow-right"></i></a>' if total > len(items) else ""
        body = "".join(items) or f"<p class='muted'>{empty}</p>"
        return f'<div class="summary-column"><h4>{title}</h4>{body}{more}</div>'

    completed_items = [render_list_item(t, "recent-item", f"Completed {fmt_date(t['completed_date'])}", "/tasks?filter=completed")
                       for t in summary["recent_completed"]]

    status_counts = {key: 0 for key, _ in STATUSES}
    for t in tasks:
        status_counts[tm.get_status(t)] += 1
    status_chips = "".join(
        f'<a class="status-chip status-{key}" href="/tasks?status={key}"><span>{label}</span><strong>{status_counts[key]}</strong></a>'
        for key, label in STATUSES
    )

    body = f"""
    <div class="page-header">
        <h1>Dashboard</h1>
        <div class="header-forms">
            {render_add_task_form("Task")}
            <form method="POST" action="/add_project" class="header-form" data-success="Project added">
                <input type="text" name="name" placeholder="Project name" required class="grow">
                <input type="text" name="description" placeholder="Description" class="grow">
                <button type="submit"><i class="fas fa-plus"></i> Project</button>
            </form>
        </div>
    </div>

    <div class="stats">
        <a href="/tasks" class="card stat">
            <h3>Total</h3><div class="number">{summary['total']}</div>
        </a>
        <a href="/tasks?filter=pending" class="card stat">
            <h3>Pending</h3><div class="number" style="color: var(--warning);">{summary['pending']}</div>
            <small class="muted">incl. {summary['overdue']} overdue</small>
        </a>
        <a href="/tasks?filter=overdue" class="card stat">
            <h3>Overdue</h3><div class="number" style="color: var(--danger);">{summary['overdue']}</div>
        </a>
        <a href="/tasks?filter=completed" class="card stat">
            <h3>Completed</h3><div class="number" style="color: var(--success);">{summary['completed']}</div>
        </a>
    </div>

    <div class="status-strip">{status_chips}</div>

    <div class="summary-section">
        <h3>Activity Summary</h3>
        <div class="summary-grid">
            {column("Pending Tasks", [pending_item(t) for t in pending_tasks[:5]], len(pending_tasks), "/tasks?filter=pending", "No pending tasks")}
            {column("Overdue Tasks", [pending_item(t) for t in overdue_tasks[:5]], len(overdue_tasks), "/tasks?filter=overdue", "No overdue tasks")}
            {column("Recently Completed", completed_items, summary['completed'], "/tasks?filter=completed", "No recent activity")}
        </div>
    </div>
    """
    return get_base_html("Dashboard", body)


def build_tasks(group_by, layout, filter_type, assignee="", status=""):
    projects, members = lookups()
    group_by = group_by if group_by in dict(GROUP_OPTIONS) else "assignee"
    layout = "horizontal" if layout == "horizontal" else "vertical"
    status = status if status in STATUS_LABELS else ""
    state = {"group_by": group_by, "layout": layout, "filter": filter_type, "assignee": assignee, "status": status}

    def url(**overrides):
        params = {k: v for k, v in {**state, **overrides}.items() if v and not (k == "filter" and v == "all")}
        return "/tasks?" + urlencode(params)

    # Assignee/status filters first, so the bucket tabs can show counts for that selection
    tasks = tm.get_all_data()["tasks"]
    if assignee == "unassigned":
        tasks = [t for t in tasks if not t.get("assigned_to")]
    elif assignee:
        tasks = [t for t in tasks if str(t.get("assigned_to")) == assignee]
    if status:
        tasks = [t for t in tasks if tm.get_status(t) == status]
    bucket_counts = {key: sum(1 for t in tasks if in_bucket(t, key)) for key, _ in BUCKETS}
    tasks = sorted((t for t in tasks if in_bucket(t, filter_type)), key=task_sort_key)

    def card(t):
        return render_single_task(t, projects, members)

    empty = "<p class='empty'><i class='fas fa-inbox'></i> No tasks match the current filters.</p>"
    if not tasks:
        grid_content = empty
    elif group_by == "none":
        grid_content = f'<div class="task-grid {"vertical" if layout == "vertical" else ""}">{"".join(map(card, tasks))}</div>'
    else:
        groups = {}
        for task in tasks:
            if group_by == "assignee":
                key = members.get(task.get("assigned_to"), "Unassigned")
            elif group_by == "project":
                key = projects.get(task.get("project_id"), "Unknown")
            elif group_by == "status":
                key = STATUS_LABELS[tm.get_status(task)]
            elif group_by == "priority":
                key = dict(PRIORITIES).get((task.get("priority") or "medium").lower(), "Medium")
            else:
                key = "Overdue" if tm.is_overdue(task) else "Due Soon" if task.get("due_date") else "No Deadline"
            groups.setdefault(key, []).append(task)

        fixed_order = {
            "status": [label for _, label in STATUSES],
            "priority": [label for _, label in PRIORITIES],
            "due": ["Overdue", "Due Soon", "No Deadline"],
        }.get(group_by)
        if fixed_order:
            names = [n for n in fixed_order if n in groups]
        else:
            names = sorted(groups, key=lambda n: (n in ("Unassigned", "Unknown"), n.lower()))

        container = "board" if layout == "vertical" else "stacked"
        grid_class = "task-grid vertical" if layout == "vertical" else "task-grid"
        grid_content = f'<div class="{container}">' + "".join(
            f'''<details class="group" data-group="{esc(group_by + ':' + name)}" open>
                <summary><span>{esc(name)}</span><span class="count">{len(groups[name])}</span></summary>
                <div class="{grid_class}">{"".join(map(card, groups[name]))}</div>
            </details>'''
            for name in names
        ) + '</div>'

    def tab(label, href, active, count=None):
        count_html = f' <span class="count">{count}</span>' if count is not None else ""
        return f'<a href="{href}" data-swap class="{"active" if active else ""}">{label}{count_html}</a>'

    bucket_tabs = "".join(tab(label, url(filter=key), filter_type == key, bucket_counts[key]) for key, label in BUCKETS)
    group_tabs = "".join(tab(label, url(group_by=key), group_by == key) for key, label in GROUP_OPTIONS)
    layout_tabs = tab('<i class="fas fa-table-columns"></i> Columns', url(layout="vertical"), layout == "vertical") + \
                  tab('<i class="fas fa-grip"></i> Grid', url(layout="horizontal"), layout == "horizontal")

    assignee_opts = options([("", "All assignees"), ("unassigned", "Unassigned")] + member_pairs(), assignee)
    status_opts = options([("", "All statuses")] + STATUSES, status)

    active_filters = sum(bool(x) for x in (assignee, status, filter_type not in ("all", "")))
    filter_badge = f'<span class="badge-count">{active_filters}</span>' if active_filters else ""
    clear_link = f'<a href="/tasks?{urlencode({"group_by": group_by, "layout": layout})}" data-swap class="clear-link"><i class="fas fa-xmark"></i> Clear filters</a>' if active_filters else ""

    body = f"""
    <div class="page-header">
        <h1>Tasks</h1>
        <div class="header-forms">
            {render_add_task_form("Add Task")}
            <form method="POST" action="/import_jira" class="header-form" data-success="JIRA ticket imported">
                <input type="text" name="ticket_id" placeholder="JIRA ID" required class="grow">
                <select name="project_id" required aria-label="Project"><option value="">Project</option>{options(project_pairs(), first_id(project_pairs()))}</select>
                <button type="submit" class="btn-edit"><i class="fas fa-download"></i> JIRA</button>
            </form>
        </div>
    </div>

    <div class="toolbar">
        <button type="button" class="filters-toggle btn-edit" data-toggle-filters aria-controls="controls">
            <i class="fas fa-filter"></i> Filters {filter_badge}<i class="fas fa-chevron-down chevron"></i>
        </button>
        <span class="muted result-count">Showing {len(tasks)} task{'s' if len(tasks) != 1 else ''}</span>
        {clear_link}
    </div>

    <div class="controls" id="controls">
        <div class="section">
            <strong>Show</strong>
            <div class="tabs">{bucket_tabs}</div>
        </div>
        <form class="section filter-selects" method="GET" action="/tasks" data-swap>
            <input type="hidden" name="group_by" value="{group_by}">
            <input type="hidden" name="layout" value="{layout}">
            <input type="hidden" name="filter" value="{esc(filter_type)}">
            <label><strong>Assignee</strong><select name="assignee" data-autosubmit>{assignee_opts}</select></label>
            <label><strong>Status</strong><select name="status" data-autosubmit>{status_opts}</select></label>
            <noscript><button type="submit">Apply</button></noscript>
        </form>
        <div class="section">
            <strong>Group by</strong>
            <div class="tabs">{group_tabs}</div>
        </div>
        <div class="section">
            <strong>Layout</strong>
            <div class="tabs">{layout_tabs}</div>
        </div>
    </div>

    {grid_content}
    """
    return get_base_html("Tasks", body)


def build_projects():
    data = tm.get_all_data()
    grid_content = ""
    for project in data["projects"]:
        project_tasks = [t for t in data["tasks"] if t.get("project_id") == project["id"]]
        open_count = sum(1 for t in project_tasks if not t.get("completed"))
        grid_content += f'''
        <a class="card entity-card" href="/tasks?group_by=project">
            <h3 class="entity-name">{esc(project["name"])}</h3>
            <p class="muted">{esc(project.get("description") or "")}</p>
            <small class="accent">{len(project_tasks)} tasks · {open_count} open</small>
        </a>'''
    if not grid_content: grid_content = "<p class='empty'>No projects defined yet.</p>"

    body = f"""
    <div class="page-header">
        <h1>Projects</h1>
        <div class="header-forms">
            <form method="POST" action="/add_project" class="header-form" data-success="Project added">
                <input type="text" name="name" placeholder="Project name" required class="grow">
                <input type="text" name="description" placeholder="Description" class="grow">
                <button type="submit"><i class="fas fa-plus"></i> Add Project</button>
            </form>
        </div>
    </div>
    <div class="entity-grid">{grid_content}</div>
    """
    return get_base_html("Projects", body)


def build_members():
    data = tm.get_all_data()
    grid_content = ""
    for member in data["members"]:
        member_tasks = [t for t in data["tasks"] if t.get("assigned_to") == member["id"]]
        open_count = sum(1 for t in member_tasks if not t.get("completed"))
        overdue_count = sum(1 for t in member_tasks if tm.is_overdue(t))
        overdue_html = f' · <span class="overdue-text">{overdue_count} overdue</span>' if overdue_count else ""
        grid_content += f'''
        <a class="card entity-card" href="/tasks?{urlencode({"assignee": member["id"], "filter": "pending"})}">
            <h3 class="entity-name">{esc(member["name"])}</h3>
            <p class="muted">Role: {esc(member.get("role") or "Member")}</p>
            <small class="accent">{len(member_tasks)} assigned · {open_count} open{overdue_html}</small>
        </a>'''
    if not grid_content: grid_content = "<p class='empty'>No team members yet.</p>"

    body = f"""
    <div class="page-header">
        <h1>Team Members</h1>
        <div class="header-forms">
            <form method="POST" action="/add_member" class="header-form" data-success="Member added">
                <input type="text" name="name" placeholder="Member name" required class="grow">
                <select name="role" aria-label="Role">
                    <option value="Member">Member</option>
                    <option value="Lead">Lead</option>
                    <option value="Manager">Manager</option>
                </select>
                <button type="submit"><i class="fas fa-user-plus"></i> Add Member</button>
            </form>
        </div>
    </div>
    <div class="entity-grid">{grid_content}</div>
    """
    return get_base_html("Team Members", body)

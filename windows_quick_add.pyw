import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

# Ensure the app can find the backend files if run from outside the working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from database import tm
except Exception as e:
    messagebox.showerror("Initialization Error", f"Could not load database backend:\n{e}")
    sys.exit(1)

def quick_add():
    title = title_entry.get().strip()
    if not title:
        messagebox.showwarning("Warning", "Task title is required!")
        return
        
    project_idx = project_combo.current()
    if project_idx < 0:
        messagebox.showwarning("Warning", "Please select an active project!")
        return
        
    member_idx = member_combo.current()
    
    desc = desc_text.get("1.0", tk.END).strip()
    priority = priority_combo.get().lower().replace(" priority", "")
    
    # Extract actual IDs from the cached lists
    project_id = global_projects[project_idx]["id"]
    assigned_to = global_members[member_idx]["id"] if member_idx > 0 else None
    
    try:
        from datetime import datetime, timedelta
        due_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        
        tm.add_task(title, desc, project_id, assigned_to, due_date, priority)
        
        # Flash success and clear fields
        title_entry.delete(0, tk.END)
        desc_text.delete("1.0", tk.END)
        status_label.config(text="✅ Task submitted successfully!")
        root.after(3000, lambda: status_label.config(text=""))
    except Exception as e:
        messagebox.showerror("Database Error", f"Failed to save task:\n{e}")

# Fetch data for dropdowns
try:
    data = tm.get_all_data()
    global_projects = data.get("projects", [])
    global_members = [{"id": None, "name": "Unassigned"}] + data.get("members", [])
except Exception as e:
    messagebox.showerror("Database Error", f"Failed to fetch data from Postgres:\n{e}")
    sys.exit(1)

# Initialize Window
root = tk.Tk()
root.title("Quick Add - TaskManager")
root.geometry("450x420")
root.configure(bg="#0f172a")

# Apply modern dark styling
style = ttk.Style(root)
style.theme_use('clam')
style.configure('TLabel', background="#0f172a", foreground="#f8fafc", font=("Segoe UI", 10))
style.configure('TCombobox', fieldbackground="#1e293b", background="#1e293b", foreground="#fff")
style.configure('TButton', font=("Segoe UI", 10, "bold"), background="#6366f1", foreground="white", borderwidth=0, padding=8)
style.map('TButton', background=[('active', '#4f46e5')])

# Form Padding
frame = tk.Frame(root, bg="#0f172a", padx=20, pady=20)
frame.pack(fill=tk.BOTH, expand=True)

# Title
ttk.Label(frame, text="Task Title").grid(row=0, column=0, sticky="w", pady=(0, 5))
title_entry = tk.Entry(frame, bg="#1e293b", fg="white", insertbackground="white", font=("Segoe UI", 12), borderwidth=1, relief="flat")
title_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 15), ipady=5)

# Description
ttk.Label(frame, text="Description (Optional)").grid(row=2, column=0, sticky="w", pady=(0, 5))
desc_text = tk.Text(frame, height=4, bg="#1e293b", fg="white", insertbackground="white", font=("Segoe UI", 10), borderwidth=1, relief="flat")
desc_text.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 15))

# Project Dropdown
ttk.Label(frame, text="Project").grid(row=4, column=0, sticky="w", pady=(0, 5))
project_combo = ttk.Combobox(frame, values=[p["name"] for p in global_projects], state="readonly")
project_combo.grid(row=5, column=0, sticky="ew", padx=(0, 10), pady=(0, 15))
if global_projects: project_combo.current(0)

# Member Dropdown
ttk.Label(frame, text="Assignee").grid(row=4, column=1, sticky="w", pady=(0, 5))
member_combo = ttk.Combobox(frame, values=[m["name"] for m in global_members], state="readonly")
member_combo.grid(row=5, column=1, sticky="ew", pady=(0, 15))
member_combo.current(0)

# Priority
ttk.Label(frame, text="Priority").grid(row=6, column=0, sticky="w", pady=(0, 5))
priority_combo = ttk.Combobox(frame, values=["Low Priority", "Medium Priority", "High Priority"], state="readonly")
priority_combo.grid(row=7, column=0, sticky="ew", padx=(0, 10), pady=(0, 20))
priority_combo.current(1)

# Submit Button
submit_btn = ttk.Button(frame, text="Add Task Instantly", command=quick_add)
submit_btn.grid(row=8, column=0, columnspan=2, sticky="ew", ipady=2)

# Status Label
status_label = ttk.Label(frame, text="", foreground="#10b981")
status_label.grid(row=9, column=0, columnspan=2, pady=10)

# Force window layout grid weights
frame.columnconfigure(0, weight=1)
frame.columnconfigure(1, weight=1)

root.mainloop()

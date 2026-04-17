import urllib.request
import urllib.error
import base64
import json
from datetime import datetime

class JiraIntegration:
    def __init__(self, server_url="", username="", api_token=""):
        self.server_url = server_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        self.auth = base64.b64encode(f"{username}:{api_token}".encode()).decode() if username and api_token else ""
    
    def get_ticket_details(self, ticket_id):
        if not all([self.server_url, self.username, self.api_token]):
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

jira = JiraIntegration()

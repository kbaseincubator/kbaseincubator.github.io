import os
import requests
import json
import csv
from datetime import datetime

# Set your GitHub personal access token and KBase organization name
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_ORG = "kbase"

# GitHub API URL
GITHUB_API_URL = "https://api.github.com"

# Headers for authentication
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

def get_repos(organization):
    """Fetch all repositories in the given GitHub organization."""
    url = f"{GITHUB_API_URL}/orgs/{organization}/repos"
    repos = []
    page = 1
    while True:
        response = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 100})
        if response.status_code != 200:
            print(f"Error fetching repos: {response.status_code}, {response.text}")
            return repos
        data = response.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos

def get_github_actions(repo_full_name):
    """Fetch the GitHub Actions workflows for a given repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/actions/workflows"
    response = requests.get(url, headers=HEADERS)
    if response.status_code != 200:
        print(f"Error fetching workflows for {repo_full_name}: {response.status_code}, {response.text}")
        return []
    workflows = response.json().get("workflows", [])
    return workflows

def get_workflow_runs(repo_full_name, workflow_id):
    """Fetch the last 5 runs of a given workflow in a repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/actions/workflows/{workflow_id}/runs"
    response = requests.get(url, headers=HEADERS, params={"per_page": 5})
    if response.status_code != 200:
        print(f"Error fetching runs for workflow {workflow_id} in {repo_full_name}: {response.status_code}, {response.text}")
        return []
    runs = response.json().get("workflow_runs", [])
    enriched_runs = []
    for run in runs:
        enriched_runs.append({
            "id": run["id"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "run_started_at": run.get("run_started_at"),
            "updated_at": run.get("updated_at"),
            "actor": run["actor"]["login"] if run.get("actor") else "Unknown",
            "head_commit": {
                "sha": run.get("head_commit", {}).get("id", "Unknown"),
                "message": run.get("head_commit", {}).get("message", "Unknown")
            }
        })
    return enriched_runs

def calculate_workflow_metrics(workflow_runs):
    """Calculate success rate, failure rate, and average duration for a workflow."""
    success_count = sum(1 for run in workflow_runs if run["conclusion"] == "success")
    failure_count = sum(1 for run in workflow_runs if run["conclusion"] == "failure")
    total_runs = len(workflow_runs)
    success_rate = (success_count / total_runs) * 100 if total_runs > 0 else 0
    failure_rate = (failure_count / total_runs) * 100 if total_runs > 0 else 0

    datetime_format = "%Y-%m-%dT%H:%M:%SZ"  # Handle GitHub's ISO format with Z
    durations = [
        (datetime.strptime(run["updated_at"], datetime_format) - datetime.strptime(run["run_started_at"], datetime_format)).total_seconds()
        for run in workflow_runs if run["run_started_at"] and run["updated_at"]
    ]
    avg_duration = sum(durations) / len(durations) if durations else 0
    return {
        "success_rate": success_rate,
        "failure_rate": failure_rate,
        "avg_duration": avg_duration
    }


def export_to_json(data, filename="github_actions.json"):
    """Export data to a JSON file."""
    with open(filename, "w") as json_file:
        json.dump(data, json_file, indent=4)
    print(f"Data exported to {filename}")

def export_to_csv(data, filename="github_actions.csv"):
    """Export data to a CSV file."""
    with open(filename, "w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Repository", "Workflow Name", "Run ID", "Status", "Conclusion", "Actor", "Commit SHA", "Commit Message", "Start Time", "End Time", "Success Rate", "Failure Rate", "Average Duration"])
        for repo, workflows in data.items():
            for workflow in workflows:
                metrics = workflow.get("metrics", {})
                for run in workflow["runs"]:
                    writer.writerow([
                        repo,
                        workflow["name"],
                        run["id"],
                        run["status"],
                        run["conclusion"],
                        run["actor"],
                        run["head_commit"]["sha"],
                        run["head_commit"]["message"],
                        run["run_started_at"],
                        run["updated_at"],
                        metrics.get("success_rate", 0),
                        metrics.get("failure_rate", 0),
                        metrics.get("avg_duration", 0)
                    ])
    print(f"Data exported to {filename}")

def main():
    print(f"Fetching repositories for organization: {GITHUB_ORG}")
    repos = get_repos(GITHUB_ORG)
    if not repos:
        print("No repositories found or unable to fetch them.")
        return

    all_data = {}

    for repo in repos:
        repo_name = repo["name"]
        full_name = repo["full_name"]
        print(f"\nRepository: {repo_name}")
        workflows = get_github_actions(full_name)
        repo_data = []
        if workflows:
            for workflow in workflows:
                workflow_info = {
                    "name": workflow["name"],
                    "id": workflow["id"],
                    "runs": []
                }
                workflow_runs = get_workflow_runs(full_name, workflow["id"])
                workflow_info["runs"] = workflow_runs
                workflow_info["metrics"] = calculate_workflow_metrics(workflow_runs)
                repo_data.append(workflow_info)
        all_data[repo_name] = repo_data

    # Export the data
    export_to_json(all_data)
    export_to_csv(all_data)

if __name__ == "__main__":
    main()

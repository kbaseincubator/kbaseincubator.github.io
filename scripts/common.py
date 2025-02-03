# Set your GitHub personal access token and KBase organization name
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_ORG = "kbase"
GITHUB_API_URL = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}
today = datetime.now().strftime("%Y-%m-%d")

ignored_workflows = ['.github/workflows/pr_build.yml', '.github/workflows/manual-build.yml',
                     '.github/workflows/release-main.yml', '.github/workflows/release.yml',
                     '.github/workflows/build_test_pr.yaml', '.github/workflows/build_prodrc_pr.yaml',
                     '.github/workflows/tag_latest_image.yaml']

DEPENDABOT_ECOSYSTEMS = [
    "composer",
    "go",
    "maven",
    "npm",
    "nuget",
    "pip",
    "rubygems",
    "rust",
    "swift"
]

def timed(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()  # Record start time
        result = func(*args, **kwargs)  # Call the wrapped function
        end_time = time.time()  # Record end time
        elapsed_time = end_time - start_time  # Calculate elapsed time
        logging.info(f"Function '{func.__name__}' took {elapsed_time:.6f} seconds to complete.")
        return result

    return wrapper


def _get_repos():
    """Fetch all repositories in the given GitHub organization."""
    url = f"{GITHUB_API_URL}/orgs/{GITHUB_ORG}/repos"
    repos = []
    page = 1
    while True:
        resp = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 100})
        if resp.status_code != 200:
            print(f"Error fetching repos: {resp.status_code}, {resp.text}")
            sys.exit(1)
            return repos
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos


@timed
def get_all_kbase_repos():
    """ Check if cache exists with today's date, if not, fetch all KBase repos"""

    # Check if cache exists with today's date

    cache_file = f"cache/repos_cache_{today}.json"
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
        logging.info(f"Using cache file: {cache_file}")
        with open(cache_file, "r") as f:
            return json.load(f)
    # Fetch all KBase repos
    logging.info("Fetching all KBase repos since cache file does not exist")
    repos = _get_repos()
    with open(cache_file, "w") as f:
        # Pretty print the JSON so we can read it
        json.dump(repos, f, indent=4)

    return repos


def _get_github_actions(repo_full_name):
    """Fetch the GitHub Actions workflows for a given repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/actions/workflows"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"Error fetching workflows for {repo_full_name}: {resp.status_code}, {resp.text}")
        return []
    return resp.json().get("workflows", [])


@timed
def get_cached_actions_for_all_repos(repos):
    """Fetch the GitHub Actions workflows for a given repository."""
    cache_file = f"cache/actions_cache_{today}.json"
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
        logging.info(f"Using cache file: {cache_file}")
        with open(cache_file, "r") as f:
            return json.load(f)
    else:
        logging.info("Fetching all githb actions workflow runs since cache file does not exist")
        actions = {}
        for repo in repos:
            repo_full_name = repo['full_name']
            actions[repo_full_name] = _get_github_actions(repo_full_name)
        with open(cache_file, "w") as f:
            # Pretty print the JSON so we can read it
            json.dump(actions, f, indent=4)
        return actions


def _get_workflow_runs(repo, workflow_id, branch=None, last_n=5):
    """Fetch the last 'n' runs of a given workflow in a repository, optionally filtering by branch."""
    url = f"{GITHUB_API_URL}/repos/{repo}/actions/workflows/{workflow_id}/runs"
    params = {"per_page": last_n}
    if branch:
        params["branch"] = branch
    resp = requests.get(url, headers=HEADERS, params=params)
    if resp.status_code != 200:
        print(f"Error fetching runs for workflow {workflow_id} in {repo}: {resp.status_code}, {resp.text}")
        return []
    return resp.json().get("workflow_runs", [])



@timed
def get_last_n_workflow_runs(last_n=5):
    """
    Get the last 'n' runs for all workflows containing 'test' in the name,
    filtering by branch for 'main', 'master', and 'develop'.
    """

    actions = get_cached_actions_for_all_repos(get_all_kbase_repos())

    cache_file = f"cache/actions_last_{last_n}_cache_{today}.json"
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 0:
        logging.info(f"Using cache file: {cache_file}")
        with open(cache_file, "r") as f:
            return json.load(f)

    last_n_runs = {}

    for repo, workflows in actions.items():
        for workflow in workflows:
            if workflow['path'] in ignored_workflows or "test" not in workflow['name'].lower():
                continue

            repo_results = {
                "develop": _get_workflow_runs(repo, workflow['id'], branch="develop", last_n=last_n),
                "main": _get_workflow_runs(repo, workflow['id'], branch="main", last_n=last_n),
                "master": _get_workflow_runs(repo, workflow['id'], branch="master", last_n=last_n)
            }
            last_n_runs[repo] = repo_results
        # Add empty results for repos that don't have any workflows
        if repo not in last_n_runs:
            last_n_runs[repo] = {}

    with open(cache_file, "w") as f:
        json.dump(last_n_runs, f, indent=4)

    return last_n_runs





def get_codecov_coverage(owner, repo, branch):
    """
    Retrieve coverage from the new Codecov endpoint for a specific branch:
      https://api.codecov.io/api/v2/github/<owner>/repos/<repo>
    Parameters:
      - owner: The GitHub organization or user owning the repository
      - repo: The repository name
      - branch: (Optional) The branch name to filter coverage
    Returns:
      - Coverage percentage (float) or 0 if no coverage data is found
    """

    codecov_url = f"https://api.codecov.io/api/v2/github/{owner}/repos/{repo}/branches/{branch}"
    try:
        resp = requests.get(codecov_url, headers={"accept": "application/json"})
        if resp.status_code == 200:
            data = resp.json()
            totals = data.get("head_commit").get("totals")
            if not totals:
                logging.info(f"No coverage totals available for {owner}/{repo} on branch {branch}.")
                return 0
            coverage = totals.get("coverage", 0) if isinstance(totals, dict) else 0
            return coverage
        else:
            logging.error(f"Error fetching Codecov coverage for {owner}/{repo} on branch {branch}: {resp.status_code}, {resp.text}")
            return 0
    except Exception as e:
        print(f"Exception calling Codecov: {e}")
        return 0



def get_codecov_coverage_for_all_repos():
    """Get the coverage for all KBase repositories on 'main', 'master', and 'develop' branches."""

    ccf = f"cache/coverage_cache_{today}.json"
    if os.path.exists(ccf) and os.path.getsize(ccf) > 0:
        with open(ccf, "r") as f:
            return json.load(f)

    coverage = defaultdict(lambda: defaultdict(dict))

    for repo in get_all_kbase_repos():
        owner, repo_name = repo["full_name"].split("/")
        for branch in ["main", "master", "develop"]:
            coverage[repo_name][branch]["coverage"] = get_codecov_coverage(owner, repo_name, branch)

    with open(ccf, "w") as f:
        json.dump(coverage, f, indent=4)

    return coverage


def get_dependabot_alerts(repo_full_name):
    """Fetch Dependabot alerts for the given repository."""
    url = f"{GITHUB_API_URL}/repos/{repo_full_name}/dependabot/alerts"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.json()
    print(f"Error fetching Dependabot alerts for {repo_full_name}: {resp.status_code}, {resp.text}")
    return []

@timed
def get_dependabot_alerts_for_all_repos():
    """Fetch Dependabot alerts for all KBase repositories."""

    ccf = f"cache/dependabot_cache_{today}.json"
    if os.path.exists(ccf) and os.path.getsize(ccf) > 0:
        with open(ccf, "r") as f:
            return json.load(f)

    alerts = {}
    for repo in get_all_kbase_repos():
        repo_name = repo["full_name"]
        alerts[repo_name] = get_dependabot_alerts(repo_name)

    with open(ccf, "w") as f:
        json.dump(alerts, f, indent=4)

    return alerts


def get_cve_report_for_repo(repo_full_name):
    pass

def get_cve_report_for_all_repos():
    """Fetch Dependabot alerts for all KBase repositories."""

    ccf = f"cache/cve_cache_{today}.json"
    if os.path.exists(ccf) and os.path.getsize(ccf) > 0:
        with open(ccf, "r") as f:
            return json.load(f)

    cve_report = {}
    for repo in get_all_kbase_repos():
        repo_name = repo["full_name"]
        cve_report[repo_name] = get_cve_report_for_repo(repo_name)

    with open(ccf, "w") as f:
        json.dump(cve_report, f, indent=4)

    return cve_report


def build_report():
    coverage = get_codecov_coverage_for_all_repos()
    last_n_actions = get_last_n_workflow_runs(5)
    dependabot_alerts = get_dependabot_alerts_for_all_repos()
    cve_report = get_cve_report_for_all_repos()


    report_data = []

    for repo in get_all_kbase_repos():
        repo_name = repo["full_name"]
        repo_coverage = coverage.get(repo_name.split("/")[-1], {})
        # repo_alerts = dependabot_alerts.get(repo_name, [])
        # Get counts of alerts filtered DEPENDABOT_ECOSYSTEMS or Other


        # Extract coverage values
        coverage_develop = repo_coverage.get("develop", {}).get("coverage", "N/A")
        coverage_main = repo_coverage.get("main", {}).get("coverage", "N/A")
        coverage_master = repo_coverage.get("master", {}).get("coverage", "N/A")

        # Get workflow runs per branch
        last_actions = last_n_actions.get(repo_name, {})
        filtered_actions = defaultdict(dict)
        for branch, actions_list in last_actions.items():
            for action in actions_list:
                action_name = action['name']
                action_conclusion = action['conclusion']
                # if conclusion is success, set it to 1, else 0
                action_conclusion = 1 if action_conclusion == 'success' else 0

                # print(repo_name, branch, action_name, action_conclusion)
                if not branch in filtered_actions[action_name]:
                    filtered_actions[action_name][branch] = []
                filtered_actions[action_name][branch].append(action_conclusion)

        if filtered_actions:
            for action in filtered_actions:
                report_data.append([
                    repo_name,
                    action,
                    filtered_actions[action].get("develop", "N/A"),
                    filtered_actions[action].get("main", "N/A"),
                    filtered_actions[action].get("master", "N/A"),
                    coverage_develop,
                    coverage_main,
                    coverage_master
                ])
        else:
            # No actions found; add a row with coverage data and a "No Actions" placeholder.
            report_data.append([
                repo_name,
                "No Test Actions Found",
                "N/A",
                "N/A",
                "N/A",
                coverage_develop,
                coverage_main,
                coverage_master
            ])




    # Convert to DataFrame
    columns = ["Repo Name", "Action Name", "Last 5 Develop Pass/Fail", "Last 5 Main Pass/Fail",
               "Last 5 Master Pass/Fail", "Coverage Develop", "Coverage Main", "Coverage Master"]
    df = pd.DataFrame(report_data, columns=columns)

    # Save to CSV
    csv_filename = "github_actions_report.csv"
    df.to_csv(csv_filename, index=False)

    print(f"Report saved to {csv_filename}")

    return csv_filename  # Returning file name in case further processing is needed



build_report()

#     # Get the last N workflow runs
#     last_runs = get_last_n_workflow_runs(5)
#     for repo, runs in last_runs.items():
#         owner, repo_name = repo["full_name"].split("/")

#         for branch, branch_runs in runs.items():
#             if branch_runs:
#                 for run in branch_runs:
#                     workflow_report[repo_name][branch]["runs"] = run["conclusion"]
#             else:
#                 workflow_report[repo_name][branch]["runs"] = "No runs"

#     # Print the report
#     for repo, data in workflow_report.items():
#         print(f"\n{repo}")
#         for branch, branch_data in data.items():
#             coverage = coverage_report[repo].get(branch, {}).get("coverage", "N/A")
#             runs = branch_data["runs"]
#             print(f"  {branch}: Coverage: {coverage}, Runs: {runs}")

# # Call the function to build and print the report
# build_repo_report()

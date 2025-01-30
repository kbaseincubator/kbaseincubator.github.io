# Set your GitHub personal access token and KBase organization name
import dataclasses
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime
import requests
import sys

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
        logging.info("Fetching all KBase repos since cache file does not exist")
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

    codecov_url = f"https://api.codecov.io/api/v2/github/{owner}/repos/{repo}"
    try:
        resp = requests.get(codecov_url, headers={"accept": "application/json"}, params={"branch": branch})
        if resp.status_code == 200:
            data = resp.json()
            totals = data.get("totals")
            if totals is not None:
                coverage = totals.get("coverage", 0)
                return coverage
            else:
                logging.info(f"No coverage totals available for {owner}/{repo} on branch {branch}.")
                return 0
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


get_codecov_coverage_for_all_repos()

# from models import Repo

# def build_repo_report():
#     coverage_report = defaultdict(lambda: defaultdict(dict))
#     workflow_report = defaultdict(lambda: defaultdict(dict))

#     # Get coverage for each branch
#     for repo in get_all_kbase_repos():


#         owner, repo_name = repo["full_name"].split("/")
#         for branch in ["main", "master", "develop"]:
#             coverage = get_codecov_coverage(owner, repo_name, branch)
#             coverage_report[repo_name][branch]["coverage"] = coverage


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

# Set your GitHub personal access token and KBase organization name
import json
import logging
import os
import sys
import time
from collections import defaultdict, Counter
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

repositories = [
    "kbase/auth2",
    "jgi-kbase/AssemblyHomologyService",
    "kbase/execution_engine2",
    "kbase/blobstore",
    "kbase/file_cache_server",
    "kbase/catalog",
    "kbase/collections",
    "kbase/data_import_export",
    "kbase/feeds",
    "kbase/groups",
    "jgi-kbase/IDMappingService",
    "kbase/handle_service2",
    "kbase/narrative_method_store",
    "kbase/relation_engine",
    "kbase/staging_service",
    "kbaseapps/sketch_service",
    "kbase/sample_service",
    "kbase/search_api2",
    "kbase/service_wizard",
    "kbase/user_profile",
    "kbase/workspace_deluxe",
    "kbase/kb_sdk",
    "kbase/narrative",
    "kbase/narrative-traefiker"
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

    last_n_runs = defaultdict(dict)

    for repo, workflows in actions.items():

        for workflow in workflows:

            if workflow['path'] in ignored_workflows or "test" not in workflow['name'].lower():
                continue

            repo_results = {
                "develop": _get_workflow_runs(repo, workflow['id'], branch="develop", last_n=last_n),
                "main": _get_workflow_runs(repo, workflow['id'], branch="main", last_n=last_n),
                "master": _get_workflow_runs(repo, workflow['id'], branch="master", last_n=last_n)
            }
            last_n_runs[repo][workflow['path']] = repo_results
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
def get_dependabot_security_alerts_for_all_repos():
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







def get_test_results(repo_name, default_branch="main"):
    last_n_actions = get_last_n_workflow_runs(1)
    last_actions = last_n_actions.get(repo_name, {})


    tests = {}

    for action_path in last_actions:
        action = last_actions[action_path].get(default_branch, [])
        last_run = action[0] if action else {}
        conclusion = last_run.get("conclusion", "N/A")
        if conclusion == "success":
            tests[action_path] = True
        elif conclusion == "failure":
            tests[action_path] = False
        else:
            tests[action_path] = "N/A"

    if repo_name == "kbase/execution_engine2":
        print(tests)

    for item in tests.values():
        if item is not True:
            return False
    return True


def get_cves(repo_name, dependabot):
    cves = dependabot.get(repo_name, [])
    if not cves:
        return ["N/A" for _ in range(4)]

    c = Counter()
    for item in cves:
        c[item["security_advisory"]["severity"]] += 1

    return [c['low'], c['medium'], c['high'], c['critical']]


def get_open_dependabot_prs(repo_full_name, dependabot=None):
    """Fetch open Dependabot PRs for the given repository."""
    if not dependabot:
        url = f"{GITHUB_API_URL}/repos/{repo_full_name}/pulls"
        params = {"state": "open", "creator": "dependabot[bot]"}
        resp = requests.get(url, headers=HEADERS, params=params)
        if resp.status_code == 200:
            return resp.json()
        print(f"Error fetching Dependabot PRs for {repo_full_name}: {resp.status_code}, {resp.text}")
        return []
    else:
        return dependabot.get(repo_full_name, [])

def get_open_dependabot_prs_for_all_repos():
    """Fetch open Dependabot PRs for all KBase repositories."""
    ccf = f"cache/dependabot_pr_cache_{today}.json"
    if os.path.exists(ccf) and os.path.getsize(ccf) > 0:
        with open(ccf, "r") as f:
            return json.load(f)

    prs = {}
    for repo in get_all_kbase_repos():
        repo_name = repo["full_name"]
        prs[repo_name] = get_open_dependabot_prs(repo_name)

    with open(ccf, "w") as f:
        json.dump(prs, f, indent=4)

    return prs


def report_open_dependabot_prs(repo_name, open_dependabot_prs):
    prs = open_dependabot_prs.get(repo_name, [])
    return len(prs)

def build_report():
    columns = ['repo', 'tests_pass', 'coverage', 'open_dependabot_prs', 'low', 'medium', 'high', 'critical']
    # If there are multiple actions with the word test, and one of them is a "failure" then we will say that tests are failing
    # Coverage and CVEs will be reported for the default branch


    coverage = get_codecov_coverage_for_all_repos()
    dependabot_security_alerts = get_dependabot_security_alerts_for_all_repos()
    open_dependabot_prs = get_open_dependabot_prs_for_all_repos()

    report_data = []
    for repo in get_all_kbase_repos():
        repo_name = repo["full_name"]
        default_branch = repo["default_branch"]
        repo_coverage = coverage.get(repo_name.split("/")[-1], {})
        default_coverage = repo_coverage.get(default_branch, {}).get("coverage", "N/A")
        cves = get_cves(repo_name, dependabot_security_alerts)
        test_workflow_results = get_test_results(repo_name=repo_name, default_branch=default_branch)
        pr_count = report_open_dependabot_prs(repo_name, open_dependabot_prs=open_dependabot_prs)
        report_data.append([repo_name, test_workflow_results, default_coverage, pr_count,  *cves])


    df = pd.DataFrame(report_data, columns=columns)
    # Save to CSV
    csv_filename = "github_actions_report.csv"
    df.to_csv(csv_filename, index=False)
    print(f"Report saved to {csv_filename}")

    # Now print  a version of the df to a file with a subset of the data using the list of repos
    csv_filename = "github_actions_report_subset.csv"
    df[df['repo'].isin(repositories)].to_csv(csv_filename, index=False)
    print(f"Subset report saved to {csv_filename}")



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

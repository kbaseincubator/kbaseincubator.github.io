# KBase Repo Stats

# Test Coverage

## [actions_cache.json](scripts/actions_cache_2025-02-03.json) 
* contains all GitHub Actions workflows for a given repository. 
* You can use this to filter out the workflows you want to analyze.
* Not all repos have github actions set up

## [actions_last_5_cache.json](scripts/actions_last_5_cache_2025-02-03.json) 
* contains the last 5 runs of each `test` workflow in the repository.
* The action must contain the word `test` in its name in order to make it into this file
* We save the last N runs for `main|master|develop` branches

## [coverage_cache.json](scripts/coverage_cache_2025-02-03.json) 
  * contains the coverage data from codecov.io for a given repository.
  * contains coverage for `main|master|develop` branches

## [dependabot_cache.json](scripts/dependabot_cache_2025-02-03.json) contains the dependabot alerts for a given repository.
* Contains information about the type of the alert
* Also Contains "security advisories" which contain the CVEs `cve_id` and `severity`
* As of Feb 2025, the list ecosystems found in kbase repos are: 
```python
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
```

## [repos_cache.json](scripts/repos_cache_2025-02-03.json) 
* contains the list of repositories in the KBase organization.
* This is the list of repositories that we are analyzing

# Scope

* The script can both scrape the data, and partially generate a csv at the moment. 
* The script caches the data for the day, so the first run of the day takes a few minutes, but subsequent runs utilize the cache
* Output format TBD, but the goal of the output is to be served by the API or from static files and then displayed somewhere in a dashboard format
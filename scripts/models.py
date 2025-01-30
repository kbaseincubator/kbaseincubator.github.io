from pydantic import BaseModel

class Repo(BaseModel):
    name: str
    code_coverage: float
    status: str
    github_actions_status: dict[str, str]  # Maps branch names to their GitHub Actions status
    branch_coverage: dict[str, float]     # Maps branch names to their code coverage percentage
    # Add other fields as necessary, such as last_updated, contributors, etc.

    class Config:
        arbitrary_types_allowed = True
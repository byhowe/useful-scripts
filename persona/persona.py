from dataclasses import dataclass, field
from typing import Any
import requests
import subprocess
import tempfile

user = input("Username > ")
repos_url = f"https://api.github.com/users/{user}/repos"
branches_url = f"https://api.github.com/repos/{user}/{{name}}/branches"


@dataclass
class github_repo:
    name: str
    clone_url: str
    archived: bool
    ssh_url: str
    mailmap: list[str] = field(default_factory=list)
    replace: bool = True
    _branches: list[str] | None = None

    @classmethod
    def parse_from_api(cls, repo: dict[str, Any]) -> "github_repo":
        c = cls(
            name=repo["name"],
            clone_url=repo["clone_url"],
            ssh_url=repo["ssh_url"],
            archived=repo["archived"],
        )

        return c

    @property
    def branches(self) -> list[str]:
        # Note that the below if statement would return True if
        # `self._branches` is an empty list, which would mean there is an error
        # since there has to be at least one branch.
        if not self._branches:
            r = requests.get(branches_url.format(repo=self.name))
            self._branches = list(b["name"] for b in r.json())
        return self._branches


r = requests.get(repos_url)
repos = r.json()
repos = list(github_repo.parse_from_api(repo) for repo in repos)
repos = list(repo for repo in repos if not repo.archived)

print("Stage 1: Cloning")
for repo in repos:
    print(f"cloning {user}/{repo.name}...")
    try:
        subprocess.run(
            ["git", "clone", repo.clone_url],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        print(f"Already cloned {user}/{repo.name}")
        continue

print("Stage 2: Extracting mailmap")
for repo in repos:
    p = subprocess.run(
        "git log | grep 'Author:'",
        capture_output=True,
        check=True,
        cwd=repo.name,
        shell=True,
    )
    author_lines = p.stdout.decode().splitlines()
    mailmap = map(lambda m: m[8:], author_lines)
    repo.mailmap.extend(list(set(mailmap)))

print("Stage 3: Mailmap")
mailmap = []
for repo in repos:
    mailmap.extend(repo.mailmap)
mailmap = list(set(mailmap))
mailmap_path = tempfile.mktemp()
with open(mailmap_path, "wt") as f:
    f.write("\n".join(mailmap))
subprocess.call(["vim", mailmap_path])

print("Stage 4: Applying mailmap")
for repo in repos:
    print(f"Applying for {user}/{repo.name}")
    subprocess.run(
        ["git", "filter-repo", "--force", "--mailmap", mailmap_path],
        capture_output=True,
        check=True,
        cwd=repo.name,
    )

print("Stage 5: Replace text")
find = input("what to search for > ")
print(f"Searching for {find.__repr__()} in the repos...")
finds = []
for repo in repos:
    p = subprocess.run(["git", "rev-list", "--all"], capture_output=True, cwd=repo.name)
    revs = p.stdout.decode().splitlines()
    try:
        p = subprocess.run(
            ["git", "grep", "-i", find, *revs],
            capture_output=True,
            check=True,
            cwd=repo.name,
        )
    except subprocess.CalledProcessError:
        print(f"No need to replace {user}/{repo.name}")
        repo.replace = False
    lines = p.stdout.decode().splitlines()
    finds.extend(map(lambda l: l[41:], lines))
finds = list(set(finds))
textreplace_path = tempfile.mktemp()
with open(textreplace_path, "wt") as f:
    f.write("\n".join(finds))
subprocess.call(["vim", textreplace_path])

print("Stage 6: Applying replace text")
for repo in (repo for repo in repos if repo.replace):
    print(f"Applying for {user}/{repo.name}")
    subprocess.run(
        ["git", "filter-repo", "--force", "--replace-text", textreplace_path],
        capture_output=True,
        check=True,
        cwd=repo.name,
    )

print("Stage 7: Push")
for repo in repos:
    subprocess.run(
        ["git", "remote", "remove", "origin"],
        capture_output=True,
        cwd=repo.name,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", repo.ssh_url],
        capture_output=True,
        check=True,
        cwd=repo.name,
    )
    for b in repo.branches:
        subprocess.call(["git", "push", "--force", "-u", "origin", b], cwd=repo.name)

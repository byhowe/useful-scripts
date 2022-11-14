from dataclasses import dataclass, field
from typing import Any
import requests
import subprocess

user = input("Username > ")


@dataclass
class github_repo:
    name: str
    clone_url: str
    archived: bool
    ssh_url: str
    mailmap: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    replace: bool = True

    @classmethod
    def parse_from_api(cls, repo: dict[str, Any]) -> "github_repo":
        c = cls(
            name=repo["name"],
            clone_url=repo["clone_url"],
            ssh_url=repo["ssh_url"],
            archived=repo["archived"],
        )

        r = requests.get(f"https://api.github.com/repos/{user}/{c.name}/branches")
        branches_json = r.json()
        branches = map(lambda b: b["name"], branches_json)
        c.branches.extend(branches)

        return c


r = requests.get(f"https://api.github.com/users/{user}/repos")
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
with open("mailmap", "wt") as f:
    f.write("\n".join(mailmap))
subprocess.call(["vim", "mailmap"])

print("Stage 4: Applying mailmap")
for repo in repos:
    print(f"Applying for {user}/{repo.name}")
    subprocess.run(
        ["git", "filter-repo", "--force", "--mailmap", "../mailmap"],
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
with open("textreplace", "wt") as f:
    f.write("\n".join(finds))
subprocess.call(["vim", "textreplace"])

print("Stage 6: Applying replace text")
for repo in (repo for repo in repos if repo.replace):
    print(f"Applying for {user}/{repo.name}")
    subprocess.run(
        ["git", "filter-repo", "--force", "--replace-text", "../textreplace"],
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

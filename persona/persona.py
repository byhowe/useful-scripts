from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import os.path
import requests
import shutil
import subprocess
import sys
import tempfile

user = input("Username > ")
repos_url = f"https://api.github.com/users/{user}/repos"
branches_url = f"https://api.github.com/repos/{user}/{{name}}/branches"


class clone_status(Enum):
    already_cloned = 1
    unknown_error = 2
    successful = 3

    def is_ok(self):
        return self == clone_status.successful


@dataclass
class github_repo:
    name: str
    clone_url: str
    archived: bool
    ssh_url: str
    mailmap: list[str] = field(default_factory=list)
    replace: bool = True
    _branches: list[str] | None = None
    _where: str | None = None

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
    def full_name(self) -> str:
        return f"{user}/{self.name}"

    @property
    def branches(self) -> list[str]:
        # Note that the below if statement would return True if
        # `self._branches` is an empty list, which would mean there is an error
        # since there has to be at least one branch.
        if not self._branches:
            r = requests.get(branches_url.format(name=self.name))
            self._branches = list(b["name"] for b in r.json())
        return self._branches

    @property
    def origin_url(self) -> str | None:
        try:
            p = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                cwd=self.name,
            )
            return p.stdout[:-1].decode()
        except subprocess.CalledProcessError:
            return None

    def _set_origin_to_null(self):
        subprocess.run(
            ["git", "remote", "remove", "origin"],
            capture_output=True,
            cwd=self.name,
        )

    def _set_origin(self, origin: str):
        subprocess.run(
            ["git", "remote", "add", "origin", origin],
            capture_output=True,
            cwd=self.name,
            check=True,
        )

    @origin_url.setter
    def origin_url(self, origin: str | None):
        match (origin is None, self.origin_url is None):
            case (True, False):
                self._set_origin_to_null()
            case (False, True):
                self._set_origin(origin)
            case (False, False):
                self._set_origin_to_null()
                self._set_origin(origin)

    def push(self, branch: str):
        subprocess.call(
            ["git", "push", "--force", "-u", "origin", branch], cwd=repo.name
        )

    @property
    def where(self) -> str:
        return self._where if self._where is not None else self.name

    def clone(self, where: str | None = None) -> clone_status:
        self._where = where
        if os.path.isdir(self.where):
            return clone_status.already_cloned
        try:
            subprocess.run(
                ["git", "clone", repo.clone_url, self.where],
                check=True,
                capture_output=True,
            )
            return clone_status.successful
        except subprocess.CalledProcessError:
            return clone_status.unknown_error

    @property
    def rev_list(self) -> list[str]:
        # Careful. Make sure this does not raise exception, which would
        # propogate and be caught in the caller.
        p = subprocess.run(
            ["git", "rev-list", "--all"], capture_output=True, cwd=repo.name
        )
        return p.stdout.decode().splitlines()


r = requests.get(repos_url)
repos = r.json()
repos = (github_repo.parse_from_api(repo) for repo in repos)
repos = (repo for repo in repos if not repo.archived)
repos = list(repos)

print(f"Found {len(repos)} repositories in total")
print(" ".join(repo.name for repo in repos))

discard = input("Any you would like to filter out? (seperate with spaces) ")
discard = discard.split()
discard = list(e.strip() for e in discard)
repos = list(repo for repo in repos if repo.name not in discard)

for i, repo in enumerate(repos, start=1):
    match repo.clone():
        case clone_status.successful:
            print(f"[{i}/{len(repos)}] {repo.full_name} cloned successfully")
        case clone_status.already_cloned:
            print(f"[{i}/{len(repos)}] {repo.full_name} is already cloned")
        case clone_status.unknown_error:
            print(
                f"[{i}/{len(repos)}] {repo.full_name} could not be cloned!",
                file=sys.stderr,
            )


def mailmap():
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

    mailmap = []
    for repo in repos:
        mailmap.extend(repo.mailmap)
    mailmap = list(set(mailmap))
    mailmap_path = tempfile.mktemp()
    with open(mailmap_path, "wt") as f:
        f.write("\n".join(mailmap))
    subprocess.call(["vim", mailmap_path])

    for repo in repos:
        print(f"Applying for {repo.full_name}")
        subprocess.run(
            ["git", "filter-repo", "--force", "--mailmap", mailmap_path],
            capture_output=True,
            check=True,
            cwd=repo.name,
        )


def textreplace():
    find = input("what to search for > ")
    print(f"Searching for {find.__repr__()} in the repos...")
    finds = []
    for i, repo in enumerate(repos, start=1):
        try:
            p = subprocess.run(
                ["git", "grep", "-i", find, *repo.rev_list],
                capture_output=True,
                check=True,
                cwd=repo.name,
            )
            lines = p.stdout.decode().splitlines()
            finds.extend(map(lambda l: l[41:], lines))
            print(f"[{i}/{len(repos)}] Matched string in {repo.full_name}")
        except subprocess.CalledProcessError:
            print(
                f"[{i}/{len(repos)}] Failed to match string in {repo.full_name}, skipping"
            )
            repo.replace = False
    finds = list(set(finds))
    textreplace_path = tempfile.mktemp()
    with open(textreplace_path, "wt") as f:
        f.write("\n".join(finds))
    subprocess.call(["vim", textreplace_path])

    for repo in (repo for repo in repos if repo.replace):
        print(f"Applying for {repo.full_name}")
        subprocess.run(
            ["git", "filter-repo", "--force", "--replace-text", textreplace_path],
            capture_output=True,
            check=True,
            cwd=repo.name,
        )


def push():
    for repo in repos:
        repo.origin_url = repo.ssh_url
        for b in repo.branches:
            repo.push(branch=b)


def cleanup():
    print(f"Removing {len(repos)} repositories...")
    for repo in repos:
        shutil.rmtree(repo.where)


def personahelp():
    print(
        "help | ?    : prints help menu\n"
        "mailmap     : runs mailmap\n"
        "textreplace : runs textreplace\n"
        "push        : runs push\n"
        "cleanup     : runes cleanup\n",
        end="",
    )


while True:
    cmd = input("(persona) ")
    match cmd:
        case "help" | "?":
            personahelp()
        case "mailmap":
            mailmap()
        case "textreplace":
            textreplace()
        case "push":
            push()
        case "cleanup":
            cleanup()

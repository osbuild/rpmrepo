#!/usr/bin/python3

"""Required modules"""
import json
import os
import re
import argparse


def main(suffix, repo_folder):
    """
    This script is used to update Schutzfile in a speciffic repository. It
    takes --suffix which specifies which date you want to update the
    snapshots to and --repo which specifies the repository folder containing
    Schutzfile.
    """
    repo_files = os.listdir("repo/")
    singletons = []
    # Get a list of all repositories that contain 'singleton'
    for repo_file in repo_files:
        with open(os.path.join("repo", repo_file), "r") as file:
            data = json.load(file)
        if "singleton" in data.keys():
            singletons.append(data["snapshot-id"])

    with open(os.path.join(repo_folder, "Schutzfile"), "r") as file:
        data = json.load(file)

    # Replace snapshot SUFFIX in repositories that don't have 'singleton' present
    for key in data.keys():
        if "repos" in data[key].keys():
            for repo in data[key]["repos"]:
                for arch_repos in repo:
                    for i, _ in enumerate(repo[arch_repos]):
                        if arch_repos == "file" or any(
                            singleton in repo[arch_repos][i]["baseurl"]
                            for singleton in singletons
                        ):
                            continue
                        repo[arch_repos][i]["baseurl"] = re.sub(
                            "[0-9]{8}",
                            suffix,
                            repo[arch_repos][i]["baseurl"],
                        )

    with open(os.path.join(repo_folder, "Schutzfile"), "w") as file:
        json.dump(data, file, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Updates Schutzfile repositories.")
    parser.add_argument(
        "--suffix",
        metavar="SUFFIX",
        type=str,
        help="date of the rpmrepo snapshots",
        required=True,
    )
    parser.add_argument(
        "--repo",
        metavar="REPO",
        type=str,
        help="repository directory containing Schutzfile",
        required=True,
    )
    args = parser.parse_args()
    main(args.suffix, args.repo)

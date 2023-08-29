#!/usr/bin/python3

"""Required modules"""
import json
import os
import re
import argparse


def main(suffix, repo_folder, dry_run):
    """
    This script is used to update Schutzfile in a speciffic repository. It
    takes --suffix which specifies which date you want to update the
    snapshots to and --repo which specifies the repository folder containing
    Schutzfile.
    """
    repo_files = os.listdir("repo/")
    singletons = []
    snapshots = []
    # Get a list of all repositories that contain 'singleton'
    for repo_file in repo_files:
        with open(os.path.join("repo", repo_file), "r") as file:
            data = json.load(file)
        snapshots.append(data["snapshot-id"])
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
                        # Terribly inefficient way to check to see if the url has been removed
                        if not any(snapshot in repo[arch_repos][i]["baseurl"]
                                   for snapshot in snapshots):
                            print(f"WARN: {repo[arch_repos][i]['baseurl']} has no current snapshot. Skipping it.")
                            continue
                        repo[arch_repos][i]["baseurl"] = re.sub(
                            "[0-9]{8}",
                            suffix,
                            repo[arch_repos][i]["baseurl"],
                        )

    if not dry_run:
        with open(os.path.join(repo_folder, "Schutzfile"), "w") as file:
            json.dump(data, file, indent=2)
    else:
        print(json.dumps(data, indent=2))

    # update repository snapshots in test/data/repositories/
    # currently exists only for osbuild-composer
    test_data_repositories_dir = os.path.join(repo_folder, "test/data/repositories/")
    if os.path.exists(test_data_repositories_dir):
        repo_json_files = os.listdir(test_data_repositories_dir)
        for repo_file in repo_json_files:
            with open(os.path.join(test_data_repositories_dir, repo_file), "r") as file:
                data = json.load(file)

            for arch in data.keys():
                for repo in data[arch]:
                    baseurl = repo["baseurl"]

                    if any(singleton in baseurl for singleton in singletons):
                        continue
                    # Terribly inefficient way to check to see if the url has been removed
                    if not any(snapshot in baseurl for snapshot in snapshots):
                        print(f"WARN: {baseurl} has no current snapshot. Skipping it.")
                        continue

                    repo["baseurl"] = re.sub(
                        "[0-9]{8}",
                        suffix,
                        baseurl,
                    )

            if not dry_run:
                with open(os.path.join(test_data_repositories_dir, repo_file), "w") as file:
                    json.dump(data, file, indent=2)
            else:
                print(json.dumps(data, indent=2))


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the new Schutzfile instead of overwriting the old one.")
    args = parser.parse_args()
    main(args.suffix, args.repo, args.dry_run)

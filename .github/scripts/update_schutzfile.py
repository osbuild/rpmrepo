#!/usr/bin/python3

"""Required modules"""
import argparse
import json
import os
import re
import urllib

import requests


def basename(url):
    """Get basename from the path of a url"""
    return os.path.basename(urllib.parse.urlparse(url.strip("/")).path)


def is_snapshot(url):
    """Check if a url is formatted as a snapshot"""
    return re.match(".*-[0-9]{8}$", basename(url)) is not None


def is_singleton(url, singletons):
    """Check if a url is a singleton"""
    return any(singleton in url for singleton in singletons)


# pylint: disable=too-many-branches
def write_schutzfile(repo_folder, dry_run, suffix, singletons, live_snapshots):
    """
    Update Schutzfile, which has the following structure:
    {
      "distro": {
        "repos": [
          {
            "file": "...",
            "arch": [
              {
                "baseurl": "..."
              }
            ]
          }
        ]
      }
    }
    """
    with open(os.path.join(repo_folder, "Schutzfile"), "r", encoding="utf-8") as file:
        schutzfile_data = json.load(file)
    print(f"Updating schutzfile {os.path.join(repo_folder, 'Schutzfile')}")
    for distro in schutzfile_data.keys():
        if "repos" not in schutzfile_data[distro].keys():
            continue

        for repos in schutzfile_data[distro]["repos"]:
            for key, arch_repos in repos.items():
                if key == "file":
                    continue

                # Always update all repositories belonging to a distro:arch together,
                # this avoids mixing snapshots for the same distro:arch, for instance
                # using baseos from March and appstream from April.
                snapshot_in_arch_missing = False
                for repo in arch_repos:
                    baseurl = repo["baseurl"]
                    if not is_snapshot(baseurl) or is_singleton(baseurl, singletons):
                        continue
                    new_baseurl = re.sub("[0-9]{8}", suffix, baseurl)
                    if basename(new_baseurl) not in live_snapshots:
                        print(
                            f"WARN: {repo['baseurl']} not updated due to expected snapshot being "
                            "missing, did the snapshot job fail?"
                        )
                        snapshot_in_arch_missing = True
                if snapshot_in_arch_missing:
                    print(
                        f"WARN: distro {key} arch {arch_repos} not updated as one of the snapshots "
                        "is missing"
                    )
                    continue

                for repo in arch_repos:
                    baseurl = repo["baseurl"]
                    if not is_snapshot(baseurl) or is_singleton(baseurl, singletons):
                        continue
                    repo["baseurl"] = re.sub("[0-9]{8}", suffix, baseurl)

    if not dry_run:
        with open(os.path.join(repo_folder, "Schutzfile"), "w", encoding="utf-8") as file:
            json.dump(schutzfile_data, file, indent=2)
    else:
        print(json.dumps(schutzfile_data, indent=2))


def write_test_repositories(repo_folder, dry_run, suffix, singletons, live_snapshots):
    """
    Update test repositories, which have the following structure:
    distro.json:
    {
      "arch": [
        {
          "baseurl": "..."
        }
      ]
    }
    """
    test_data_repositories_dir = os.path.join(repo_folder, "test/data/repositories/")
    print(f"Updating {test_data_repositories_dir}")
    if os.path.exists(test_data_repositories_dir):
        repo_json_files = os.listdir(test_data_repositories_dir)
        for repo_file in repo_json_files:
            if not repo_file.endswith(".json"):
                print(f"{repo_file} not a JSON file: skipping")
                continue
            with open(os.path.join(test_data_repositories_dir, repo_file), "r", encoding="utf-8") as file:
                data = json.load(file)

            for arch in data.keys():
                # Always update all repositories belonging to a distro:arch together,
                # this avoids mixing snapshots for the same distro:arch, for instance
                # using baseos from March and appstream from April.
                snapshot_in_arch_missing = False
                for repo in data[arch]:
                    baseurl = repo["baseurl"]
                    if not is_snapshot(baseurl) or is_singleton(baseurl, singletons):
                        continue
                    new_baseurl = re.sub("[0-9]{8}", suffix, baseurl)
                    if basename(new_baseurl) not in live_snapshots:
                        print(
                            f"WARN: {repo['baseurl']} not updated due to expected snapshot being "
                            "missing, did the snapshot job fail?"
                        )
                        snapshot_in_arch_missing = True
                if snapshot_in_arch_missing:
                    print(
                        f"WARN: distro {repo_file} arch {arch} not updated as one of the snapshots "
                        "is missing"
                    )
                    continue

                for repo in data[arch]:
                    baseurl = repo["baseurl"]
                    if not is_snapshot(baseurl) or is_singleton(baseurl, singletons):
                        continue
                    repo["baseurl"] = re.sub("[0-9]{8}", suffix, baseurl)

            if not dry_run:
                with open(
                    os.path.join(test_data_repositories_dir, repo_file), "w", encoding="utf-8"
                ) as file:
                    json.dump(data, file, indent=2)
            else:
                print(json.dumps(data, indent=2))


def main(suffix, repo_folder, dry_run):
    """
    This script is used to update Schutzfile in a speciffic repository. It
    takes --suffix which specifies which date you want to update the
    snapshots to and --repo which specifies the repository folder containing
    Schutzfile.
    """
    repo_files = os.listdir("repo/")
    singletons = []
    live_snapshots = []

    # Get a list of all repositories that contain 'singleton'
    for repo_file in repo_files:
        with open(os.path.join("repo", repo_file), "r", encoding="utf-8") as file:
            data = json.load(file)
        if "singleton" in data.keys():
            singletons.append(data["snapshot-id"])

    # Get a list of the current snapshot in rpmrepo to validate any
    # proposed update against
    enumerate_response = requests.get("https://rpmrepo.osbuild.org/v2/enumerate", timeout=120)
    if enumerate_response.status_code != 200:
        raise RuntimeError("Unable to get live snapshots current enumerate cache")
    live_snapshots = json.loads(enumerate_response.text)
    write_schutzfile(repo_folder, dry_run, suffix, singletons, live_snapshots)
    write_test_repositories(repo_folder, dry_run, suffix, singletons, live_snapshots)


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
        help="Print the new Schutzfile instead of overwriting the old one.",
    )
    args = parser.parse_args()
    main(args.suffix, args.repo, args.dry_run)

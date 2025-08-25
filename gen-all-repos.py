#!/usr/bin/python3
# pylint: disable=invalid-name
"""
Generate all repo snapshot configuration files based on the definitions list
"""

import argparse
import json
import logging
import subprocess
import sys

import yaml


logger = logging.getLogger(__name__)


def get_parser():
    """
    Create argument parser
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--definitions',
        default='repo-definitions.yaml',
        help='Path to the definitions list (JSON or YAML)'
    )
    parser.add_argument(
        '--output-dir',
        default='./repo',
        help='Path to the output directory'
    )
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        default=False,
        help='Enable debug logging'
    )
    return parser

# pylint: disable=too-many-locals,too-many-branches
def main():
    """
    Main function
    """
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if args.debug:
        logger.setLevel(logging.DEBUG)

    logger.info('Reading definitions from %s', args.definitions)
    with open(args.definitions, encoding='utf-8') as file:
        if args.definitions.endswith('.json'):
            definitions = json.load(file)
        if args.definitions.endswith('.yaml'):
            definitions = yaml.safe_load(file)
        else:
            raise ValueError('Unknown file type: %s' % args.definitions)

    for distro, repos in definitions.items():
        for repo in repos:
            cmd = [sys.executable, 'gen-repos.py', '--target-dir', args.output_dir]

            # COMMON OPTIONS
            arch = repo.get('arch', [])
            for a in arch:
                cmd.extend(['--arch', a])

            repo_name = repo.get('repo_name', [])
            for n in repo_name:
                cmd.extend(['--repo-name', n])

            base_url = repo.get('base_url')
            if base_url:
                cmd.extend(['--base-url', base_url])

            base_url_template = repo.get('base_url_template')
            if base_url_template:
                cmd.extend(['--base-url-template', base_url_template])

            snapshot_id_suffix = repo.get('snapshot_id_suffix')
            if snapshot_id_suffix:
                cmd.extend(['--snapshot-id-suffix', snapshot_id_suffix])

            storage = repo.get('storage')
            if storage:
                cmd.extend(['--storage', storage])

            singleton = repo.get('singleton')
            if singleton:
                cmd.extend(['--singleton', singleton])

            # END OF COMMON OPTIONS

            cmd.append(distro)

            # DISTRO SPECIFIC OPTIONS
            if distro != 'eln':
                release = repo['release']
                cmd.extend(['--release', release])

            if distro == 'rhel':
                released = repo.get('released', False)
                if released:
                    cmd.append('--released')
                eus = repo.get('eus', False)
                if eus:
                    cmd.append('--eus')

            elif distro == 'fedora':
                stream = repo.get('stream')
                if stream:
                    cmd.extend(['--stream', stream])

            logger.debug('Running %s', ' '.join(cmd))
            subprocess.check_call(cmd, stdout=sys.stdout)


if __name__ == '__main__':
    main()

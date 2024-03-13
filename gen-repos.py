#!/usr/bin/python3
# pylint: disable=invalid-name
"""
gen-repos.py - Generate JSON repository files from a template
"""

import abc
import argparse
import json
import logging
import os


logger = logging.getLogger(__name__)


class BaseRepoConfigGenerator(abc.ABC):
    """
    Base class for generating repository files
    """

    DEFAULT_STORAGE = 'public'

    # pylint: disable=too-many-arguments
    def __init__(self, release, arch, repo_name=None, singleton=None, storage=None, base_url=None,
                 snapshot_id_suffix=None):
        """
        :param release: The release to generate the repository file for (e.g. 8.3)
        :param arch: The architecture to generate the repository file for (e.g. x86_64)
        :param repo_name: The repository name to generate the repository file for (e.g. BaseOS)
        :param singleton: Singleton string to use if the snapshot is a singleton (defaults to None)
        :param storage: The storage to use (defaults to self.DEFAULT_STORAGE)
        :param base_url: The base URL to use (if not provided, it will be generated based on the generator class rules)
        :param snapshot_id_suffix: The snapshot ID suffix to use (if not provided, it will be generated based on the
                                   generator class rules)
        """
        self.release = release
        self.arch = arch
        self.repo_name = repo_name
        self.singleton = singleton
        self.storage = storage
        self.base_url = base_url
        self.snapshot_id_suffix = snapshot_id_suffix

    @staticmethod
    @abc.abstractmethod
    def default_arches(release):
        """
        Return a list of default architectures
        """

    @staticmethod
    @abc.abstractmethod
    def default_repo_names(arch, release):
        """
        Return a list of default repository names for the given arch and release
        """

    @abc.abstractmethod
    def get_base_url(self):
        """
        Return the base URL to use
        """

    @abc.abstractmethod
    def get_platform_id(self):
        """
        Return the platform ID to use
        """

    @abc.abstractmethod
    def get_snapshot_id(self):
        """
        Return the snapshot ID to use
        """

    def generate(self, target_dir):
        """
        Generate the repository file
        """
        repo_config = {
            'base-url': self.get_base_url(),
            'platform-id': self.get_platform_id(),
            'snapshot-id': self.get_snapshot_id(),
            'storage': self.storage or self.DEFAULT_STORAGE,
        }
        if self.singleton is not None:
            repo_config['singleton'] = self.singleton

        filename = f"{self.get_snapshot_id()}.json"
        path = os.path.join(target_dir, filename)
        with open(path , 'w', encoding='utf-8') as file:
            logger.info('Writing %s', path)
            json.dump(repo_config, file, indent=8, sort_keys=True)
            # it is a basic file's right to end with a newline
            file.write('\n')


class RHELRepoConfigGenerator(BaseRepoConfigGenerator):
    """
    Generate RHEL repository files
    """

    # RHEL repo snapshots are stored in the rhvpn storage by default
    DEFAULT_STORAGE = 'rhvpn'
    BASE_URL_TEMPLATE = "http://download.eng.bos.redhat.com/rhel-{release_major}/{stream}/RHEL-{release_major}/" + \
                        "latest-RHEL-{release_major}.{release_minor}/compose/{repo_name}/{arch}/os/"

    # pylint: disable=too-many-arguments
    def __init__(self, release, arch, repo_name=None, singleton=None, storage=None, base_url=None,
                 snapshot_id_suffix=None, released=False):
        super().__init__(release, arch, repo_name, singleton, storage, base_url, snapshot_id_suffix)
        self.released = released

    @staticmethod
    def default_arches(release):
        return ['x86_64', 'aarch64', 'ppc64le', 's390x']

    @staticmethod
    def default_repo_names(arch, release):
        if arch == 'x86_64':
            return ['BaseOS', 'AppStream', 'CRB', 'HighAvailability', 'RT', 'SAP', 'SAPHANA']
        if arch == 'aarch64':
            return ['BaseOS', 'AppStream', 'CRB']
        return ['BaseOS', 'AppStream']

    def get_base_url(self):
        if self.base_url is not None:
            return self.base_url

        release_major, release_minor = self.release.split('.')
        stream = 'rel-eng' if self.released else 'nightly'
        return self.BASE_URL_TEMPLATE.format(
            release_major=release_major,
            release_minor=release_minor,
            stream=stream,
            repo_name=self.repo_name,
            arch=self.arch,
        )

    def get_platform_id(self):
        release_major, _ = self.release.split('.')
        return f'el{release_major}'

    def get_snapshot_id(self):
        snapshot_id_suffix = self.snapshot_id_suffix
        if snapshot_id_suffix is None:
            release_major, release_minor = self.release.split('.')

            # abbreviations used for some repo names
            repo_name_mapping = {
                'HighAvailability': 'ha',
            }
            repo_name_specifier = repo_name_mapping.get(self.repo_name, self.repo_name.lower())
            stream_specifier = 'r' if self.released else 'n'
            snapshot_id_suffix = f'{repo_name_specifier}-{stream_specifier}{release_major}.{release_minor}'

        return f'{self.get_platform_id()}-{self.arch}-{snapshot_id_suffix}'


class CSRepoConfigGenerator(BaseRepoConfigGenerator):
    """
    Generate CentOS Stream repository files
    """

    CS8_BASE_URL_TEMPLATE = "http://msync.centos.org/centos/{release_major}-stream/{repo_name}/{arch}/os/"
    CS9_BASE_URL_TEMPLATE = "https://composes.stream.centos.org/production/latest-CentOS-Stream/compose/" + \
                            "{repo_name}/{arch}/os/"
    CS10_BASE_URL_TEMPLATE = "https://composes.stream.centos.org/stream-10/production/latest-CentOS-Stream/compose/" + \
                            "{repo_name}/{arch}/os/"

    @staticmethod
    def default_arches(release):
        if release == '8':
            return ['x86_64', 'aarch64', 'ppc64le']
        if release == '9' or release == '10':
            return ['x86_64', 'aarch64', 'ppc64le', 's390x']
        raise ValueError(f'No default arches defined for CentOS Stream release: {release}')

    @staticmethod
    def default_repo_names(arch, release):
        if release == '8':
            return ['BaseOS', 'AppStream', 'PowerTools']
        if release == '9' or release == '10':
            if arch == 'x86_64':
                return ['BaseOS', 'AppStream', 'CRB', 'RT']
            return ['BaseOS', 'AppStream', 'CRB']
        raise ValueError(f'No default repo names defined for CentOS Stream release: {release}')

    def get_base_url(self):
        if self.base_url is not None:
            return self.base_url

        if self.release == '8':
            template = self.CS8_BASE_URL_TEMPLATE
        elif self.release == '9':
            template = self.CS9_BASE_URL_TEMPLATE
        elif self.release == '10':
            template = self.CS10_BASE_URL_TEMPLATE
        else:
            raise NotImplementedError(f'No BaseURL template defined for CentOS Stream {self.release}')

        return template.format(
            release_major=self.release,
            repo_name=self.repo_name,
            arch=self.arch,
        )

    def get_platform_id(self):
        return f'el{self.release}'

    def get_snapshot_id(self):
        snapshot_id_suffix = self.snapshot_id_suffix
        if snapshot_id_suffix is None:
            snapshot_id_suffix = self.repo_name.lower()

        return f'cs{self.release}-{self.arch}-{snapshot_id_suffix}'


class FedoraRepoConfigGenerator(BaseRepoConfigGenerator):
    """
    Generate Fedora repository files
    """

    FEDORA_BASE_URL_TEMPLATE = "https://dl01.fedoraproject.org/pub/fedora/linux/{stream}/{stream_release}/" + \
                               "{repo_name}/{arch}/os/"
    FEDORA_SECONDARY_BASE_URL_TEMPLATE = "https://dl.fedoraproject.org/pub/fedora-secondary/{stream}/" + \
                                         "{stream_release}/{repo_name}/{arch}/os/"
    RELEASE_STREAM = ['releases', 'updates', 'development', 'rawhide']

    # pylint: disable=too-many-arguments
    def __init__(self, release, arch, repo_name=None, singleton=None, storage=None, base_url=None,
                 snapshot_id_suffix=None, stream='releases'):
        super().__init__(release, arch, repo_name, singleton, storage, base_url, snapshot_id_suffix)
        self.stream = stream
        if self.stream not in self.RELEASE_STREAM:
            raise ValueError(f'Invalid release status: {self.stream}')

    @staticmethod
    def default_arches(release):
        return ['x86_64', 'aarch64', 'ppc64le', 's390x']

    @staticmethod
    def default_repo_names(arch, release):
        return ['Everything']

    def get_base_url(self):
        if self.base_url is not None:
            return self.base_url

        if self.stream == 'rawhide':
            stream = 'development'
            stream_release = self.stream
        else:
            stream = self.stream
            stream_release = self.release

        template = self.FEDORA_BASE_URL_TEMPLATE
        if self.arch in ['ppc64le', 's390x']:
            template = self.FEDORA_SECONDARY_BASE_URL_TEMPLATE

        url = template.format(
            stream=stream,
            stream_release=stream_release,
            repo_name=self.repo_name,
            arch=self.arch,
        )

        # updates repos do not end with "os/"
        if self.stream == 'updates':
            url = url.removesuffix('os/')

        return url

    def get_platform_id(self):
        return f'f{self.release}'

    def get_snapshot_id(self):
        snapshot_id_suffix = self.snapshot_id_suffix
        if snapshot_id_suffix is None:
            if self.stream == 'rawhide':
                snapshot_id_suffix = 'rawhide'
            elif self.stream == 'development':
                snapshot_id_suffix = 'branched'
            elif self.stream == 'releases':
                snapshot_id_suffix = 'fedora'
            elif self.stream == 'updates':
                snapshot_id_suffix = 'updates-released'

            if self.repo_name != 'Everything':
                snapshot_id_suffix += f'-{self.repo_name.lower()}'

        return f'f{self.release}-{self.arch}-{snapshot_id_suffix}'


class ELNRepoConfigGenerator(BaseRepoConfigGenerator):
    """
    Generate Fedora ELN repository files
    """

    FEDORA_BASE_URL_TEMPLATE = "https://odcs.fedoraproject.org/composes/production/latest-Fedora-ELN/compose/" + \
                               "{repo_name}/{arch}/os/"

    # pylint: disable=too-many-arguments
    def __init__(self, arch, repo_name):
        super().__init__(None, arch, repo_name=repo_name)

    @staticmethod
    def default_arches(release):
        return ['x86_64', 'aarch64', 'ppc64le', 's390x']

    @staticmethod
    def default_repo_names(arch, release):
        return ['BaseOS', 'AppStream', 'CRB']

    def get_base_url(self):
        return self.FEDORA_BASE_URL_TEMPLATE.format(repo_name=self.repo_name,arch=self.arch)

    def get_platform_id(self):
        return 'eln'

    def get_snapshot_id(self):
        return f'eln-{self.arch}-{self.repo_name.lower()}'


def get_parser():
    """
    Create argument parser
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--target-dir',
        default='./repo',
        metavar='DIR',
        help='Target directory for generated JSON files'
    )
    parser.add_argument(
        '--arch',
        choices=['x86_64', 'aarch64', 'ppc64le', 's390x'],
        action='append',
        default=[],
        help='Architecture'
    )
    parser.add_argument(
        '--repo-name',
        action='append',
        default=[],
        metavar='NAME',
        help='Repository name'
    )
    parser.add_argument(
        '--base-url',
        action='store',
        default=None,
        metavar='URL',
        help='Literal URL to use for the repository base URL'
    )
    parser.add_argument(
        '--snapshot-id-suffix',
        action='store',
        default=None,
        metavar='SUFFIX',
        help='Literal suffix to use for the snapshot ID'
    )
    parser.add_argument(
        '--storage',
        choices=['public', 'rhvpn'],
        default=None,
        help='Storage type'
    )
    parser.add_argument(
        '--singleton',
        action='store',
        default=None,
        metavar='DATE',
        help='Singleton date'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        default=False,
        help='Enable debug logging'
    )

    subparsers = parser.add_subparsers(dest='distro', required=True)

    rhel_parser = subparsers.add_parser('rhel', help='Generate RHEL repository files')
    rhel_parser.set_defaults(generator=RHELRepoConfigGenerator)
    rhel_parser.add_argument(
        '--release',
        required=True,
        help='Release version ("X.Y")'
    )
    rhel_parser.add_argument(
        '--released',
        action='store_true',
        default=False,
        help='Released or not'
    )

    cs_parser = subparsers.add_parser('cs', help='Generate CentOS Stream repository files')
    cs_parser.set_defaults(generator=CSRepoConfigGenerator)
    cs_parser.add_argument(
        '--release',
        required=True,
        help='Release version ("X")'
    )

    fedora_parser = subparsers.add_parser('fedora', help='Generate Fedora repository files')
    fedora_parser.set_defaults(generator=FedoraRepoConfigGenerator)
    fedora_parser.add_argument(
        '--release',
        required=True,
        help='Release version ("X")'
    )
    fedora_parser.add_argument(
        '--stream',
        choices=['releases', 'updates', 'development', 'rawhide'],
        default='releases',
        help='Stream of the release'
    )

    eln_parser = subparsers.add_parser('eln', help='Generate Fedora ELN repository files')
    eln_parser.set_defaults(generator=ELNRepoConfigGenerator)


    return parser

# pylint: disable=too-many-branches
def main():
    """
    Main function
    """
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # check arguments
    # If at least one of base_url or snapshot_id_suffix is not provided, repo_name must be provided.
    # The reason is that repo_name is used to generate the base_url and snapshot_id from template.
    if ((args.base_url is None and args.snapshot_id_suffix is not None) or
        (args.base_url is not None and args.snapshot_id_suffix is None)) and not args.repo_name:
        parser.error('--repo-name must be provided if at least one of --base-url or --snapshot-id-suffix is provided,' +
                     ' but not both')
    # If both base_url and snapshot_id_suffix are provided, repo_name has no effect.
    if (args.base_url is not None and args.snapshot_id_suffix is not None) and args.repo_name:
        parser.error('Providing --repo-name when both --base-url and --snapshot-id-suffix are provided has no effect')
    # Using default architectures does not make sense when base_url is provided, because the URL would be the same
    # for all architectures.
    if args.base_url is not None and not args.arch:
        parser.error('--arch must be provided when --base-url is provided')
    # Fedora and CentOS Stream use only major version number in release
    if args.distro in ['cs', 'fedora'] and '.' in args.release:
        parser.error(f'{args.distro} uses only major version number in release.')

    logger.debug(args)

    release = None
    if "release" in args:
        release = args.release

    arches = args.arch
    # if arch is not specified, generate the default arches
    if not arches:
        arches = args.generator.default_arches(release)
        logger.info('Generating for all default arches: %s', arches)

    repo_names = args.repo_name
    # if repo_names is specified, generate the specified repo_names for each arch
    if repo_names:
        arch_repo_names_map = {arch: repo_names for arch in arches}
    # if repo_names is not specified, generate the default repo_names for each arch
    if not repo_names:
        # if base_url is specified, do not generate the default repo_names
        if args.base_url is not None:
            arch_repo_names_map = {arch: [None] for arch in arches}
        else:
            arch_repo_names_map = {
                arch: args.generator.default_repo_names(arch, release) for arch in arches
            }
        logger.info('Generating for all default repo_names: %s', arch_repo_names_map)

    for arch, repo_names in arch_repo_names_map.items():
        for repo_name in repo_names:
            if args.distro == 'rhel':
                generator = args.generator(args.release, arch, repo_name, args.singleton, args.storage, args.base_url,
                                           args.snapshot_id_suffix, args.released)
            elif args.distro == 'fedora':
                generator = args.generator(args.release, arch, repo_name, args.singleton, args.storage, args.base_url,
                                           args.snapshot_id_suffix, args.stream)
            elif args.distro == 'eln':
                generator = args.generator(arch, repo_name)
            else:
                generator = args.generator(args.release, arch, repo_name, args.singleton, args.storage, args.base_url,
                                           args.snapshot_id_suffix)
            generator.generate(args.target_dir)


if __name__ == '__main__':
    main()

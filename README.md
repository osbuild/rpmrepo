RPMrepo Snapshots
=================

RPM Repository Snapshot Management

The RPMrepo project creates persistent and immutable snapshots of RPM
repositories. It provides tools and infrastructure to create such snapshots, as
well as host and serve them.

### Project

 * **Website**: <https://www.osbuild.org>
 * **Bug Tracker**: <https://github.com/osbuild/rpmrepo/issues>

### Requirements

The requirements for this project are:

 * `python >= 3.8`

### About

RPMrepo is comprised of a set of different utilities and infrastructure. The
main goal is to regularly create immutable snapshots of a set of public and
RedHat-private RPM repositories and provide them for a fixed amount of time
on our own infrastructure.

Our infrastructure is maintained via the OSBuild Terraform configuration. See
the
[image-builder-terraform](https://github.com/osbuild/image-builder-terraform)
repository, in particular the
[rpmrepo.tf](https://github.com/osbuild/image-builder-terraform/blob/main/rpmrepo.tf)
configuration.

For user documentation on RPMrepo, see: <https://osbuild.org/rpmrepo/>

The backend implementation of RPMrepo involves the following steps:

  * Target Repository Configuration

    When running snapshot operations, we need to know the list of target RPM
    repositories to snapshot, what to call the snapshots, and where to store
    the data. This information is currently stored as JSON files in this
    repository (see the `./repo/` subdirectory).

    For each target repository, we store a JSON dictionary with the following
    information:

      * "base-url": The RPM repository base-url to create the snapshot of. An
                    RPM repository base-url requires the root-level metadata
                    file to be accessible as `repodata/repomd.xml`. See the
                    DNF / RPM documentation for more information, if desired.

      * "platform-id": The DNF Platform ID to use. This allows to group
                       multiple snapshots together and share the backend
                       storage. We use this to deduplicate RPMs in our backend.
                       This ID can be freely chosen, but all snapshots that
                       share an ID can only be deleted together. We usually
                       pick the actual DNF Platform ID (see the DNF
                       `module_platform_id` for details) here, but this is
                       not required.

      * "singleton": We usually create snapshots regularly. In case a target
                     repository is already immutable by design, this key can
                     be set to make sure only a single snapshot of this
                     repository is ever taken. Simply set this key to the
                     snapshot suffix to use for the singleton snapshot, and
                     all snapshot operations will use this suffix (and thus
                     skipping the operation if it already exists).

      * "snapshot-id": The name of the snapshot to store it as. Usually this
                       is the same as the name of this file without extension.
                       This name can be freely chosen. We usually name
                       snapshots as:

                           <platform-id>-<arch>-<repo>[-<repo-version>].

                       Note that the actual snapshots will get a suffix like
                       `-<date>` appended automatically. This field must not
                       include this suffix in the snapshot ID.

      * "storage": The ID of the storage location to use. We have different
                   storage locations for different access rights. For now, this
                   is just a string that specifies the directory in our backend
                   storage. See the backend information for possible values.

  * Snapshot Creation

    To create snapshots, we use the `reposync` dnf module. See `dnf reposync`
    for more information. This tool just downloads an entire RPM repository
    to local storage. We then index this data for our backend storage and
    upload it.

    The `./src/ctl/` directory implements the command-line control client
    that we use for this. It is a python module that just wraps `dnf reposync`
    to download a repository, provides indexing helpers, and then wraps the
    AWS `boto3` API to upload everything to our storage.

    Note that a single snapshot might store up to 100GiB of data intermittently
    and can take up to 8h. Therefore, none of the default script execution
    engines can be used, since they either have limited disk-space or limited
    execution time.

    We provide a container (see the `osbuild/containers` repository) called
    `rpmrepo-snapshot` which reads the configuration in `./repo/` and uses the
    python module in `./src/ctl/` to create a snapshot. The container supports
    batched execution, thus can be used to create many snapshots in parallel.

  * Storage

    We currently store all snapshots in a dedicated AWS S3 bucket called
    `rpmrepo-storage`. Since we store a lot of data, we employ a data
    deduplication strategy. All actual data files are stored with their sha256
    checksum as name in `data/<storage>/<platform-id>/sha256-<checksum>`. This
    means matching files will be deduplicated if they are stored in the same
    storage-directory with the same platform-id.

    Since we dropped file-names and paths, we cannot serve an RPM repository
    from this checksum-based storage. Therefore, we create shim wrapping layers
    that refer to this storage. In `data/ref/<platform-id>/<snapshot-id>/...`
    we store the entire RPM repository, but with empty files. We then attach
    AWS S3 metadata to all these empty files and fill in the checksum of their
    content. This way, all objects underneath the `data/ref/...` directory is
    empty, and thus free of charge.

    Our frontend thus only needs to redirect requests from `data/ref/` to
    the correct underlying file, by reading the checksum metadata.

  * Gateway

    The frontend to the RPM repository snapshots is a simple HTTP REST API. It
    uses AWS API Gateway to create a simple catch-all REST API that forwards
    all HTTP requests to an AWS Lambda script. This script is sourced from
    `./src/gateway/` in this repository.

    This scripts provides a multitude of legacy interfaces for all kinds of
    operations. See its implementation for details. Its main job is to read
    requests to a snapshot, find the file in `data/ref/...`, read the checksum
    from the metadata of this empty file, and then return a 301 HTTP redirect
    to the right file in `data/<storage>/<platform-id>/sha256-<checksum>`. It
    is then the client's job to follow this redirect and directly download the
    file.

    Note that we simply redirect clients to the public HTTP interface to AWS
    S3. The gateway never transmits any data of the repositories. This keeps
    our charges low and makes sure large files are always directly transferred
    between AWS S3 and the client.

    Several paths in the `rpmrepo-storage` S3 bucket are publicly accessible.
    In particular, `data/public/`, `data/ref/`, and `data/thread/`. The
    `data/rhvpn/` path is *NOT* publicly accessible. Instead, we have an AWS
    VPC Endpoint that opens up this path to all clients from within the RH
    VPN. Hence, data stored in this directory is only accessible from within
    RH.
    Note that `data/ref/` is public, and as such all snapshots can be listed
    and enumerated publicly. Only the file content is possibly protected from
    public access. This is intentional, but can be changed in the future if
    it poses a problem.

    Apart from redirects, the gateway also provides utility functions to
    enumerate all snapshots, or redirect to old legacy storage locations of
    older RPMrepo revisions.

  * Snapshot Routine

    As a single snapshot operation requires a lot of storage and time, we use
    custom infrastructure to run this. This used to be Beaker, but for better
    reliability, we now schedule the snapshot jobs on AWS Batch. The
    previously mentioned `rpmrepo-snapshot` container is scheduled on AWS Batch
    and then will create the requested snapshots.

    The snapshot routine can be scheduled as a single job, or as an array job.
    If scheduled as single job, you must specify the name of the target
    configuration in `./repo/` to run. If scheduled as an array job, you should
    size the array as big as the number of files in `./repo/` (bigger is fine,
    those excess jobs will be no-ops; smaller is less fine, as it will miss
    snapshots). The array jobs will then each pick one file in `./repo/` based
    on their ARRAY-JOB-ID.

    Furthermore, the snapshot routine requires you to specify the branch and
    commit of the `rpmrepo` repository to use. You can use `main`+`HEAD`, but
    this will be subject to concurrent changes in the upstream repository. You
    are strongly advised to use `main`+`<commit-sha>` instead.

    Lastly, you can specify the suffix to be used for the snapshots. If you
    specify `auto`, it will use the current date and time (except for singleton
    snapshots; see above). You should specify this suffix manually to make
    sure all snapshots share a suffix. Otherwise, updating users will be a
    hassle.

    The AWS Batch interface will allow you to track all the snapshot jobs, see
    which failed, and allow you to reschedule individual jobs, if desired.

  * Updating snapshot configurations

    The `./repo/` directory contains all the configuration files for the
    snapshots. Each file is a JSON file that specifies the configuration for
    one snapshot.

    Individual snapshot configurations can be generated using the helper script
    `./gen-repos.py`. Multiple snapshot configurations can be generated by
    defining them in `./repo-definitions.yaml` and then running
    `./gen-all-repos.py`, which internally calls `./gen-repos.py`.

    Updating the snapshot configurations usually consists of deleting unused
    configurations, and adding new ones. The most convenient way to do this is
    to update the `./repo-definitions.yaml` file, and then run the
    `snapshot-configs` Makefile target. This will automatically delete all
    configurations that are no longer present in the definition file, and
    generate new ones.

### List Available Snapshots

If you just need a list of the available snapshots you can query the API like
this:

    `curl https://rpmrepo.osbuild.org/v2/enumerate | jq .`

Which will return a JSON list of the snapshots names.

### Repository:

 - **web**:   <https://github.com/osbuild/rpmrepo>
 - **https**: `https://github.com/osbuild/rpmrepo.git`
 - **ssh**:   `git@github.com:osbuild/rpmrepo.git`

### License:

 - **Apache-2.0**
 - See LICENSE file for details.

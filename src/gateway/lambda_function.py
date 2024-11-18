"""RPMrepo - Gateway Entrypoint

This module provides the entrypoint of the AWS Gateway to RPMrepo. It is an AWS
lambda function hooked into AWS API-Gateway as a proxy resource. The
`lambda_handler()` function is the AWS entrypoint called for every HTTP request
on the configured domain. It serves as catch-all entrypoint and gets the HTTP
request path as argument.
"""

# pylint: disable=duplicate-code
# pylint: disable=fixme
# pylint: disable=invalid-name
# pylint: disable=line-too-long
# pylint: disable=no-else-return
# pylint: disable=too-few-public-methods
# pylint: disable=too-many-branches
# pylint: disable=too-many-return-statements
# pylint: disable=too-many-statements

import json
import urllib.parse

import botocore
import boto3

_robots_txt = """User-agent: *
Disallow: /
"""

_storage_urls = {
    "anon": "https://rpmci.s3.us-east-2.amazonaws.com/data/anon",
    "psi": "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/rpmci/data/anon",
    "psi-legacy": "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/manifestdb/rpmrepo",
    "public": "https://rpmrepo-storage.s3.amazonaws.com/data/public",
    "rhvpn": "https://rpmrepo-storage.bucket.vpce-08d3201af28373567-o10c2v4q.s3.us-east-1.vpce.amazonaws.com/data/rhvpn",
}

_documentation_url = "https://osbuild.org/docs/developer-guide/projects/rpmrepo/"


def _error(code=500):
    """Synthesize API Error Reply"""

    return { "statusCode": code }


def _redirect(location):
    """Synthesize API Redirect Reply"""

    return {
        "statusCode": 301,
        "headers": {
            "Location": location,
        },
    }


def _success(body=None):
    """Synthesize API Success Reply"""

    return {
        "statusCode": 200,
        "body": body or "",
    }


def _parse_proxy(stage, proxy):
    """Parse proxy argument"""

    # Split the proxy argument by slashes and decode each element. You are
    # allowed to encode further slashes or other special characters in each
    # element. The command handlers explicitly support that. However, we do
    # not allow empty elements, as all current commands require non-empty
    # arguments (this also means you cannot have trailing slashes for now,
    # but API-Gateway drops those silently, anyway).

    if proxy is None:
        return None

    elements = proxy.split("/")
    if len(elements) < 1:
        return None

    for k, v in enumerate(elements):
        elements[k] = urllib.parse.unquote(v)
        if len(elements[k]) < 1:
            return None

    # Depending on which stage we are deployed to, different commands are
    # supported. In particular, a handful of legacy stages provide backwards
    # compatibility to previous APIs. We implement the ones that are still in
    # use. Note that there are gating-tests in old RHEL versions that might
    # use those APIs for quite some time.

    if stage == "control":
        command = elements[0]
        if command == "snapshots":
            return { "enumerate": {} }
        else:
            return None
    elif stage == "psi":
        # Old PSI storage which simply redirects based on metadata or package
        # selector. Uses the old `manifestdb` Swift-Storage on PSI OpenStack.
        # This is no longer updated, but still used.

        host = _storage_urls["psi-legacy"] + "/"
        location = []

        if elements[2] == "Packages":
            location += ["rpm", elements[0]]
        elif elements[2] == "repodata":
            location += ["repo", elements[1]]
        else:
            return None

        location += elements[2:]

        return {
            "redirect": {
                "location": host + urllib.parse.quote("/".join(location)),
            },
        }

    elif stage == "s3":
        # These APIs are no longer in use, so we do not implement them.

        return None

    elif stage == "v1":
        # The first version of the query API. This one is basically a hardcoded
        # `mirror` command of the later versions.

        if len(elements) < 4:
            return None

        return {
            "mirror": {
                "path": "/".join(elements[3:]),
                "platform": elements[1],
                "snapshot": elements[2],
                "storage": elements[0],
            },
        }

    else:
        command = elements[0]
        if command == "enumerate":
            if len(elements) < 2:
                return { command: {} }
            elif len(elements) == 2:
                return { command: { "thread": elements[1] } }
            else:
                return None
        elif command == "mirror":
            if len(elements) < 5:
                return None

            return {
                command: {
                    "path": "/".join(elements[4:]),
                    "platform": elements[2],
                    "snapshot": elements[3],
                    "storage": elements[1],
                },
            }
        else:
            return None


def _parse_storage(storage):
    """Parse the storage identifier"""

    if storage == "anon":
        return _storage_urls["anon"]
    elif storage == "psi":
        return _storage_urls["psi"]
    elif storage == "public":
        return _storage_urls["public"]
    elif storage == "rhvpn":
        return _storage_urls["rhvpn"]
    else:
        return None


def _query_s3(storage, snapshot, path):
    """Query S3 for checksum metadata"""

    # Expliticly create an anonymous client. We do not want to leak resources,
    # none are needed for this query.
    s3c = boto3.client(
        "s3",
        config=botocore.client.Config(
            signature_version=botocore.UNSIGNED
        ),
    )

    # Legacy storage uses the old `rpmci` logic. Keep this as long as we have
    # snapshots in those storage locations.
    if storage in ("anon", "psi"):
        try:
            head = s3c.head_object(
                Bucket="rpmci",
                Key=f"data/ref/snapshot/{snapshot}/{path}",
            )
        except botocore.exceptions.ClientError:
            return None

        return head.get("Metadata", {}).get("rpmci-checksum")
    else:
        try:
            head = s3c.head_object(
                Bucket="rpmrepo-storage",
                Key=f"data/ref/{snapshot}/{path}",
            )
        except botocore.exceptions.ClientError:
            return None

        return head.get("Metadata", {}).get("rpmrepo-checksum")


def _run_enumerate(arguments):
    """Handle the `enumerate/*` command

    The `enumerate` command is used to list thread indices. Since data stores
    on S3 are not atomic, we store an index when a full snapshot is synced.
    Those indices can be enumerate to get a list of snapshots.
    """

    # Expliticly create an anonymous client. We do not want to leak resources,
    # none are needed for this query.
    s3c = boto3.client(
        "s3",
        config=botocore.client.Config(
            signature_version=botocore.UNSIGNED
        ),
    )

    # Serve the data from the enumerate cache if present
    try:
        obj = s3c.get_object(Bucket="rpmrepo-storage", Key="data/thread/meta/cache.json")
        return _success(obj['Body'].read())
    except botocore.exceptions.ClientError as e:
        if not e.response['Error']['Code'] == "NoSuchKey":
            return _error(500)

    prefix = "data/thread/"
    if "thread" in arguments:
        prefix = prefix + arguments["thread"] + "/"

    results = []
    paginator = s3c.get_paginator("list_objects_v2")
    pages = paginator.paginate(
        Bucket="rpmrepo-storage",
        Prefix=prefix,
        # S3 limits this to 1000 currently, but maybe not forever. Lets try to
        # fetch more to avoid repeated requests, which significantly slow down
        # the operation.
        PaginationConfig={'PageSize': 16384},
    )

    for page in pages:
        for entry in page.get("Contents", []):
            # get everything past the last slash
            key = entry.get("Key").rsplit("/", 1)[1]
            if len(key) > 0:
                results.append(key)

    results.sort()

    return _success(json.dumps(results))


def _run_mirror(arguments):
    """Handle the `mirror/*` command

    The `mirror/*` command allows accessing the data stored in our S3 bucket
    via HTTP. We do not place any kinds of restrictions on what data we mirror.
    However, we always apply a deduplication technique: The stored file-system
    tree is just a bunch of empty files in
    `data/ref/<platform>/<snapshot>/<path>`, but each file has an
    `rpmrepo-checksum` metadata property attached. The actual file-content is
    stored with its checksum as file-name in
    `data/<storage>/<platform>/<checksum>`. Files with identical checksums will
    thus share storage.

    The `mirror/*` command looks for the requested file in `data/ref/*`, reads
    the metadata property and returns a redirect to the requested file.

    Note that the "symlink-farm" is public. It contains empty files which have
    the checksum of their underlying file as metadata. Hence, they do not
    expose the actual file-content but only the checksum. Thus, this
    information does not need to be protected. Moreover, this entire handler
    performs an action with exclusively public information. It is merely a
    public gateway to our snapshots. However, the redirects it returns can
    point to protected data and thus you cannot follow the redirects if you do
    not have suitable permissions.
    """

    host = _parse_storage(arguments["storage"])
    if host is None:
        return _error(406)

    checksum = _query_s3(arguments["storage"], arguments["snapshot"], arguments["path"])
    if checksum is None:
        return _error(404)

    destination = host + "/" + arguments["platform"] + "/" + checksum

    return _redirect(destination)


def _run_redirect(arguments):
    """Handle redirects

    Some commands are parsed directly into hard-coded redirects. The use the
    `redirect` keyword and contain a single parameter `location`, which is the
    destination of the redirect.
    """

    return _redirect(arguments["location"])


def lambda_handler(event, _context):
    """Entrypoint

    This is the AWS Lambda entrypoint, called by AWS whenever the Lambda is
    invoked. The `event` structure contains the payload of the event trigger
    depending on what service invoked the Lambda. The `context` structure is
    filled with information on the execution environment, and is unused by us.

    We parse the proxy parameter and then invoke the requested command handler.
    """

    pathparameters = event.get("pathParameters", {})
    proxy = pathparameters.get("proxy")

    requestcontext = event.get("requestContext", {})
    stage = requestcontext.get("stage")

    request = _parse_proxy(stage, proxy)
    if request is None:
        if proxy == "robots.txt":
            return _success(_robots_txt)
        if proxy is None or proxy in ["", "/"]:
            return _redirect(_documentation_url)
        return _error(400)

    if "enumerate" in request:
        return _run_enumerate(request["enumerate"])
    elif "mirror" in request:
        return _run_mirror(request["mirror"])
    elif "redirect" in request:
        return _run_redirect(request["redirect"])
    else:
        return _error(400)


def test_synthesized_replies():
    """Tests for reply synthesizers"""

    r = _error()
    assert isinstance(r, dict)
    assert r["statusCode"] == 500

    r = _error(404)
    assert isinstance(r, dict)
    assert r["statusCode"] == 404

    r = _redirect("https://example.com")
    assert isinstance(r, dict)
    assert r["statusCode"] == 301
    assert isinstance(r["headers"], dict)
    assert r["headers"]["Location"] == "https://example.com"

    r = _success()
    assert isinstance(r, dict)
    assert r["statusCode"] == 200
    assert r["body"] == ""

    r = _success("foobar")
    assert isinstance(r, dict)
    assert r["statusCode"] == 200
    assert r["body"] == "foobar"


def test_parse_proxy():
    """Tests for proxy-argument parser"""

    # Generic splitter tests

    r = _parse_proxy(None, "")
    assert r is None
    r = _parse_proxy(None, "/")
    assert r is None
    r = _parse_proxy(None, "//")
    assert r is None
    r = _parse_proxy(None, "///")
    assert r is None
    r = _parse_proxy(None, "a/b/c/")
    assert r is None
    r = _parse_proxy(None, "a/b//d")
    assert r is None
    r = _parse_proxy(None, "a//c/d")
    assert r is None
    r = _parse_proxy(None, "/b/c/d")
    assert r is None
    r = _parse_proxy(None, "a/b/c/d")
    assert r is None

    # Test `control` stage

    r = _parse_proxy("control", "")
    assert r is None
    r = _parse_proxy("control", "/")
    assert r is None
    r = _parse_proxy("control", "foobar")
    assert r is None

    r = _parse_proxy("control", "snapshots")
    assert r == {
        "enumerate": {}
    }

    # Test `psi` stage

    psihost = "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/manifestdb/rpmrepo/"

    r = _parse_proxy("psi", "a/b/repodata")
    assert r == {
        "redirect": {
            "location": psihost + "repo/b/repodata"
        }
    }
    r = _parse_proxy("psi", "a/b/repodata/c")
    assert r == {
        "redirect": {
            "location": psihost + "repo/b/repodata/c"
        }
    }
    r = _parse_proxy("psi", "a/b/repodata/c/d")
    assert r == {
        "redirect": {
            "location": psihost + "repo/b/repodata/c/d"
        }
    }

    r = _parse_proxy("psi", "a/b/Packages")
    assert r == {
        "redirect": {
            "location": psihost + "rpm/a/Packages"
        }
    }
    r = _parse_proxy("psi", "a/b/Packages/c")
    assert r == {
        "redirect": {
            "location": psihost + "rpm/a/Packages/c"
        }
    }
    r = _parse_proxy("psi", "a/b/Packages/c/d")
    assert r == {
        "redirect": {
            "location": psihost + "rpm/a/Packages/c/d"
        }
    }

    # Test `v1` stage

    r = _parse_proxy("v1", "")
    assert r is None
    r = _parse_proxy("v1", "/")
    assert r is None
    r = _parse_proxy("v1", "///")
    assert r is None
    r = _parse_proxy("v1", "a/b/c/")
    assert r is None

    r = _parse_proxy("v1", "a/b/c/d")
    assert r == {
        "mirror": {
            "path": "d",
            "platform": "b",
            "snapshot": "c",
            "storage": "a",
        }
    }

    r = _parse_proxy("v1", "a/b/c/%20/%2F/xyz")
    assert r == {
        "mirror": {
            "path": " ///xyz",
            "platform": "b",
            "snapshot": "c",
            "storage": "a",
        }
    }

    # Test `enumerate` parser

    r = _parse_proxy("v2", "enumerate/")
    assert r is None
    r = _parse_proxy("v2", "enumerate/foo/bar")
    assert r is None

    r = _parse_proxy("v2", "enumerate")
    assert r == {
        "enumerate": {}
    }

    r = _parse_proxy("v2", "enumerate/foo")
    assert r == {
        "enumerate": { "thread": "foo" }
    }

    # Test `mirror` parser

    r = _parse_proxy("v2", "mirror")
    assert r is None
    r = _parse_proxy("v2", "mirror/")
    assert r is None
    r = _parse_proxy("v2", "mirror////")
    assert r is None
    r = _parse_proxy("v2", "mirror/a/b/c/")
    assert r is None

    r = _parse_proxy("v2", "mirror/a/b/c/d")
    assert r == {
        "mirror": {
            "path": "d",
            "platform": "b",
            "snapshot": "c",
            "storage": "a",
        }
    }

    r = _parse_proxy("v2", "mirror/a/b/c/%20/%2F/xyz")
    assert r == {
        "mirror": {
            "path": " ///xyz",
            "platform": "b",
            "snapshot": "c",
            "storage": "a",
        }
    }


def test_parse_storage():
    """Tests for the storage parser"""

    r = _parse_storage("")
    assert r is None

    r = _parse_storage("anon")
    assert r == "https://rpmci.s3.us-east-2.amazonaws.com/data/anon"

    r = _parse_storage("psi")
    assert r == "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/rpmci/data/anon"

    r = _parse_storage("psi-legacy")
    assert r is None # not supported as explicit storage option

    r = _parse_storage("public")
    assert r == "https://rpmrepo-storage.s3.amazonaws.com/data/public"

    r = _parse_storage("rhvpn")
    assert r == "https://rpmrepo-storage.bucket.vpce-08d3201af28373567-o10c2v4q.s3.us-east-1.vpce.amazonaws.com/data/rhvpn"


def test_query_s3():
    """Tests for the S3 checksum query"""

    # This test verifies the `_query_s3()` helper. This is a bit ugly, since
    # it will perform network requests from within unit-tests. We can always
    # gate this test in the future, if this becomes an issue.
    #
    # This test makes use of the `test/empty` file that we explicitly store in
    # the S3 buckets for testing. This is an empty file with the sha256 of an
    # empty file as metadata.

    r = _query_s3("anon", "test", "empty")
    assert r == "sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    r = _query_s3("anon", "test-invalid", "empty")
    assert r is None

    r = _query_s3("anon", "test", "empty-invalid")
    assert r is None

    r = _query_s3("public", "test", "empty")
    assert r == "sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    r = _query_s3("public", "test-invalid", "empty")
    assert r is None

    r = _query_s3("public", "test", "empty-invalid")
    assert r is None


def test_enumerate():
    """Tests for the enumerate command"""

    # Similarly to `test_query_s3()`, this test ends up accessing the network
    # in a unit-test. If this becomes an issue in the future, we can simply
    # guard the test.
    # Furthermore, this test also makes use of the `test` thread entries
    # that we have in our S3 buckets explicitly for testing.

    r = lambda_handler(
        { "pathParameters": { "proxy": "enumerate/" } },
        None,
    )
    assert r["statusCode"] == 400

    r = lambda_handler(
        { "pathParameters": { "proxy": "enumerate/foo/bar" } },
        None,
    )
    assert r["statusCode"] == 400

    r = lambda_handler(
        { "pathParameters": { "proxy": "enumerate" } },
        None,
    )
    assert r["statusCode"] == 200

    r = lambda_handler(
        { "pathParameters": { "proxy": "enumerate/test" } },
        None,
    )
    assert r["statusCode"] == 200
    assert "empty" in json.loads(r["body"])

    # TODO the prefix filtering no longer works as the entire cache gets served
    # r = lambda_handler(
    #     { "pathParameters": { "proxy": "enumerate/invalid" } },
    #     None,
    # )
    # assert r["statusCode"] == 200
    # assert r["body"] == json.dumps([])


def test_mirror():
    """Tests for the mirror command"""

    # Similarly to `test_query_s3()`, this test ends up accessing the network
    # in a unit-test. If this becomes an issue in the future, we can simply
    # guard the test.
    # Furthermore, this test also makes use of the `test/empty` snapshot file
    # that we have in our S3 buckets explicitly for testing. See
    # `test_query_s3()` for details.

    r = lambda_handler(
        { "pathParameters": { "proxy": "mirror/anon/unused/test/empty" } },
        None,
    )
    assert r["statusCode"] == 301
    assert r["headers"]["Location"] == "https://rpmci.s3.us-east-2.amazonaws.com/data/anon/unused/sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    r = lambda_handler(
        { "pathParameters": { "proxy": "mirror/public/unused/test/empty" } },
        None,
    )
    assert r["statusCode"] == 301
    assert r["headers"]["Location"] == "https://rpmrepo-storage.s3.amazonaws.com/data/public/unused/sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_robots():
    """Tests for robots.txt"""

    r = lambda_handler(
        {
            "pathParameters": {"proxy": "robots.txt"},
        },
        None,
    )
    assert r["statusCode"] == 200
    assert r["body"] == _robots_txt


def test_psi():
    """Tests for the legacy PSI stage"""

    r = lambda_handler(
        {
            "pathParameters": { "proxy": "a/b/repodata/c/d" },
            "requestContext": { "stage": "psi" },
        },
        None,
    )
    assert r["statusCode"] == 301
    assert r["headers"]["Location"] == "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/manifestdb/rpmrepo/repo/b/repodata/c/d"

    r = lambda_handler(
        {
            "pathParameters": { "proxy": "a/b/Packages/c/d" },
            "requestContext": { "stage": "psi" },
        },
        None,
    )
    assert r["statusCode"] == 301
    assert r["headers"]["Location"] == "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/manifestdb/rpmrepo/rpm/a/Packages/c/d"


def test_basics():
    """Tests for the basic redirects"""
    documentation_events = [{"pathParameters": {"proxy": "/"}},
                            {"pathParameters": {"proxy": ""}},
                            {}]

    for event in documentation_events:
        r = lambda_handler(event
                           ,
                           None,
                           )
        assert r["statusCode"] == 301
        assert r["headers"]["Location"] == _documentation_url

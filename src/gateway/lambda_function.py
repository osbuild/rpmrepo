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

import urllib.parse

import botocore
import boto3


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


def _parse_proxy(proxy):
    """Parse proxy argument"""

    # Split the proxy argument by slashes and decode each element. You are
    # allowed to encode further slashes or other special characters in each
    # element. The command handlers explicitly support that. However, we do
    # not allow empty elements, as all current commands require non-empty
    # arguments (this also means you cannot have trailing slashes for now).

    elements = proxy.split("/")
    if len(elements) < 1:
        return None

    for k, v in enumerate(elements):
        elements[k] = urllib.parse.unquote(v)
        if len(elements[k]) < 1:
            return None

    command = elements[0]
    if command == "mirror":
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
        return "https://rpmci.s3.us-east-2.amazonaws.com/data/anon"
    elif storage == "psi":
        return "https://rhos-d.infra.prod.upshift.rdu2.redhat.com:13808/v1/AUTH_95e858620fb34bcc9162d9f52367a560/rpmci/data/anon"
    elif storage == "public":
        return "https://rpmrepo.storage.s3.amazonaws.com/data/public"
    elif storage == "rhvpn":
        # XXX: This must use our VPCE to work.
        return "https://rpmrepo.storage.s3.amazonaws.com/data/rhvpn"
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
                Bucket="rpmrepo.storage",
                Key=f"data/ref/{snapshot}/{path}",
            )
        except botocore.exceptions.ClientError:
            return None

        return head.get("Metadata", {}).get("rpmrepo-checksum")


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

    request = _parse_proxy(proxy)
    if request is None:
        return _error(400)

    if "mirror" in request:
        return _run_mirror(request["mirror"])
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


def test_parse_proxy():
    """Tests for proxy-argument parser"""

    # Generic splitter tests

    r = _parse_proxy("")
    assert r is None
    r = _parse_proxy("/")
    assert r is None
    r = _parse_proxy("//")
    assert r is None
    r = _parse_proxy("///")
    assert r is None
    r = _parse_proxy("a/b/c/")
    assert r is None
    r = _parse_proxy("a/b//d")
    assert r is None
    r = _parse_proxy("a//c/d")
    assert r is None
    r = _parse_proxy("/b/c/d")
    assert r is None
    r = _parse_proxy("a/b/c/d")
    assert r is None

    # Test `mirror` parser

    r = _parse_proxy("mirror")
    assert r is None
    r = _parse_proxy("mirror/")
    assert r is None
    r = _parse_proxy("mirror////")
    assert r is None
    r = _parse_proxy("mirror/a/b/c/")
    assert r is None

    r = _parse_proxy("mirror/a/b/c/d")
    assert r == {
        "mirror": {
            "path": "d",
            "platform": "b",
            "snapshot": "c",
            "storage": "a",
        }
    }

    r = _parse_proxy("mirror/a/b/c/%20/%2F/xyz")
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

    r = _parse_storage("public")
    assert r == "https://rpmrepo.storage.s3.amazonaws.com/data/public"

    r = _parse_storage("rhvpn")
    assert r == "https://rpmrepo.storage.s3.amazonaws.com/data/rhvpn"


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
    assert r["headers"]["Location"] == "https://rpmrepo.storage.s3.amazonaws.com/data/public/unused/sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

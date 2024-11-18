#
# RPMrepo Makefile
#
# This makefile provides utility helpers for the RPMrepo repository and
# project.
#

#
# Global Setup
#
# This section sets some global parameters that get rid of some old `make`
# annoyences.
#
#     SHELL
#         We standardize on `bash` for better inline scripting capabilities,
#         and we always enable `pipefail`, to make sure individual failures
#         in a pipeline will be treated as failure.
#
#     .SECONDARY:
#         An empty SECONDARY target signals gnu-make to keep every intermediate
#         files around, even on failure. We want intermediates to stay around
#         so we get better caching behavior.
#

SHELL			:= /bin/bash -o pipefail

.SECONDARY:

#
# Parameters
#
# The set of global parameters that can be controlled by the caller and the
# calling environment.
#
#     BUILDDIR
#         Path to the directory used to store build artifacts. This defaults
#         to `./build`, so all artifacts are stored in a subdirectory that can
#         be easily cleaned.
#
#     SRCDIR
#         Path to the source code directory. This defaults to `.`, so it
#         expects `make` to be called from within the source directory.
#
#     BIN_*
#         For all binaries that are executed as part of this makefile, a
#         variable called `BIN_<exe>` defines the path or name of the
#         executable. By default, they are set to the name of the binary.
#

BUILDDIR		?= ./build
SRCDIR			?= .

BIN_MKDIR		?= mkdir
BIN_ZIP			?= zip

#
# Generic Targets
#
# The following is a set of generic targets used across the makefile. The
# following targets are defined:
#
#     help
#         This target prints all supported targets. It is meant as
#         documentation of targets we support and might use outside of this
#         repository.
#         This is also the default target.
#
#     $(BUILDDIR)/
#     $(BUILDDIR)/%/
#         This target simply creates the specified directory. It is limited to
#         the build-dir as a safety measure. Note that this requires you to use
#         a trailing slash after the directory to not mix it up with regular
#         files. Lastly, you mostly want this as order-only dependency, since
#         timestamps on directories do not affect their content.
#
#     FORCE
#         Dummy target to use as dependency to force `.PHONY` behavior on
#         targets that cannot use `.PHONY`.
#

.PHONY: help
help:
	@echo "make [TARGETS...]"
	@echo
	@echo "This is the maintenance makefile of RPMrepo. The following"
	@echo "targets are available:"
	@echo
	@echo "    help:               Print this usage information."
	@echo "    snapshot-configs:   Regenerate all snapshot configs from definitions."
	@echo "    test:               Run unit-tests."

$(BUILDDIR)/:
	$(BIN_MKDIR) -p "$@"

$(BUILDDIR)/%/:
	$(BIN_MKDIR) -p "$@"

.PHONY: FORCE
FORCE:

#
# Gateway
#
# A few helpers to build the gateway application and package them
# for AWS consumption.
#

GATEWAY_SOURCES = $(wildcard $(SRCDIR)/src/gateway/*.py)

$(BUILDDIR)/gateway/rpmrepo-gateway-%.zip: $(GATEWAY_SOURCES) | $(BUILDDIR)/gateway/
	$(BIN_ZIP) --junk-paths "$@" $+

.PHONY: gateway-zip
gateway-zip: $(BUILDDIR)/gateway/rpmrepo-gateway-main.zip

#
# Regenerate all snapshot configs from definitions
#
# This target regenerates all snapshot configuration files from the current
# definiton stored in `repo-definitions.yaml`. Before generating snapshot
# configuration files into `repo/`, it will first delete the whole content
# of the directory.

.PHONY: snapshot-configs
snapshot-configs:
	rm -f $(SRCDIR)/repo/*.json
	./gen-all-repos.py --definitions $(SRCDIR)/repo-definitions.yaml --output $(SRCDIR)/repo/

.PHONY: test
test:
	pytest src/gateway/lambda_function.py

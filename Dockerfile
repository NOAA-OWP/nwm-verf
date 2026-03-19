## TODO: replace with base image created under NGWPC-3223 ##
## see: https://jira.nextgenwaterprediction.com/browse/NGWPC-3223
ARG BASE_REPO=rockylinux
ARG BASE_TAG=8

FROM ${BASE_REPO}:${BASE_TAG}

# OCI Metadata Arguments
ARG BASE_REPO
ARG BASE_TAG
ARG BASE_NAME="${BASE_REPO}:${BASE_TAG}"
ARG BASE_DIGEST="unknown"
ARG BASE_REVISION="unknown"
ARG IMAGE_SOURCE="unknown"
ARG IMAGE_VENDOR="unknown"
ARG IMAGE_VERSION="unknown"
ARG IMAGE_REVISION="unknown"
ARG IMAGE_CREATED="unknown"

# OCI Standard Labels
LABEL org.opencontainers.image.base.name="${BASE_NAME}" \
    org.opencontainers.image.base.digest="${BASE_DIGEST}" \
    io.ngwpc.image.base.revision="${BASE_REVISION}" \
    org.opencontainers.image.source="${IMAGE_SOURCE}" \
    org.opencontainers.image.vendor="${IMAGE_VENDOR}" \
    org.opencontainers.image.version="${IMAGE_VERSION}" \
    org.opencontainers.image.revision="${IMAGE_REVISION}" \
    org.opencontainers.image.created="${IMAGE_CREATED}" \
    org.opencontainers.image.title="NWM Verification" \
    org.opencontainers.image.description="Docker image for the NWM verification application"


# ensure local python is preferred over distribution python
ENV PATH="/usr/local/bin:$PATH"

# cannot remove LANG even though https://bugs.python.org/issue19846 is fixed
# last attempted removal of LANG broke many users:
# https://github.com/docker-library/python/pull/570
ENV LANG="C.UTF-8"

ENV PYTHON_VERSION="3.10.14"

# install runtime dependencies
RUN set -eux; \
    dnf install -y epel-release; \
    dnf config-manager --set-enabled powertools; \
    dnf install -y \
        bzip2 bzip2-devel \
        cmake \
        curl curl-devel \
        file \
        findutils \
        git \
## FIXME: replace GNU compilers with Intel compiler ##
        gcc-toolset-10 \
        gcc-toolset-10-libasan-devel \
        libasan6 \
        libffi libffi-devel \
        m4 \
        openssl openssl-devel \
        rsync \
        sqlite sqlite-devel \
        tk tk-devel \
        uuid uuid-devel \
        which \
        xz \
        zlib zlib-devel \
        jq \
    ; \
    dnf clean all

## FIXME: replace GNU compilers with Intel compiler ##
SHELL [ "/usr/bin/scl", "enable", "gcc-toolset-10"]

RUN set -eux; \
	\
	curl --location --output python.tar.xz "https://www.python.org/ftp/python/${PYTHON_VERSION%%[a-z]*}/Python-$PYTHON_VERSION.tar.xz"; \
	mkdir --parents /usr/src/python; \
	tar --extract --directory /usr/src/python --strip-components=1 --file python.tar.xz; \
	rm python.tar.xz; \
	\
	cd /usr/src/python; \
	./configure \
		--enable-loadable-sqlite-extensions \
		--enable-optimizations \
		--enable-option-checking=fatal \
		--enable-shared \
		--with-lto \
		--with-system-expat \
		--without-ensurepip \
	; \
	nproc="$(nproc)"; \
	make -j "$nproc" \
		"PROFILE_TASK=${PROFILE_TASK:-}" \
	; \
# https://github.com/docker-library/python/issues/784
# prevent accidental usage of a system installed libpython of the same version
	rm python; \
	make -j "$nproc" \
		"LDFLAGS=${LDFLAGS:--Wl},-rpath='\$\$ORIGIN/../lib'" \
		"PROFILE_TASK=${PROFILE_TASK:-}" \
		python \
	; \
	make install; \
# enable GDB to load debugging data: https://github.com/docker-library/python/pull/701
    bin="$(readlink -ve /usr/local/bin/python3)"; \
    dir="$(dirname "$bin")"; \
    mkdir --parents "/usr/share/gdb/auto-load/$dir"; \
    cp -vL Tools/gdb/libpython.py "/usr/share/gdb/auto-load/$bin-gdb.py"; \
    \
    cd /; \
    rm -rf /usr/src/python; \
    \
    find /usr/local -depth \
        \( \
            \( -type d -a \( -name test -o -name tests -o -name idle_test \) \) \
            -o \( -type f -a \( -name '*.pyc' -o -name '*.pyo' -o -name 'libpython*.a' \) \) \
        \) -exec rm -rf '{}' + \
    ; \
    \
    ldconfig; \
    \
    python3 --version

# make some useful symlinks that are expected to exist ("/usr/local/bin/python" and friends)
RUN set -eux; \
	for src in idle3 pydoc3 python3 python3-config; do \
		dst="$(echo "$src" | tr -d 3)"; \
		[ -s "/usr/local/bin/$src" ]; \
		[ ! -e "/usr/local/bin/$dst" ]; \
		ln -svT "$src" "/usr/local/bin/$dst"; \
	done


ENV VIRTUAL_ENV=/ngen-app/nwm-verf-python
RUN set -eux; \
        \
        python3.10 -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

ARG NWM_EVAL_MGR_REF=development
RUN set -eux; \
	\
    pip3 install "git+https://github.com/NGWPC/nwm-eval-mgr.git@${NWM_EVAL_MGR_REF}" ; \
    pip3 cache purge

COPY . /ngen-app/nwm-verf/
WORKDIR /ngen-app/nwm-verf/
RUN set -eux; \
	\
    pip3 install . ; \
    pip3 cache purge

COPY ./docker/run-nwm-verf.sh /ngen-app/bin/
RUN set -eux; \
	\
    chmod +x /ngen-app/bin/run-nwm-verf.sh

ARG CI_COMMIT_REF_NAME

RUN set -eux; \
    repo_url=$(git config --get remote.origin.url); \
    key=${repo_url##*/}; \
    key=${key%.git}; \
    GIT_INFO_PATH="/ngen-app/${key}_git_info.json"; \
    branch=$( [ -n "${CI_COMMIT_REF_NAME:-}" ] && echo "${CI_COMMIT_REF_NAME}" || git rev-parse --abbrev-ref HEAD ); \
    jq -n \
      --arg commit_hash "$(git rev-parse HEAD)" \
      --arg branch "$branch" \
      --arg tags "$(git tag --points-at HEAD | tr '\n' ' ')" \
      --arg author "$(git log -1 --pretty=format:'%an')" \
      --arg commit_date "$(date -u -d @$(git log -1 --pretty=format:'%ct') +'%Y-%m-%d %H:%M:%S UTC')" \
      --arg message "$(git log -1 --pretty=format:'%s' | tr '\n' ';')" \
      --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
      "{\"$key\": {commit_hash: \$commit_hash, branch: \$branch, tags: \$tags, author: \$author, commit_date: \$commit_date, message: \$message, build_date: \$build_date}}" \
      > $GIT_INFO_PATH


WORKDIR /
SHELL ["/bin/bash", "-c"]

ENTRYPOINT [ "/ngen-app/bin/run-nwm-verf.sh" ]
CMD [ "--help" ]

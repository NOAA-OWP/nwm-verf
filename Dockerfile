## TODO: replace with base image created under NGWPC-3223 ##
## see: https://jira.nextgenwaterprediction.com/browse/NGWPC-3223
FROM rockylinux:8


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


ENV VIRTUAL_ENV=/ngen-app/ngen-verf-python
RUN set -eux; \
        \
        python3.10 -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

ARG NWM_EVAL_MGR_TAG=development
RUN set -eux; \
	\
    pip3 install "git+https://github.com/NGWPC/nwm-eval-mgr.git@${NWM_EVAL_MGR_TAG}" ; \
    pip3 cache purge

COPY . /ngen-app/ngen-verf/
WORKDIR /ngen-app/ngen-verf/
RUN set -eux; \
	\
    pip3 install . ; \
    pip3 cache purge

COPY ./docker/run-ngen-verf.sh /ngen-app/bin/
RUN set -eux; \
	\
    chmod +x /ngen-app/bin/run-nwm-verf.sh

WORKDIR /
SHELL ["/bin/bash", "-c"]

ENTRYPOINT [ "/ngen-app/bin/run-nwm-verf.sh" ]
CMD [ "--help" ]

FROM docker.io/mambaorg/micromamba:2.0.2-ubuntu24.04
#FROM docker.io/mambaorg/micromamba:1.5.1-jammy

LABEL maintainer="trygveas@met.no"

ENV MAPGEN_REPO=https://github.com/metno/mapgen-fastapi.git \
    MAPGEN_VERSION=main

# Install dependencies:
COPY --chown=$MAMBA_USER:$MAMBA_USER containers/fastapi/environment.yaml /tmp/environment.yaml
RUN micromamba install -y -n base --file /tmp/environment.yaml \
    && micromamba clean --force-pkgs-dirs --yes

USER root
RUN set -ex \
    && ln -s /opt/conda/bin/curl /usr/bin/curl \
    && savedAptMark="$(apt-mark showmanual)" \
    && apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y ca-certificates git lsof less build-essential libssl-dev libpcre2-dev pkg-config procps net-tools \
    && mkdir -p /usr/lib/unit/modules /usr/lib/unit/debug-modules \
    && mkdir -p /usr/src/unit \
    && cd /usr/src/unit \
    && git clone --depth 1 -b 1.33.0-1 https://github.com/nginx/unit \
    && cd unit \
    && NCPU="$(getconf _NPROCESSORS_ONLN)" \
    && DEB_HOST_MULTIARCH="$(dpkg-architecture -q DEB_HOST_MULTIARCH)" \
    && CC_OPT="$(DEB_BUILD_MAINT_OPTIONS="hardening=+all,-pie" DEB_CFLAGS_MAINT_APPEND="-Wp,-D_FORTIFY_SOURCE=2 -fPIC $(dpkg-buildflags --get CFLAGS)")" \
    && LD_OPT="$(DEB_BUILD_MAINT_OPTIONS="hardening=+all,-pie" DEB_LDFLAGS_MAINT_APPEND="-Wl,--as-needed -pie" dpkg-buildflags --get LDFLAGS)" \
    && CONFIGURE_ARGS_MODULES="--prefix=/usr \
                --statedir=/var/lib/unit \
                --control=unix:/var/run/unit/control.unit.sock \
                --runstatedir=/var/run/unit \
                --pid=/var/run/unit/unit.pid \
                --logdir=/var/log/unit \
                --log=/var/log/unit/unit.log \
                --tmpdir=/var/tmp \
                --user=$MAMBA_USER \
                --group=$MAMBA_USER \
                --openssl \
                --libdir=/usr/lib/$DEB_HOST_MULTIARCH" \
    && CONFIGURE_ARGS="$CONFIGURE_ARGS_MODULES \
                --njs" \
    && make -j $NCPU -C pkg/contrib .njs \
    && export PKG_CONFIG_PATH=$(pwd)/pkg/contrib/njs/build \
    && ./configure $CONFIGURE_ARGS --cc-opt="$CC_OPT" --ld-opt="$LD_OPT" --modulesdir=/usr/lib/unit/debug-modules --debug \
    && make -j $NCPU unitd \
    && install -pm755 build/sbin/unitd /usr/sbin/unitd-debug \
    && make clean \
    && ./configure $CONFIGURE_ARGS --cc-opt="$CC_OPT" --ld-opt="$LD_OPT" --modulesdir=/usr/lib/unit/modules \
    && make -j $NCPU unitd \
    && install -pm755 build/sbin/unitd /usr/sbin/unitd \
    && make clean \
    && /bin/true \
    && ./configure $CONFIGURE_ARGS_MODULES --cc-opt="$CC_OPT" --modulesdir=/usr/lib/unit/debug-modules --debug \
    && ./configure python --config=/opt/conda/bin/python3-config \
    && make -j $NCPU python3-install \
    && make clean \
    && ./configure $CONFIGURE_ARGS_MODULES --cc-opt="$CC_OPT" --modulesdir=/usr/lib/unit/modules \
    && ./configure python --config=/opt/conda/bin/python3-config \
    && make -j $NCPU python3-install \
    && cd \
    && rm -rf /usr/src/unit \
    && for f in /usr/sbin/unitd /usr/lib/unit/modules/*.unit.so; do \
        ldd $f | awk '/=>/{print $(NF-1)}' | while read n; do dpkg-query -S `basename $n`; done | sed 's/^\([^:]\+\):.*$/\1/' | sort | uniq >> /requirements.apt; \
       done \
    && apt-mark showmanual | xargs apt-mark auto > /dev/null \
    && { [ -z "$savedAptMark" ] || apt-mark manual $savedAptMark; } \
    && /bin/true \
    && mkdir -p /var/lib/unit/ \
    && mkdir -p /docker-entrypoint.d/ \
    && apt-get update \
    && apt-get --no-install-recommends --no-install-suggests -y install $(cat /requirements.apt) \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /requirements.apt

USER $MAMBA_USER
RUN /opt/conda/bin/pip install "git+${MAPGEN_REPO}@${MAPGEN_VERSION}" xncml
USER root
WORKDIR /app

ENV LD_LIBRARY_PATH=/usr/local/lib:/opt/conda/lib:/usr/local/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu
COPY ./docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN mkdir -pv /usr/share/unit/welcome && chown -R $MAMBA_USER:$MAMBA_USER /usr/share/unit
COPY --chown=$MAMBA_USER:$MAMBA_USER welcome.* /usr/share/unit/welcome/
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["unitd", "--no-daemon", "--control", "unix:/var/run/unit/control.unit.sock", "--statedir", "/var/lib/unit", "--pid", "/var/run/unit/unit.pid", "--log", "/proc/1/fd/1"]

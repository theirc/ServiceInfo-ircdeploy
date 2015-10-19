# For this project, we don't need a postgres server installed.
# Make sure any we used to have is uninstalled.
# Also we need a 9.4 client.
{% set pg_version = salt['pillar.get']('postgres_version', '9.4') %}

postgres_repo:
  pkgrepo.managed:
    - humanname: Postgres PPA
    - name: deb http://apt.postgresql.org/pub/repos/apt/ {{ grains['lsb_distrib_codename'] }}-pgdg main
    - file: /etc/apt/sources.list.d/postgres.list
    - key_url: salt://project/pgdg.pub
    - require_in:
      - pkg: postgres-client-packages

# REMOVE postgres server (not client) if present,
# and old client packages.
remove-postgres-server-packages:
  pkg.removed:
    - names:
      - postgresql  {# this package requires whatever version of postgres Ubuntu currently likes #}
      - postgresql-9.3
      - postgresql-9.4
      - postgresql-contrib-9.3
      - postgresql-contrib-9.4
      - postgresql-server-dev-9.3
      - postgresql-server-dev-9.4
      - postgresql-client-9.3
      - postgresql-9.3-postgis-2.1
      - postgresql-9.4-postgis-2.1
      - postgresql-common

# Postgres client, plus libraries needed by GeoDjango and PostGIS, because
# they're no longer pulled in due to having postgresql-9.x-postgis-xx installed.
postgres-client-packages:
  pkg.latest:
    - names:
      - postgresql-client-{{ pg_version }}
      - binutils
      - libproj-dev
      - gdal-bin
      - libgeoip1
      - python-gdal

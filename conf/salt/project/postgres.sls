# For this project, we don't need a postgres server installed.
# Make sure any we used to have is uninstalled.
# Also we need a 9.4 client to match the server on RDS.
{% set pg_version = salt['pillar.get']('postgres_version', '9.4') %}

# REMOVE unneeded postgres servers, and wrong version of client, if present,
# and old client packages.  We seem to have 9.3 and 9.4 on our servers.
postgres-packages:
  pkg.removed:
    - names:
      - postgresql  {# this package requires whatever version of postgres Ubuntu currently likes #}
      - postgresql-9.3
      - postgresql-contrib-9.3
      - postgresql-server-dev-9.3
      - postgresql-client-9.3
      - postgresql-9.4
      - postgresql-contrib-9.4
      - postgresql-server-dev-9.4

our-postgres-packages:
  pkg.latest:
    - names:
      - postgresql-client-{{ pg_version }}
      - postgresql-{{ pg_version }}-postgis-2.1

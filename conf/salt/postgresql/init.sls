{% set pg_version=pillar.get("postgresql_version", "9.3") %}

{% if pg_version|float < 9.3 %}
include:
  - locale.utf8
{% endif %}

postgresql-apt-repo:
  pkgrepo.managed:
    - name: 'deb http://apt.postgresql.org/pub/repos/apt/ {{ grains['oscodename'] }}-pgdg main'
    - file: /etc/apt/sources.list.d/pgdg.list
    - key_url: https://www.postgresql.org/media/keys/ACCC4CF8.asc

db-packages:
  pkg:
    - installed
    - names:
      - postgresql-{{ pg_version }}
      - libpq-dev
    - require:
      - pkgrepo: postgresql-apt-repo

postgresql:
  pkg:
    - installed
    - name: postgresql-{{ pg_version }}
  service:
    - running
    - enable: True

{% if pg_version|float < 9.3 %}
/var/lib/postgresql/configure_utf-8.sh:
  cmd.wait:
    - name: bash /var/lib/postgresql/configure_utf-8.sh
    - user: postgres
    - cwd: /var/lib/postgresql
    - unless: psql -U postgres template1 -c 'SHOW SERVER_ENCODING' | grep "UTF8"
    - require:
      - file: /etc/default/locale
    - watch:
      - file: /var/lib/postgresql/configure_utf-8.sh

  file.managed:
    - name: /var/lib/postgresql/configure_utf-8.sh
    - source: salt://postgresql/default-locale.sh
    - user: postgres
    - group: postgres
    - mode: 755
    - template: jinja
    - context:
        version: "{{ pg_version }}"
    - require:
      - pkg: postgresql
{% endif %}

{% if 'postgis' in pillar['postgresql_extensions'] %}
postgis-packages:
  pkg:
    - installed
    - names:
      - postgresql-{{ pg_version }}-postgis-2.1
      - binutils
      - libproj-dev
      - gdal-bin
      - libgeoip1
      - python-gdal
      - postgresql-server-dev-{{ pg_version }}
    - require:
      - pkg: db-packages
{% endif %}

{% import 'project/_vars.sls' as vars with context %}

include:
  - supervisor.pip
  - postgres
  - project.dirs
  - project.venv
  - project.django
  - postfix
  - ufw

gunicorn_requirements:
  pip.installed:
    - name: "gunicorn>=19.1,<19.2"
    - bin_env: {{ vars.venv_dir }}
    - upgrade: true
    - require:
      - virtualenv: venv

gunicorn_conf:
  file.managed:
    - name: /etc/supervisor/conf.d/{{ pillar['project_name'] }}-gunicorn.conf
    - source: salt://project/web/gunicorn.conf
    - user: root
    - group: root
    - mode: 600
    - template: jinja
    - context:
        newrelic_config_file: "{{ vars.services_dir }}/newrelic-app.ini"
        log_dir: "{{ vars.log_dir }}"
        settings: "{{ pillar['project_name'] }}.settings.{{ pillar['environment'] }}"
        virtualenv_root: "{{ vars.venv_dir }}"
        directory: "{{ vars.source_dir }}"
    - require:
      - pip: supervisor
      - file: log_dir
      - pip: pip_requirements
      - pip: gunicorn_requirements
    - watch_in:
      - cmd: supervisor_update

{% for host, ifaces in vars.balancer_minions.items() %}
{% set host_addr = vars.get_primary_ip(ifaces) %}
app_allow-{{ host_addr }}:
  ufw.allow:
    - name: '8000'
    - enabled: true
    - from: {{ host_addr }}
    - require:
      - pkg: ufw
{% endfor %}

# node_ppa:
#   pkgrepo.managed:
#     - ppa: chris-lea/node.js

npm:
  pkg.installed:
    - refresh: True

nodejs:
  pkg.installed:
    - require:
      - pkg: npm
    - refresh: True

node_alias:
  # Stupid ubuntu (http://askubuntu.com/questions/235655/node-js-conflicts-sbin-node-vs-usr-bin-node/320271#320271)
  cmd.run:
    - name: update-alternatives --install /usr/bin/node node /usr/bin/nodejs 10
    - require:
        - pkg: nodejs

less:
  cmd.run:
    - name: npm install less@1.5.1 -g
    - user: root
    - unless: "which lessc && lessc --version | grep 1.5.1"
    - require:
      - cmd: node_alias

# Need to run install in case this is the first time, and
# update in case it's not the first time.  Unfortunately there's
# not a single command that will figure out for itself what to do,
# and it seems safest to just run both.
npm_installs:
  cmd.run:
    - name: npm install; npm update
    - cwd: "{{ vars.source_dir }}"
    - user: {{ pillar['project_name'] }}
    - require:
      - cmd: node_alias

make_bundle:
  cmd.run:
    - name: "gulp build --config={{ pillar['environment'] }}"
    - cwd: "{{ vars.source_dir }}"
    - user: {{ pillar['project_name'] }}
    - env:
        PATH: "{{ vars.source_dir }}/node_modules/.bin:{{ salt['grains.get']('path') }}"
    - require:
      - cmd: npm_installs

static_dir:
  file.directory:
    - name: {{ vars.static_dir }}
    - user: {{ pillar['project_name'] }}
    - group: www-data
    - dir_mode: 775
    - file_mode: 664
    - makedirs: True
    - recurse:
      - user
      - group
      - mode
    - require:
      - file: root_dir

collectstatic:
  cmd.run:
    - name: "{{ vars.path_from_root('manage.sh') }} collectstatic --noinput"
    - user: {{ pillar['project_name'] }}
    - group: {{ pillar['project_name'] }}
    - require:
      - file: manage
      - file: static_dir
      - cmd: make_bundle

migrate:
  cmd.run:
    - name: "{{ vars.path_from_root('manage.sh') }} migrate --noinput"
    - user: {{ pillar['project_name'] }}
    - group: {{ pillar['project_name'] }}
    - onlyif: "{{ vars.path_from_root('manage.sh') }} migrate --list | grep '\\[ \\]'"
    - require:
      - file: manage
    - order: last

gunicorn_process:
  supervisord.running:
    - name: {{ pillar['project_name'] }}-server
    - restart: True
    - require:
      - file: gunicorn_conf
      - cmd: collectstatic
      - cmd: migrate

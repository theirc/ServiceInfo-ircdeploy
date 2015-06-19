{% import 'project/_vars.sls' as vars with context %}

include:
  - project.dirs
  - project.repo
  - python

python-pkgs:
  pkg:
    - installed
    - names:
      - python{{ pillar['python_version'] }}-complete
    - require:
      - pkgrepo: deadsnakes

# The virtualenv from Ubuntu 12.04 doesn't seem up to installing Python 3.4 stuff...
# Create our venv our own way. Once it's created, we can use its pip from then on.
make_the_venv:
  cmd.run:
    - name: pyvenv-3.4 {{ vars.venv_dir }}
    - unless:
      - test -x {{ vars.venv_dir }}/bin/pip
    - check_cmd:
      - test -x {{ vars.venv_dir }}/bin/pip
    - require:
      - file: root_dir
      - file: project_repo
      - pkg: python-pkgs

pip_requirements:
  pip.installed:
    - bin_env: {{ vars.venv_dir }}/bin/pip
    - requirements: {{ vars.build_path(vars.source_dir, 'requirements/production.txt') }}
    - upgrade: true
    - require:
      - cmd: make_the_venv

project_path:
  file.managed:
    - contents: "{{ vars.source_dir }}"
    - name: {{ vars.build_path(vars.venv_dir, 'lib/python' ~ pillar['python_version'] ~ '/site-packages/project.pth') }}
    - user: {{ pillar['project_name'] }}
    - group: {{ pillar['project_name'] }}
    - require:
      - pip: pip_requirements

ghostscript:
  pkg.installed

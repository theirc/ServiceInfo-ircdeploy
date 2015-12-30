base:
  '*':
    - base
    - sudo
    - sshd
    - sshd.github
    - locale.utf8
    - project.devs
    - salt.minion
{% if 'newrelic_license_key' in pillar['secrets'] %}
    - newrelic_sysmon
{% endif %}
  'roles:salt-master':
    - match: grain
    - salt.master
  'roles:web':
    - match: grain
    - project.web.app
    - postgres
    - project.elasticsearch
{% if 'newrelic_license_key' in pillar['secrets'] %}
    - project.newrelic_webmon
{% endif %}
  'roles:worker':
    - match: grain
    - postgres
    - project.elasticsearch
    - project.worker.default
  'roles:beat':
    - match: grain
    - project.worker.beat
  'roles:balancer':
    - match: grain
    - project.web.balancer
  'roles:queue':
    - match: grain
    - project.queue
  'roles:cache':
    - match: grain
    - project.cache

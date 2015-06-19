import os
import subprocess
import tempfile

import yaml

from fabric.api import env, execute, get, hide, lcd, local, put, require, run, settings, sudo, task
from fabric.colors import red
from fabric.contrib import files, project
from fabric.contrib.console import confirm
from fabric.utils import abort

DEFAULT_SALT_LOGLEVEL = 'info'
PROJECT_NAME = "service_info"
PROJECT_ROOT = os.path.dirname(__file__)
CONF_ROOT = os.path.join(PROJECT_ROOT, 'conf')

VALID_ROLES = (
    'salt-master',
    'web',
    'worker',
    'balancer',
    'db-master',
    'queue',
    'cache',
    'beat',
)


@task
def staging():
    env.environment = 'staging'
    # 54.93.66.254 Staging server on AWS Frankfurt
    # Internal hostname for our own access to the server
    # To change the domain, see conf/pillar/<envname>/env.sls
    # env.master = 'serviceinfo-staging.rescue.org'
    env.master = 'ec2-54-93-66-254.eu-central-1.compute.amazonaws.com'
    env.hosts = [env.master]

@task
def testing():
    """TEMPORARY - for testing the open source deploy changes"""
    env.environment = 'testing'
    env.master = 'ec2-54-152-72-255.compute-1.amazonaws.com'
    env.hosts = [env.master]


@task
def production():
    env.environment = 'production'
    # Internal hostname for our own access to the server
    # To change the domain, see conf/pillar/<envname>/env.sls
    # env.master = 'serviceinfo.rescue.org'
    env.master = 'ec2-54-93-51-232.eu-central-1.compute.amazonaws.com'
    env.hosts = [env.master]


@task
def setup_master():
    """Provision master with salt-master."""
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr'):
            installed = run('which salt')
    if not installed:
        sudo('apt-get update -qq -y')
        sudo('apt-get install python-software-properties -qq -y')
        sudo('add-apt-repository ppa:saltstack/salt -y')
        sudo('apt-get update -qq')
        sudo('apt-get install salt-master -qq -y')
    # make sure git is installed for gitfs
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr'):
            installed = run('which git')
    if not installed:
        sudo('apt-get install python-pip git-core -qq -y')
        sudo('pip install -q -U GitPython')
    put(local_path='conf/master.conf', remote_path="/etc/salt/master", use_sudo=True)
    sudo('service salt-master restart')


@task
def sync():
    """Rysnc local states and pillar data to the master."""
    # Check for missing local secrets so that they don't get deleted
    # project.rsync_project fails if host is not set
    if not have_secrets():
        get_secrets()
    else:
        # Check for differences in the secrets files
        for environment in [env.environment]:
            remote_file = os.path.join('/srv/pillar/', environment, 'secrets.sls')
            with lcd(os.path.join(CONF_ROOT, 'pillar', environment)):
                if files.exists(remote_file):
                    get(remote_file, 'secrets.sls.remote')
                else:
                    local('touch secrets.sls.remote')
                with settings(warn_only=True):
                    result = local('diff -u secrets.sls.remote secrets.sls')
                    if result.failed and not confirm(
                            red("Above changes will be made to secrets.sls. Continue?")):
                        abort("Aborted. File have been copied to secrets.sls.remote. " +
                              "Resolve conflicts, then retry.")
                    else:
                        local("rm secrets.sls.remote")
    salt_root = CONF_ROOT if CONF_ROOT.endswith('/') else CONF_ROOT + '/'
    project.rsync_project(local_dir=salt_root, remote_dir='/tmp/salt', delete=True)
    sudo('mkdir -p /srv')
    sudo('rm -rf /srv/salt /srv/pillar')
    sudo('mv /tmp/salt/* /srv/')
    sudo('rm -rf /tmp/salt/')


def have_secrets():
    """Check if the local secret files exist for all environments."""
    found = True
    for environment in [env.environment]:
        local_file = os.path.join(CONF_ROOT, 'pillar', environment, 'secrets.sls')
        found = found and os.path.exists(local_file)
    return found


@task
def get_secrets():
    """Grab the latest secrets file from the master."""
    require('environment')
    for environment in [env.environment]:
        local_file = os.path.join(CONF_ROOT, 'pillar', environment, 'secrets.sls')
        if os.path.exists(local_file):
            local('cp {0} {0}.bak'.format(local_file))
        remote_file = os.path.join('/srv/pillar/', environment, 'secrets.sls')
        get(remote_file, local_file)


@task
def setup_minion(*roles):
    """Setup a minion server with a set of roles."""
    require('environment')
    for r in roles:
        if r not in VALID_ROLES:
            abort('%s is not a valid server role for this project.' % r)
    # install salt minion if it's not there already
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr'):
            installed = run('which salt-minion')
    if not installed:
        # install salt-minion from PPA
        sudo('apt-get update -qq -y')
        sudo('apt-get install python-software-properties -qq -y')
        sudo('add-apt-repository ppa:saltstack/salt -y')
        sudo('apt-get update -qq')
        sudo('apt-get install salt-minion -qq -y')
    config = {
        'master': 'localhost' if env.master == env.host else env.master,
        'output': 'mixed',
        'grains': {
            'environment': env.environment,
            'roles': list(roles),
        },
        'mine_functions': {
            'network.interfaces': []
        },
    }
    _, path = tempfile.mkstemp()
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    put(local_path=path, remote_path="/etc/salt/minion", use_sudo=True)
    sudo('service salt-minion restart')
    # queries server for its fully qualified domain name to get minion id
    key_name = run('python -c "import socket; print socket.getfqdn()"')
    execute(accept_key, key_name)


@task
def add_role(name):
    """Add a role to an exising minion configuration."""
    if name not in VALID_ROLES:
        abort('%s is not a valid server role for this project.' % name)
    _, path = tempfile.mkstemp()
    get("/etc/salt/minion", path)
    with open(path, 'r') as f:
        config = yaml.safe_load(f)
    grains = config.get('grains', {})
    roles = grains.get('roles', [])
    if name not in roles:
        roles.append(name)
    else:
        abort('Server is already configured with the %s role.' % name)
    grains['roles'] = roles
    config['grains'] = grains
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    put(local_path=path, remote_path="/etc/salt/minion", use_sudo=True)
    sudo('service salt-minion restart')


@task
def salt(cmd, target="'*'", loglevel=DEFAULT_SALT_LOGLEVEL):
    """Run arbitrary salt commands."""
    with settings(warn_only=True):
        sudo("salt {0} -l{1} {2} ".format(target, loglevel, cmd))


@task
def highstate(target="'*'", loglevel=DEFAULT_SALT_LOGLEVEL):
    """Run highstate on master."""
    print("This can take a long time without output, be patient")
    execute(salt, 'state.highstate', target, loglevel, hosts=[env.master])


@task
def accept_key(name):
    """Accept minion key on master."""
    sudo('salt-key --accept={0} -y'.format(name))
    sudo('salt-key -L')


@task
def delete_key(name):
    """Delete specific key on master."""
    sudo('salt-key -L')
    sudo('salt-key --delete={0} -y'.format(name))
    sudo('salt-key -L')


@task
def deploy(loglevel=DEFAULT_SALT_LOGLEVEL):
    """Deploy to a given environment by pushing the latest states and executing the highstate."""
    require('environment')
    if env.environment != "local":
        sync()
    target = "-G 'environment:{0}'".format(env.environment)
    salt('saltutil.sync_all', target, loglevel)
    highstate(target)


@task
def manage_run(command):
    """
    Run a Django management command on the remote server.
    """
    require('environment')
    # Setup the call
    settings = '{0}.settings.{1}'.format(PROJECT_NAME, env.environment)
    manage_sh = u"DJANGO_SETTINGS_MODULE={0} /var/www/{1}/manage.sh ".format(settings, PROJECT_NAME)
    sudo(manage_sh + command, user=PROJECT_NAME)


@task
def ssh():
    """
    Convenience task to ssh to whatever host has been selected.

    E.g. ``fab production ssh``
    """
    require('environment')
    local("ssh %s" % env.hosts[0])

import os
import re
import tempfile

import yaml

from fabric.api import cd, env, execute, get, hide, lcd, local, put, require, run, settings, sudo, task
from fabric.colors import red, green
from fabric.contrib import files, project
from fabric.contrib.console import confirm
from fabric.utils import abort

DEFAULT_SALT_LOGLEVEL = 'info'
SALT_VERSION = '2015.5.1'
PROJECT_NAME = "service_info"
PROJECT_ROOT = os.path.dirname(__file__)
CONF_ROOT = os.path.join(PROJECT_ROOT, 'conf')

VALID_ROLES = (
    'salt-master',
    'web',
    'worker',
    'balancer',
    'queue',
    'cache',
    'beat',
)


def _common_env():
    env.project = PROJECT_NAME
    env.project_root = os.path.join('/var', 'www', env.project)
    env.media_source = os.path.join(env.project_root, 'public', 'media')
    env.db_wrapper = os.path.join(env.project_root, 'run_with_db.sh')
    # refresh_environment() needs this even though the task is run against staging
    env.production_master = 'ec2-54-93-51-232.eu-central-1.compute.amazonaws.com'


@task
def staging():
    _common_env()
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
    _common_env()
    env.environment = 'testing'
    env.master = 'serviceinfo-testing.caktusgroup.com'
    env.hosts = [env.master]


@task
def production():
    _common_env()
    env.environment = 'production'
    # Internal hostname for our own access to the server
    # To change the domain, see conf/pillar/<envname>/env.sls
    # env.master = 'serviceinfo.rescue.org'
    env.master = env.production_master
    env.hosts = [env.master]


def get_salt_version(command):
    """Run `command` --version, pick out the part of the output that is digits and dots,
    and return it as a string.
    If the command fails, return None.
    """
    with settings(warn_only=True):
        with hide('running', 'stdout', 'stderr'):
            result = run('%s --version' % command)
            if result.succeeded:
                return re.search(r'([\d\.]+)', result).group(0)


@task
def install_salt(version, master=False, minion=False, restart=True):
    """
    Install or upgrade Salt minion and/or master if needed.

    :param version: Version string, just numbers and dots, no leading 'v'.  E.g. "2015.5.0".
      THERE IS NO DEFAULT, you must pick a version.
    :param master: If True, include master in the install.
    :param minion: If True, include minion in the install.
    :param restart: If we don't need to reinstall a salt package, restart its server anyway.
    :returns: True if any changes were made, False if nothing was done.
    """
    master_version = None
    install_master = False
    if master:
        master_version = get_salt_version("salt")
        install_master = master_version != version
        if install_master and master_version:
            # Already installed - if Ubuntu package, uninstall current version first
            # because we're going to do a git install later
            sudo("apt-get purge salt-master -y")
        if restart and not install_master:
            sudo("service salt-master restart")

    minion_version = None
    install_minion = False
    if minion:
        minion_version = get_salt_version('salt-minion')
        install_minion = minion_version != version
        if install_minion and minion_version:
            # Already installed - if Ubuntu package, uninstall current version first
            # because we're going to do a git install later
            sudo("apt-get purge salt-minion -y")
        if restart and not install_minion:
            sudo("service salt-minion restart")

    if install_master or install_minion:
        args = []
        if install_master:
            args.append('-M')
        if not install_minion:
            args.append('-N')
        args = ' '.join(args)
        # To update local install_salt.sh: wget -O install_salt.sh https://bootstrap.saltstack.com
        # then inspect it
        put(local_path="install_salt.sh", remote_path="install_salt.sh")
        sudo("sh install_salt.sh -D {args} git v{version}".format(args=args, version=version))
        return True
    return False


@task
def setup_master():
    """Provision master with salt-master."""

    # Get config onto system before the bootstrap tries to start salt
    sudo("mkdir -p /etc/salt")
    put(local_path='conf/master.conf', remote_path="/etc/salt/master", use_sudo=True)
    # If no changes, restart salt-master anyway
    install_salt(SALT_VERSION, master=True, restart=True)


@task
def sync():
    """Rysnc local states and pillar data to the master, and checkout margarita."""
    # Check for missing local secrets so that they don't get deleted
    # project.rsync_project fails if host is not set
    sudo("mkdir -p /srv")
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
                    if result.failed and files.exists(remote_file) and not confirm(
                            red("Above changes will be made to secrets.sls. Continue?")):
                        abort("Aborted. File have been copied to secrets.sls.remote. " +
                              "Resolve conflicts, then retry.")
                    else:
                        local("rm secrets.sls.remote")
    salt_root = CONF_ROOT if CONF_ROOT.endswith('/') else CONF_ROOT + '/'
    project.rsync_project(local_dir=salt_root, remote_dir='/tmp/salt', delete=True)
    sudo('rm -rf /srv/salt /srv/pillar')
    sudo('mv /tmp/salt/* /srv/')
    sudo('rm -rf /tmp/salt/')
    execute(margarita)


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
    config = {
        'master': 'localhost' if env.master == env.host else env.master,
        'output': 'mixed',
        'grains': {
            'environment': env.environment,
            'roles': list(roles),
        },
        'mine_functions': {
            'network.interfaces': [],
            'network.ip_addrs': []
        },
    }
    _, path = tempfile.mkstemp()
    with open(path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)
    sudo("mkdir -p /etc/salt")
    put(local_path=path, remote_path="/etc/salt/minion", use_sudo=True)
    # install salt minion if it's not there already
    install_salt(SALT_VERSION, master=False, minion=True, restart=True)
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
def margarita():
    require('environment')
    execute(state, 'margarita')
    sudo('service salt-master restart')


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
def state(name, target="'*'"):
    salt('state.sls {}'.format(name), target)


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


@task
def get_db_dump(clean=False):
    """Get db dump of remote enviroment."""
    require('environment')
    db_name = '%(project)s_%(environment)s' % env
    dump_file = db_name + '.sql' % env
    temp_file = os.path.join(env.project_root, dump_file)
    flags = '-Ox'
    if clean:
        flags += 'c'
    dump_command = '%s pg_dump %s %s -U %s > %s' % (env.db_wrapper, flags, db_name, db_name, temp_file)
    with settings(host_string=env.master):
        sudo(dump_command, user=env.project)
        get(temp_file, dump_file)


@task
def reset_local_db():
    """ Reset local database from remote host """
    require('environment')
    question = 'Are you sure you want to reset your local ' \
               'database with the %(environment)s database?' % env
    if not confirm(question, default=False):
        abort('Local database reset aborted.')
    remote_db_name = '%(project)s_%(environment)s' % env
    db_dump_name = remote_db_name + '.sql'
    local_db_name = env.project
    get_db_dump()
    with settings(warn_only=True):
        local('dropdb %s' % local_db_name)
    local('createdb -E UTF-8 %s' % local_db_name)
    local('psql %s -c "CREATE EXTENSION postgis;"' % local_db_name)
    local('cat %s | psql %s' % (db_dump_name, local_db_name))


@task
def reset_local_media(service_info_directory):
    """ Reset local media from remote host """
    require('environment')
    media_target = os.path.join(service_info_directory, 'public')
    with settings():
        local("rsync -rvaz %s:%s %s" % (env.master, env.media_source, media_target))


@task
def refresh_environment(project_path=None):
    """
    Refresh any non-production environment with new DB data and new media.

    If ``project_path`` is not provided, then we get a DB dump and media from production.

    If ``project_path`` is provided, then we get the DB dump and media from inside the
    ``project_path``. We expect the dump to be at ``${project_path}/service_info.sql`` and
    the media to be at ``${project_path}/public/media``.
    """
    require('environment')
    if env.environment == 'production':
        abort('Production cannot be refreshed!')
    dump_file_name = '%(project)s.sql' % env
    media_path = 'media'
    db_name = db_user = '%s_%s' % (env.project, env.environment)

    if project_path is None:
        # We are refreshing from the live production server
        prod_dump_file_path = os.path.join('/tmp', dump_file_name)

        with settings(host_string=env.production_master):
            prod_db_name = '%(project)s_production' % env
            sudo('%s pg_dump -Ox %s -U %s > %s' % (env.db_wrapper, prod_db_name, prod_db_name, prod_dump_file_path))
            get(prod_dump_file_path, dump_file_name)
            get(env.media_source, media_path)
            sudo('rm -f %s' % prod_dump_file_path)
    else:
        # We are refreshing from files in the local project_path directory
        current_dump_path = os.path.join(project_path, dump_file_name)
        current_media_path = os.path.join(project_path, 'public', media_path)
        local('cp %s %s' % (current_dump_path, dump_file_name))
        local('cp -r %s .' % current_media_path)

    with cd('/tmp'):
        put(local_path=dump_file_name, remote_path=dump_file_name)
        # stop the servers
        sudo('supervisorctl stop all')

        # Backup DB, create fresh DB, and install dump into it
        sudo('%s dropdb --if-exists %s_backup' % (env.db_wrapper, db_name))
        sudo('%s psql master -c "alter database %s rename to %s_backup"' % (env.db_wrapper, db_name, db_name))
        sudo('%s createdb -E UTF-8 -O %s %s' % (env.db_wrapper, db_user, db_name))
        sudo('%s psql %s -c "CREATE EXTENSION postgis;"' % (env.db_wrapper, db_name))
        sudo('%s psql -U %s -d %s -f %s' % (env.db_wrapper, db_user, db_name, dump_file_name))
        sudo('rm -f %s' % dump_file_name)

        # Backup and refresh the media
        local('rsync -zPae ssh --delete %s %s:/tmp/ ' % (media_path, env.master))
        sudo('rm -rf %s.backup' % env.media_source)
        with settings(warn_only=True):
            sudo('mv %s %s.backup' % (env.media_source, env.media_source))
        sudo('cp -r %s %s' % (media_path, env.media_source))
        sudo('chown -R %s:%s %s' % (env.project, env.project, env.media_source))
        sudo('rm -rf %s' % media_path)

    manage_run("migrate --noinput")
    manage_run("change_cms_site --from=serviceinfo.rescue.org --to=serviceinfo-staging.rescue.org")
    manage_run("rebuild_index --noinput")
    sudo('supervisorctl start all')
    local('rm -rf %s %s' % (dump_file_name, media_path))


@task
def refresh_from_backup(project_path):
    refresh_environment(project_path)
    print(green('Backup has been restored. It sometimes takes a few minutes for the load '
                'balancer to realize things are healthy again.'))

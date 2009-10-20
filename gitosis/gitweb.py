"""
Generate ``gitweb`` project list based on ``gitosis.conf``.

To plug this into ``gitweb``, you have two choices.

- The global way, edit ``/etc/gitweb.conf`` to say::

	$projects_list = "/path/to/your/projects.list";

  Note that there can be only one such use of gitweb.

- The local way, create a new config file::

	do "/etc/gitweb.conf" if -e "/etc/gitweb.conf";
	$projects_list = "/path/to/your/projects.list";
        # see ``repositories`` in the ``gitosis`` section
        # of ``~/.gitosis.conf``; usually ``~/repositories``
        # but you need to expand the tilde here
	$projectroot = "/path/to/your/repositories";

   Then in your web server, set environment variable ``GITWEB_CONFIG``
   to point to this file.

   This way allows you have multiple separate uses of ``gitweb``, and
   isolates the changes a bit more nicely. Recommended.
"""

import os, urllib, logging, glob, pwd

from ConfigParser import NoSectionError, NoOptionError

from gitosis import util

def _escape_filename(s):
    s = s.replace('\\', '\\\\')
    s = s.replace('$', '\\$')
    s = s.replace('"', '\\"')
    return s

def _generate_user_module_entry(name, repositories, fp):

    log = logging.getLogger('gitosis.gitweb._generate_user_module_entry')
    remove = repositories + os.sep
    userpos = -1

    # Deal with wildcards in the path
    if -1 != name.find('$user'):
        namesplit = name.split(os.sep)
        # Work out which of the path components matches '$user' so
        # we can use it later
        for i in range(len(namesplit)):
            if namesplit[i] == '$user':
                userpos = i
                break
        name = name.replace('$user', '*')

    if -1 != name.find('*'):
        for entry in glob.glob(os.path.join(repositories, name)):
            entry = entry.replace(remove, '')
            # Now, if we have a userpos we can use that to work
            # out who owns this repository
            if userpos != -1:
                namesplit = entry.split(os.sep)
                owner = namesplit[userpos]
                try:
                    # Let's see if we can get a full name rather
                    # than just username here
                    pwnam = pwd.getpwnam(owner)
                    owner = pwnam[4]
                except:
                    pass
            else:
                owner = ""
            response = [entry]
            response.append(owner)
            line = ' '.join([urllib.quote_plus(s) for s in response])
            print >>fp, line
            log.debug('Found entry %s' % line)


def generate_project_list_fp(config, fp):
    """
    Generate projects list for ``gitweb``.

    :param config: configuration to read projects from
    :type config: RawConfigParser

    :param fp: writable for ``projects.list``
    :type fp: (file-like, anything with ``.write(data)``)
    """
    log = logging.getLogger('gitosis.gitweb.generate_projects_list')

    repositories = util.getRepositoryDir(config)

    try:
        global_enable = config.getboolean('gitosis', 'gitweb')
    except (NoSectionError, NoOptionError):
        global_enable = False

    for section in config.sections():
        l = section.split(None, 1)
        type_ = l.pop(0)
        if type_ != 'repo':
            continue
        if not l:
            continue

        try:
            enable = config.getboolean(section, 'gitweb')
        except (NoSectionError, NoOptionError):
            enable = global_enable

        if not enable:
            continue

        name, = l

        # Special handling for $user and wildcard repositories
        if -1 != name.find('$user') or -1 != name.find('*'):
            _generate_user_module_entry(name, repositories, fp)
            continue

        if not os.path.exists(os.path.join(repositories, name)):
            namedotgit = '%s.git' % name
            if os.path.exists(os.path.join(repositories, namedotgit)):
                name = namedotgit
            else:
                log.warning(
                    'Cannot find %(name)r in %(repositories)r'
                    % dict(name=name, repositories=repositories))

        response = [name]
        try:
            owner = config.get(section, 'owner')
        except (NoSectionError, NoOptionError):
            pass
        else:
            response.append(owner)

        line = ' '.join([urllib.quote_plus(s) for s in response])
        print >>fp, line

def generate_project_list(config, path):
    """
    Generate projects list for ``gitweb``.

    :param config: configuration to read projects from
    :type config: RawConfigParser

    :param path: path to write projects list to
    :type path: str
    """
    tmp = '%s.%d.tmp' % (path, os.getpid())

    f = file(tmp, 'w')
    try:
        generate_project_list_fp(config=config, fp=f)
    finally:
        f.close()

    f.flush()
    os.fsync(f.fileno())
    os.rename(tmp, path)

def _write_description(repositories, name, description):

    log = logging.getLogger('gitosis.gitweb.write_description')

    path = os.path.join(
        repositories,
        name,
        'description',
        )

    log.debug('Writing new description file %s' % path)

    tmp = '%s.%d.tmp' % (path, os.getpid())
    f = file(tmp, 'w')
    try:
        print >>f, description
    finally:
        f.close()
    f.flush()
    os.fsync(f.fileno())
    os.rename(tmp, path)

def _generate_user_description_entry(name, repositories, description):

    log = logging.getLogger('gitosis.gitweb._generate_user_description_entry')
    remove = repositories + os.sep
    userpos = -1

    # Deal with wildcards in the path
    if -1 != name.find('$user'):
        namesplit = name.split(os.sep)
        # Work out which of the path components matches '$user' so
        # we can use it later
        for i in range(len(namesplit)):
            if namesplit[i] == '$user':
                userpos = i
                break
        name = name.replace('$user', '*')

    if -1 != name.find('*'):
        for entry in glob.glob(os.path.join(repositories, name)):
            relative = entry.replace(remove, '', 1)
            # Now, if we have a userpos we can use that to work
            # out who owns this repository
            if userpos != -1:
                namesplit = relative.split(os.sep)
                owner = namesplit[userpos]
                try:
                    # Let's see if we can get a full name rather
                    # than just username here
                    pwnam = pwd.getpwnam(owner)
                    owner = pwnam[4]
                except:
                    pass
            else:
                owner = ""

            new_description = description.replace('$username', owner)
            log.debug('Found entry %s: %s' % (entry, new_description))
            _write_description(repositories, entry, new_description)

def set_descriptions(config):
    """
    Set descriptions for gitweb use.
    """
    log = logging.getLogger('gitosis.gitweb.set_descriptions')

    repositories = util.getRepositoryDir(config)

    for section in config.sections():
        l = section.split(None, 1)
        type_ = l.pop(0)
        if type_ != 'repo':
            continue
        if not l:
            continue

        try:
            description = config.get(section, 'description')
        except (NoSectionError, NoOptionError):
            continue

        if not description:
            continue

        name, = l

        log.debug('looking at name %s' % name)

        # Special handling for $user and wildcard repositories
        if -1 != name.find('$user') or -1 != name.find('*'):
            _generate_user_description_entry(name, repositories, description)
            continue

        if not os.path.exists(os.path.join(repositories, name)):
            namedotgit = '%s.git' % name
            if os.path.exists(os.path.join(repositories, namedotgit)):
                name = namedotgit
            else:
                log.warning(
                    'Cannot find %(name)r in %(repositories)r'
                    % dict(name=name, repositories=repositories))
                continue

        _write_description(repositories, name, description)

import os, logging
from ConfigParser import NoSectionError, NoOptionError

from gitosis import group

def pathMatch(path, repo):
    """
    Compare path and repos, dealing with wildcards where appropriate
    """

    log = logging.getLogger('gitosis.access.pathMatch')

    pathsplit = path.split(os.sep)
    reposplit = repo.split(os.sep)

    # Must have the same number of components
    if len(pathsplit) != len(reposplit):
        return None

    # Compare each component individually. Both '*' and '$user' count
    # as simple wildcards here; '$user' will already have been
    # replaced by the current username before we get here on the
    # second ($user) pass
    for i in range(len(pathsplit)):
        if (
            pathsplit[i] != reposplit[i] and 
            reposplit[i] != '*' and
            reposplit[i] != '$user'
           ):
            log.debug('path match %d failed; %s != %s and no wildcard match' % (i, pathsplit[i], reposplit[i]))
            return None

    log.debug('paths %s and %s match ok!' % (path, repo))
    return path


def haveAccess(config, user, mode, path):
    """
    Map request for write access to allowed path.

    Note for read-only access, the caller should check for write
    access too.

    Returns ``None`` for no access, or a tuple of toplevel directory
    containing repositories and a relative path to the physical repository.
    """
    log = logging.getLogger('gitosis.access.haveAccess')

    log.debug(
        'Access check for %(user)r as %(mode)r on %(path)r...'
        % dict(
        user=user,
        mode=mode,
        path=path,
        ))

    basename, ext = os.path.splitext(path)
    if ext == '.git':
        log.debug(
            'Stripping .git suffix from %(path)r, new value %(basename)r'
            % dict(
            path=path,
            basename=basename,
            ))
        path = basename

    for groupname in group.getMembership(config=config, user=user):
        try:
            repos = config.get('group %s' % groupname, mode)
        except (NoSectionError, NoOptionError):
            repos = []
        else:
            repos = repos.split()

        mapping = None

        for repo in repos:
            if pathMatch(path, repo):
                log.debug(
                    'Access ok for %(user)r as %(mode)r on %(path)r'
                    % dict(
                    user=user,
                    mode=mode,
                    path=path,
                    ))
                mapping = path
        if mapping is None:
            try:
                mapping = config.get('group %s' % groupname,
                                     'map %s %s' % (mode, path))
            except (NoSectionError, NoOptionError):
                pass
            else:
                log.debug(
                    'Access ok for %(user)r as %(mode)r on %(path)r=%(mapping)r'
                    % dict(
                    user=user,
                    mode=mode,
                    path=path,
                    mapping=mapping,
                    ))

        if mapping is not None:
            prefix = None
            try:
                prefix = config.get(
                    'group %s' % groupname, 'repositories')
            except (NoSectionError, NoOptionError):
                try:
                    prefix = config.get('gitosis', 'repositories')
                except (NoSectionError, NoOptionError):
                    prefix = 'repositories'

            log.debug(
                'Using prefix %(prefix)r for %(path)r'
                % dict(
                prefix=prefix,
                path=mapping,
                ))
            return (prefix, mapping)

    # Now see if we have access using the $user rules
    for groupname in group.getMembership(config=config, user='$user'):
        try:
            repos = config.get('group %s' % groupname, mode)
        except (NoSectionError, NoOptionError):
            repos = []
        else:
            repos = repos.split()

        mapping = None

        for repo in repos:
            # Substitute in our own username to replace $user now
            repo = repo.replace('$user', user)
            log.debug('map-> user %s has %s access to repo %s' % (user, mode, repo))

            if pathMatch(path, repo):
                log.debug(
                    'Access ok for $user %(user)r as %(mode)r on %(path)r'
                    % dict(
                    user=user,
                    mode=mode,
                    path=path,
                    ))
                mapping = path
            else:
                try:
                    mapping = config.get('group %s' % groupname,
                                         'map %s %s' % (mode, path))
                except (NoSectionError, NoOptionError):
                    pass
                else:
                    log.debug(
                        'Access ok for %(user)r as %(mode)r on %(path)r=%(mapping)r'
                        % dict(
                        user='$user',
                        mode=mode,
                        path=path,
                        mapping=mapping,
                        ))

        if mapping is not None:
            prefix = None
            try:
                prefix = config.get(
                    'group %s' % groupname, 'repositories')
            except (NoSectionError, NoOptionError):
                try:
                    prefix = config.get('gitosis', 'repositories')
                except (NoSectionError, NoOptionError):
                    prefix = 'repositories'

            log.debug(
                'Using prefix %(prefix)r for %(path)r'
                % dict(
                prefix=prefix,
                path=mapping,
                ))
            return (prefix, mapping)


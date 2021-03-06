"""
Enforce git-shell to only serve allowed by access control policy.
directory. The client should refer to them without any extra directory
prefix. Repository names are forced to match ALLOW_RE.
"""

import logging

import sys, os, re
import subprocess

from gitosis import access
from gitosis import repository
from gitosis import gitweb
from gitosis import gitdaemon
from gitosis import app
from gitosis import util
from gitosis.repository import GitInitError

from ConfigParser import NoSectionError, NoOptionError

log = logging.getLogger('gitosis.serve')

ALLOW_RE = re.compile("^'/*(?P<path>[a-zA-Z0-9][a-zA-Z0-9@._-]*(/[a-zA-Z0-9][a-zA-Z0-9@._-]*)*)'$")

COMMANDS_READONLY = [
    'git-upload-pack',
    'git upload-pack',
    'git-upload-archive',
    'git upload-archive',
    ]

COMMANDS_WRITE = [
    'git-receive-pack',
    'git receive-pack',
    ]

class ServingError(Exception):
    """Serving error"""

    def __str__(self):
        return '%s' % self.__doc__

class CommandMayNotContainNewlineError(ServingError):
    """Command may not contain newline"""

class UnknownCommandError(ServingError):
    """Unknown command denied"""

class CommandTooLongError(ServingError):
    """Command malformed - too many args"""

class UnsafeArgumentsError(ServingError):
    """Arguments to command look dangerous"""

class AccessDenied(ServingError):
    """Access denied to repository"""

class WriteAccessDenied(AccessDenied):
    """Repository write access denied"""

class ReadAccessDenied(AccessDenied):
    """Repository read access denied"""

def serve(
    cfg,
    user,
    command,
    ):
    if '\n' in command:
        raise CommandMayNotContainNewlineError()

    try:
        verb, args = command.split(None, 1)
    except ValueError:
        # all known "git-foo" commands take one argument; improve
        # if/when needed
        raise CommandTooLongError()

    if verb == 'git':
        try:
            subverb, args = args.split(None, 1)
        except ValueError:
            # all known "git foo" commands take one argument; improve
            # if/when needed
            raise CommandTooLongError()
        verb = '%s %s' % (verb, subverb)

    if (verb not in COMMANDS_WRITE
        and verb not in COMMANDS_READONLY):
        raise UnknownCommandError()

    match = ALLOW_RE.match(args)
    if match is None:
        raise UnsafeArgumentsError()

    path = match.group('path')

    # write access is always sufficient
    newpath = access.haveAccess(
        config=cfg,
        user=user,
        mode='writable',
        path=path)

    if newpath is None:
        # didn't have write access; try once more with the popular
        # misspelling
        newpath = access.haveAccess(
            config=cfg,
            user=user,
            mode='writeable',
            path=path)
        if newpath is not None:
            log.warning(
                'Repository %r config has typo "writeable", '
                +'should be "writable"',
                path,
                )

    if newpath is None:
        # didn't have write access

        newpath = access.haveAccess(
            config=cfg,
            user=user,
            mode='readonly',
            path=path)

        if newpath is None:
            raise ReadAccessDenied()

        if verb in COMMANDS_WRITE:
            # didn't have write access and tried to write
            raise WriteAccessDenied()

    (topdir, relpath) = newpath
    assert not relpath.endswith('.git'), \
           'git extension should have been stripped: %r' % relpath
    repopath = '%s.git' % relpath
    fullpath = os.path.join(topdir, repopath)
    if verb in COMMANDS_WRITE and not os.path.exists(fullpath):
        # IFF:
        # 1. it doesn't exist on the filesystem
        # 2. the configuration refers to it
        # 3. we're serving a write request
        # 4. and the user is authorized to do that:
        # THEN:
        # create the repository on the fly

        # create leading directories
        p = topdir
        for segment in repopath.split(os.sep)[:-1]:
            p = os.path.join(p, segment)
            util.mkdir(p, 0751)

        repository.init(path=fullpath)
        gitweb.set_descriptions(
            config=cfg,
            )
        generated = util.getGeneratedFilesDir(config=cfg)
        gitweb.generate_project_list(
            config=cfg,
            path=os.path.join(generated, 'projects.list'),
            )
        gitdaemon.set_export_ok(
            config=cfg,
            )

        try:
            post_init_hook = cfg.get('hooks', 'post-init')
            log.info ('Running post-init hook %s for new repository' % post_init_hook)
            returncode = subprocess.call(
                args=[ post_init_hook, repopath ],
                stdout=sys.stderr
                )
            if returncode != 0:
                raise GitInitError('exit status %d from post-init hook %s' % (returncode, post_init_hook))

        except (NoSectionError, NoOptionError):
            pass

    # put the verb back together with the new path
    newcmd = "%(verb)s '%(path)s'" % dict(
        verb=verb,
        path=fullpath,
        )
    return newcmd

class Main(app.App):
    def create_parser(self):
        parser = super(Main, self).create_parser()
        parser.set_usage('%prog [OPTS] USER')
        parser.set_description(
            'Allow restricted git operations under DIR')
        return parser

    def handle_args(self, parser, cfg, options, args):
        try:
            (user,) = args
        except ValueError:
            parser.error('Missing argument USER.')

        main_log = logging.getLogger('gitosis.serve.main')
        os.umask(0022)

        cmd = os.environ.get('SSH_ORIGINAL_COMMAND', None)
        if cmd is None:
            main_log.error('Need SSH_ORIGINAL_COMMAND in environment.')
            sys.exit(1)

        main_log.debug('Got command %(cmd)r' % dict(
            cmd=cmd,
            ))

        os.chdir(os.path.expanduser('~'))

        try:
            newcmd = serve(
                cfg=cfg,
                user=user,
                command=cmd,
                )
        except ServingError, e:
            main_log.error('%s', e)
            sys.exit(1)

        main_log.debug('Serving %s', newcmd)
        os.execvp('git', ['git', 'shell', '-c', newcmd])
        main_log.error('Cannot execute git-shell.')
        sys.exit(1)

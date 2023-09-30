'''Shell-like DSL for subprocess.Popen calls.

Usage:
    [Sh.pipe(INFILE) |] Sh(CMD) [| CMD]... [(>|>>) FILE]

INFILE is:
* file like object
* filename
* iterable
* string content, if wrapped in iterable, see Sh.Stdin

CMD is one of:
* Sh('ls', '-la')
* 'ls -la'
* ['ls, '-la']

FILE is:
* file like object
* filename

All arguments (CMD, FILE, INFILE) may contain special characters for expansion
such as `~?*!` and environment variables such as `$HOME`.

Gotchas:

*Evaluation means execution.* If a command is not evaluated it is not run. A
command is evaluated when its returncode is checked (truth evaluation), string
evaluation, or iteration.

*One shot.* Commands can't be piped or redirected after evaluation. That would
require a new run, which is achievable through the reset function. The reset
function will kill currently running command in the chain if needed. Reset may
be called during iteration, to abort the command.

*Expand per default.* Sometimes you want to avoid expansion, be careful with
'grep' in particular. Example: Sh('cat ~/.bashrc') | Sh('grep .*').expand(False)

*Splitting.* Input a single string and it gets split with shlex.split, to avoid
that, pass in a list instead. Example: Sh(['/path with spaces/script', 'arg'])

*Pythonic chain.* When you want the returncode and don't want to have to wrap
the expression in parenthesis, use .Sh and/or .redirect method. Example:
   res = Sh.pipe('~/.bashrc').Sh('grep ^PATH').redirect('~/path.txt').returncode

'''

import os
import subprocess
import glob
import itertools
import shlex
import sys
import fcntl
import select
import signal
from itertools import chain, islice


class Sh(object):
    debug = False
    set_sigchld_handler = False

    def __repr__(self):
        res = []
        t = self
        while t._output is not None:
            t = t._output
        while t is not None:
            res.append(t._repr())
            t = t._input
        return ' | '.join(res[::-1])

    def _repr(self):
        c = [repr(self._cmd)] + [repr(arg) for arg in self._args]
        res = ['Sh(' + ', '.join(c) + ')']
        if self._cwd:
            res.append('chdir(%r)' % self._cwd)
        if self._original_env:
            res.append('env(' + ', '.join(['%s:%r' % (k, v) for k, v in self._original_env.iteritems()]) + ')')
        if self._err_to_out:
            res.append('err_to_out()')
        if self._stdin:
            res.append('stdin(%r)' % (getattr(self._stdin, 'name', self._stdin)))
        return '.'.join(res)

    @staticmethod
    def make_sh(cmd):
        if type(cmd) in (str, unicode):
            cmd = shlex.split(cmd)
        if not type(cmd) is Sh:
            cmd = Sh(*cmd)
        return cmd

    def __init__(self, *cmd):
        self._stdin = None
        self._input = None
        self._output = None
        self._env = None
        self._err_to_out = False
        self._cwd = None
        self._pop = None
        self._expand = True
        self._original_cmd = cmd
        self._original_env = None
        self.expand(True)
        if self.debug:
            print "*** DEBUG: Sh(%r, %r)" % (self._cmd, self._args)
        if Sh.set_sigchld_handler:
            # Prevent Zombies from taking over the world
            signal.signal(signal.SIGCHLD, Sh.sigchld_handler)
            Sh.set_sigchld_handler = False

    def env(self, **kw):
        '''
        Allows adding/overriding env vars in the execution context.
        :param kw: Key-value pairs
        :return: self
        '''
        self._original_env = kw
        if self._env is None:
            self._env = dict(os.environ)
        self._env.update({k: unicode(v) for k, v in kw.iteritems()})
        return self

    def chdir(self, chdir):
        '''
        Changes the current working directory in the execution context.
        :param chdir: Any directory
        :return: self
        '''
        self._cwd = chdir
        return self

    def expand(self, expand):
        '''
        Turn off argument expansion, useful for 'grep'. Example:

            Sh('grep .*').expand(False) > 'tango'

        :param expand: True or False
        :return: self
        '''
        self._expand = expand
        cmd = self._original_cmd
        if len(cmd) == 1:
            if not type(cmd[0]) in (str, unicode):
                cmd = cmd[0]
            else:
                cmd = shlex.split(cmd[0])
        cmd = [os.path.expanduser(os.path.expandvars(arg)) for arg in cmd]
        self._cmd, self._args = cmd[0], cmd[1:]
        return self

    @property
    def include_stderr(self):
        '''
        Redirects stderr output to stdout so that stdout includes stderr
        content as well.
        :return: self
        '''
        self._err_to_out = True
        return self

    @property
    def returncode(self):
        '''
        Runs the command if it has not yet run (redirecting output to stdout).
        :return: The returncode of the last executed command in the chain.
        '''
        if not self._pop:
            self > sys.stdout
        link = self
        while link is not None:
            if link._pop:
                return link._pop.returncode
        return None

    def reset(self):
        '''
        Allows you to re-run the command chain.
        :return: self
        '''
        t = self
        while t._output is not None:
            t = t._output
        while t is not None:
            if t._pop and t._pop.returncode is None:
                t._pop.kill()
                t._pop.wait()
            del t._pop
            t._pop = None
            t = t._input
        return self

    def __del__(self):
        try:
            self.reset()
        except OSError:
            pass
        except IOError:
            pass

    def __bool__(self):
        return self.returncode == 0

    __nonzero__ = __bool__

    def __gt__(self, outfile):
        '''
        Writes stdout of the command into outfile.
        :param outfile: Filename or file-like object for writing.
        :return: The returncode
        '''
        if self.debug:
            print "(%s) > (%s)" % (self._original_cmd, outfile)
        assert self._pop is None, "*** ERROR: Command has already run and is now immutable."
        self._stream_out(outfile)
        return self

    def redirect(self, outfile):
        '''
        For chaining without parenthesis.

        Example:
            res=Sh.pipe('~/.bashrc').Sh('grep ^PATH').redirect('~/path.txt').returncode

        :param outfile: See __gt__
        :return: self
        '''
        return self > outfile

    def __rshift__(self, outfile):
        '''
        Appends stdout of the command into outfile.
        :param outfile: Filename or file-like object for writing.
        :return: The returncode
        '''
        assert self._pop is None, "*** ERROR: Command has already run and is now immutable."
        self._stream_out(outfile, True)
        return self

    def __or__(self, cmd):
        '''
        Pipes the output of this command into cmd.
        :param cmd: String, iterable or Sh object
        :return:
        '''
        assert self._pop is None, "*** ERROR: Command has already run and is now immutable."
        cmd = Sh.make_sh(cmd)
        self._append(cmd)
        return cmd

    def Sh(self, *cmd):
        '''
        Equivalent to using the |-operator.

        Example:
            if (Sh('ls') | 'wc').returncode:
                print "Good"
            if Sh('ls').Sh('wc').returncode:
                print "Good"

        :param cmd: See __or__
        :return: Chained command, see __or__
        '''
        return self | cmd

    def __iter__(self):
        '''
        :return: Lines as they arrive, if line is incomplete, it is not
        newline terminated, please make sure to test for that.
        '''
        self._run()
        fd = self._pop.stdout
        # Make sure file doesn't block, so we can do .read()
        fcntl.fcntl(fd, fcntl.F_SETFL, fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)
        fds = [fd]

        while True:
            try:
                ready, _, _ = select.select(fds, [], [])
            except select.error, e:
                if e.args == (4, 'Interrupted system call'):
                    continue
                raise
            ready = ready[-1]
            data = ready.read()
            if not data:
                break
            data = data.split('\n')
            while len(data) > 1:
                yield data.pop(0) + '\n'
            if data[0]:
                yield data[0]
        self._pop.wait()

    def wait(self):
        '''
        Causes the command chain to run.
        :return: self.returncode
        '''
        return self.returncode

    def communicate(self):
        '''
        Similar to Popen.communicate it returns the stdout and stderr content.
        :return:(stdout, stderr)
        '''
        self._run()
        return self._pop.communicate()

    def read(self):
        '''
        Runs the command and reads all stdout.
        :return: All stdout as a single string.
        '''
        stdout, _ = self.communicate()
        return stdout

    __str__ = read

    def readlines(self):
        '''
        Runs the command and reads all stdout into a list.
        :return: All stdout as a list of newline terminated strings.
        '''
        return self.read().splitlines(True)

    def _append(self, sh):
        '''
        Internal. Chains a command after this.
        :param sh: Next command.
        '''
        sh._input = self
        self._output = sh
        if self._env:
            sh._env = dict(self._env)
        if self._cwd:
            sh._cwd = self._cwd

    def _run(self, stdout=subprocess.PIPE):
        '''
        Internal. Starts running this command and those before it. Can only
        be called once.
        :param stdout: Where to send stdout for this link in the chain.
        '''
        assert self._pop is None
        if self._input is not None:
            self._input._run()

        cwd = (self._cwd if self._cwd else os.getcwd()) + '/'

        def glob_or(expr):
            res = [expr]
            if self._expand and ('*' in expr or '?' in expr):
                if expr and expr[0] != '/':
                    expr = cwd + expr
                res = glob.glob(expr)
                if not res:
                    res = [expr]
            return res

        args = [glob_or(arg) for arg in self._args]
        stderr = subprocess.STDOUT if self._err_to_out else None
        assert not self._stdin or self._input is None, "*** ERROR: Stdin must be none outside of head of chain."
        stdin = self._stdin if self._input is None else self._input._pop.stdout
        if stdin is not None and getattr(stdin, 'fileno', None) is None:
            stdin = subprocess.PIPE
        cmd = [self._cmd] + list(itertools.chain.from_iterable(args))
        if self.debug:
            print "*** DEBUG: Run", cmd
        try:
            self._pop = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr,
                                         close_fds=True, cwd=self._cwd, env=self._env)
            if stdin == subprocess.PIPE:
                try:
                    # TODO: Write a non-blocking reader-writer to ship data here
                    self._pop.stdin.write(self._stdin.read())
                except AttributeError:
                    self._pop.stdin.write(self._stdin)
        except OSError:
            print "*** ERROR: %r failed at %r" % (self, self._original_cmd)
            raise

    def _stream_out(self, outfile, append=False):
        '''
        Internal. Writes all stdout into outfile.
        :param outfile: Filename or file-like object for writing.
        :param append: Opens filename with append.
        :return: This command's returncode.
        '''
        if type(outfile) in (str, unicode):
            outfile = os.path.expanduser(os.path.expandvars(outfile))
            outfile = open(outfile, 'a' if append else 'w')
        self._run(outfile)
        self._pop.wait()

    @classmethod
    def pipe(cls, input):
        '''
        Creates a stdin source for Sh object chains.
        :param input: If string; open as filename, if iterable, send iterated content into next command,
        if none of the above assume file like object.

        To input a string as content source, wrap in iterable:

        print 'Lines in "my_input_string":', Sh.pipe([my_string_input]) | 'wc -l'
        :return: Stdin object for chaining Sh commands after.

        WARNING: If iterable is an endless generator command evaluation will never complete.
        '''
        if type(input) in (str, unicode):
            return cls.Stdin.from_file(input)
        try:
            return cls.Stdin.from_iterator(iter(input))
        except TypeError:
            pass
        return cls.Stdin.from_file(input)

    @staticmethod
    def sigchld_handler(signal, frame):
        try:
            while True:
                pid, returncode = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
        except OSError:
            pass
        except IOError:
            pass


    class Stdin(object):
        '''
        A wrapper class that provides the pipe syntax to lead into Sh object, such as:

            Stdin.from_file(filename) | 'sort' | 'uniq'
        '''

        class FileFromIterator(object):
            '''
            Converts an iterator into a file like object.
            '''

            def __init__(self, src):
                self._src = chain.from_iterable(src)

            def read(self, n=None):
                if n is None:
                    return "".join(self._src)
                return "".join(islice(self._src, None, n))

        def __init__(self, infile):
            '''
            Takes a file like object as input for a subsequent Sh command.
            :param infile: File like object
            '''
            self._infile = infile

        def __or__(self, cmd):
            sh = Sh.make_sh(cmd)
            assert sh._pop is None, "*** ERROR: Command has already run and is now immutable."
            sh._stdin = self._infile
            return sh

        def Sh(self, *cmd):
            'See Sh.Sh'
            return self | cmd

        @classmethod
        def from_file(cls, infile):
            '''
            :param infile: Filename or file like object
            :return: Stdin object
            '''
            if type(infile) in (str, unicode):
                infile = open(os.path.expanduser(os.path.expandvars(infile)))
            return cls(infile)

        @classmethod
        def from_iterator(cls, inlines):
            '''
            :param inlines: An iterable that produces string-like objects for piping to Sh commands.
            :return:
            '''
            return cls(cls.FileFromIterator(inlines))

        @classmethod
        def from_string(cls, instring):
            return cls(instring)

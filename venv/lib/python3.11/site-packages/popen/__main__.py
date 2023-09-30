'''
This module serves not purpose besides being a testing crutch for me
as I develop popen.
'''
from . import Sh
from StringIO import StringIO

if __name__ == '__main__':
    # This is a test
    Sh.debug = True
    print Sh('w')
    if Sh('ls') | 'sort':
        print "OK"
    if Sh('make').include_stderr | 'wc':
        print "OK"
    Sh('ls') > '~/listing.txt'
    (Sh.pipe('~/listing.txt') | Sh('wc')).returncode
    for line in Sh('ls', '-la', '~'):
        print "GOT", line
    print "OK", Sh.pipe('~/listing.txt').Sh('grep', '-q', 'code').returncode
    print Sh('ls', '$USER', '~/*'), Sh('echo "hole in one"')
    Sh('ls', '-l') | ['wc', '-l'] > '/dev/null'
    for line in Sh('du', '~/') | 'head -n 10' | 'sort -n':
        print('GOT', line)

    Sh('ls') > 'polka list'
    print Sh('cat', '*py').Sh('wc').returncode
    print (Sh.pipe('polka list') | 'wc').returncode

    open('test script.sh', 'w').write('''#!/bin/bash
echo "Running"''')
    Sh(['chmod', 'a+x', 'test script.sh']).returncode
    if str(Sh(['./test script.sh'])) == 'Running\n':
        print "OK"
    if Sh.pipe('polka list') | Sh('wc') | 'fmt -1' > 'tango':
        print open('tango').read()
        Sh('rm tango').returncode

    s = Sh('ls') | ['grep', 'blt'] | 'wc "-l"'
    print s, s.returncode

    print "OK", Sh('ls').read()
    print "OK", Sh('ls').readlines()

    print "EXPAND", Sh('ls') | Sh('grep', r'~a.*$').expand(False)
    if Sh(['rm', 'polka list', 'test script.sh', '~/listing.txt']):
        print "DONE"

    print Sh.Stdin.from_string('''Look
    no hands''') | Sh('wc')
    buf = StringIO()
    buf.write('''Look
    no hands''')
    buf.seek(0)
    print Sh.pipe(buf) | Sh('wc')
    print Sh.pipe(['''Look
    no hands''']) | Sh('wc')

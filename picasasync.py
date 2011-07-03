#!/usr/bin/env python3.2

import sys
import os
import argparse
from subprocess import check_output

googleclcmd = "google"
# case insensitive:
allowed_extensions = ['jpg', 'jpeg', 'png']

class Printer(object):
    """
    Printing class
    """
    
    def __init__(self, verbose=False):
        """
        """
        self.p = self.nuthing
        if verbose:
            self.p = self.printme

    def nuthing(self, txt):
        return

    def printme(self, txt):
        print(" ::", txt)

# an instance to work with in other classes
printer = Printer()

# Little helper utility from
# http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python/377028#377028
def which(program):
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None

class GoogleCLHelper(object):
    """
    Helper class for interacting with googlecl
    """
    albums = None
    
    def __init__(self):
        self.cmd = which(googleclcmd)
        if self.cmd is None:
            print("Can't find `%s' in your PATH. Please install googlecl from http://code.google.com/p/googlecl/"
                    % googleclcmd)
            raise PicasaSyncException()
        else:
            printer.p ("googlecl command: %s" % self.cmd)


    def run_picasa_cmd(self, *args):
        'helper to run "google picasa <cmd>"'
        return check_output([googleclcmd, "picasa"] + list(args))

    def get_picasa_albums(self):
        """
        Gets a list of all picasa web albums. This will be cached each
        session. The user will have to authenticate if they haven't in
        the past. returns a 2-tuple of (album_names, url)
        """
        if self.albums is None:
            printer.p("getting remote album list")
            retval = self.run_picasa_cmd("list-albums")
            self.albums = [a.split(',') for a in retval.decode('ascii').split('\n')]
            while [''] in self.albums:
                self.albums.remove([''])

        return ([a[0] for a in self.albums], [a[1] for a in self.albums])

    def get_picasa_album_listing(self, album):
        "get album listing. caching is not used. returns a 2-tuple with (filenames, urls)"
        if album not in self.get_picasa_albums()[0]:
            return None

        retval = self.run_picasa_cmd("list", album)
        l = [a.split(',') for a in retval.decode('ascii').split('\n')]
        try:
            l.remove([''])
        except:
            pass
        return ([a[0] for a in l], [a[1] for a in l])

    def upload_file_to_picasa_album(self, remote_album, f):
        if remote_album not in self.get_picasa_albums()[0]:
            print("Couldn't upload %s: Remote album %s does not exist"
                  % (f, remote_album))
            raise PicasaSyncException()
        self.run_picasa_cmd("post", "--title", remote_album, "--src", f)


class PicasaSync(object):
    """
    Sync directories with picasa
    """

    upload_queue = []
    
    def __init__(self, local, remote, dry_run=False):
        self.dry_run = dry_run
        self.cl = GoogleCLHelper()

        # set up and validate the local path:
        self.local = local
        if not os.path.exists(self.local):
            print ("That local path doesn't appear to exist...")
            raise PicasaSyncException()
        if not os.path.isdir(self.local):
            print ("local path must be a directory.")
            raise PicasaSyncException()
        self.local_full = os.path.abspath(self.local)
        printer.p("local dir: %s" % self.local_full)

        # set up and validate the remote album:
        self.remote = remote
        albums = self.cl.get_picasa_albums()[0]
        if albums is None:
            print("Couldn't find any remote albums... You might need to go create one first.")
            raise PicasaSyncException()
        if self.remote not in albums:
            print("That remote album was not found. Your remote albums:")
            print("\n".join(albums))
            raise PicasaSyncException()
        else:
            printer.p("Using remote album %s" % self.remote)

    def run(self):
        print ("syncing local directory `%s' to album `%s'" % (self.local, self.remote))
        remote_files_in_album = self.cl.get_picasa_album_listing(self.remote)[0]
        ext_skip_cnt = 0
        ja_skip_cnt = 0
        for (dirpath, dirnames, filenames) in os.walk(self.local_full):
            for f in filenames:
                fullfilename = os.path.join(dirpath, f)
                extension = os.path.splitext(fullfilename)[1][1:].lower()
                if extension not in allowed_extensions:
                    printer.p("skipping %s because its extension (%s) isn't one of (%s)"
                              % (fullfilename, extension, ', '.join(allowed_extensions)))
                    ext_skip_cnt += 1
                    continue
                if f in remote_files_in_album:
                    printer.p("%s is already in %s" % (f, self.remote))
                    ja_skip_cnt += 1
                    continue

                self.add_to_upload_queue(self.remote, fullfilename)

        print("Queue'd up %d files for upload"
              % len(self.upload_queue))
        print("skipped %d due to invalid extension" % ext_skip_cnt)
        print("skipped %d because they already exist in the remote album" % ja_skip_cnt)
        self.upload_everything_in_queue()

    def add_to_upload_queue(self, remote_album, fullpathtofile):
        self.upload_queue.append((remote_album, fullpathtofile))

    def upload_everything_in_queue(self):
        print("Now uploading %d items..." % len(self.upload_queue))
        for (cnt,f) in enumerate(self.upload_queue[:]):
            if self.dry_run:
                print('dry run: %s to %s' % (f[1], f[0]))
            else:
                print("%d/%d" % (cnt+1, len(self.upload_queue)))
                self.cl.upload_file_to_picasa_album(*f)

class PicasaSyncException(BaseException):
    pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=PicasaSync.__doc__,
                                     epilog="by Mitchel Humpherys <mitch.special@gmail.com>")
    parser.add_argument('local', help="Local directory you'd like to sync")
    parser.add_argument('remote', help="Remote album to which you'd like to sync")
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help="Only print what we would sync, don't actually sync")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Be verbose")

    args = parser.parse_args()

    printer = Printer(args.verbose)

    try:
        ps=PicasaSync(args.local, args.remote, dry_run=args.dry_run)
    except PicasaSyncException:
        print("Error...")
    except:
        raise
    else:
        ps.run()
        
    

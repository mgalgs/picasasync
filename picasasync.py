#!/usr/bin/env python3.2

# Sync local directories with picasa albums online. Since the gdata
# python bindings don't support py3k yet, this script calls the
# `google' utility (googlecl) rather than using the gdata library
# directly.

import sys
import os
import argparse
import subprocess

googleclcmd = "google"
# case insensitive:
allowed_extensions = ['jpg', 'jpeg', 'png']
# can only store this many files in remote albums:
NUM_REMOTE_FILES_IN_ALBUM = 1000

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
    dry_run = False
    
    def __init__(self, dry_run=False):
        """
        Arguments:
        - `dry_run`: set dry_run=True to prevent uploads (new albums will still be created)
        """
        self.cmd = which(googleclcmd)
        self.dry_run = dry_run
        if self.cmd is None:
            raise PicasaSyncError("Can't find `%s' in your PATH. Please install googlecl from http://code.google.com/p/googlecl/"
                    % googleclcmd)
        else:
            printer.p ("googlecl command: %s" % self.cmd)

        # See if they have given `google' authorization before:
        print("Checking picasa authorization...")


    def run_picasa_cmd(self, *args):
        'helper to run "google picasa <cmd>"'
        return subprocess.check_output([googleclcmd, "picasa"] + list(args))

    def get_picasa_albums(self, force=False):
        """
        Gets a list of all picasa web albums. This will be cached each
        session. Pass force=True to bypass cache. The user will have
        to authenticate if they haven't in the past. returns a 2-tuple
        of (album_names, url)
        """
        if force:
            self.albums = None

        if self.albums is None:
            p = subprocess.Popen(["google", "picasa", "list-albums"],
                                 stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            (mstdout, mstderr) = p.communicate(b"stuff")
            if "Please log in" in mstdout.decode('ascii'):
                raise PicasaSyncError("""It looks like you've never used googlecl before... Please run the command\n
\t{0:s} picasa list\n
from the command line and follow the instructions to authorize `{0:s}' on this computer""".format(googleclcmd))

            retval = mstdout
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
            raise PicasaSyncError("Couldn't upload %s: Remote album %s does not exist"
                  % (f, remote_album))
        if self.dry_run:
            print ("dry run: would upload %s to %s" % (f, remote_album))
        else:
            self.run_picasa_cmd("post", "--title", remote_album, "--src", f)

    def create_album(self, album):
        "create a picasa album"
        self.run_picasa_cmd("create", album)


class PicasaSync(object):
    """
    Sync local directories with picasa
    """

    upload_queue = []
    
    def __init__(self, local, remotes, dry_run=False, create_needed=False):
        self.create_needed = create_needed
        self.cl = GoogleCLHelper(dry_run=dry_run)

        # set up and validate the local path:
        self.local = local
        if not os.path.exists(self.local):
            raise PicasaSyncError("That local path doesn't appear to exist...")
        if not os.path.isdir(self.local):
            raise PicasaSyncError("local path must be a directory.")
        self.local_full = os.path.abspath(self.local)
        printer.p("local dir: %s" % self.local_full)

        # set up and validate the remote album:
        self.remotes = remotes
        albums = self.cl.get_picasa_albums()[0]
        if albums is None:
            raise PicasaSyncError("Couldn't find any remote albums... You might need to go create one first.")
        for remote in self.remotes:
            if remote not in albums:
                if create_needed:
                    print('Creating album %s' % remote)
                    self.cl.create_album(remote)
                    albums = self.cl.get_picasa_albums(force = True)[0]
                else:
                    raise PicasaSyncError("""The remote album %s was not found. Your remote albums:
%s
Alternatively, you can use the -c option to automatically create any albums that don't exist"""
                      % (remote, "\n".join(albums)))

        printer.p("Using remote albums: %s" % ', '.join(self.remotes))
        # eo __init__

    def run(self):
        # the files we would like to upload
        files = []
        print('Getting list of files under %s...' % self.local)
        for (dirpath, dirnames, filenames) in os.walk(self.local_full):
            for f in filenames:
                fullfilename = os.path.join(dirpath, f)
                files.append(fullfilename)

        # all files in all remote albums:
        remotefiles = []
        remoteinfo = {}
        for remote in self.remotes:
            print('Getting remote listing of picasa album %s...' % remote)
            remote_files_in_album = self.cl.get_picasa_album_listing(remote)[0]
            remotefiles += remote_files_in_album
            remoteinfo[remote] = {'remotefiles': remote_files_in_album}


        remoteiter = iter(self.remotes)
        current_remote = next(remoteiter)
        ext_skip_cnt = 0
        ja_skip_cnt = 0
        for f in files:
            extension = os.path.splitext(f)[1][1:].lower()
            basename = os.path.split(f)[1]
            if extension not in allowed_extensions:
                printer.p("skipping %s because its extension (%s) isn't one of (%s)"
                          % (f, extension, ', '.join(allowed_extensions)))
                ext_skip_cnt += 1
                continue
            if basename in remotefiles:
                printer.p("%s is already in one of the remote albums" % f)
                ja_skip_cnt += 1
                continue

            if len(remoteinfo[current_remote]['remotefiles']) >= NUM_REMOTE_FILES_IN_ALBUM:
                try:
                    current_remote = next(remoteiter)
                except StopIteration:
                    raise PicasaSyncError("""Not enough room in those picasa albums to store all of those photos...
You are trying to upload {0:,d} files but each picasa album can only store 1,000
photos (and the provided albums already contain {1:,d} photos).""".format(len(files), len(remotefiles)))


            remoteinfo[current_remote]['remotefiles'].append(basename)
            self.add_to_upload_queue(current_remote, f)


        print("Queue'd up %d files for upload"
              % len(self.upload_queue))
        print("skipped %d photos due to invalid extension" % ext_skip_cnt)
        print("skipped %d photos because they already exist in the remote albums" % ja_skip_cnt)
        self.upload_everything_in_queue()

        # eo run

    def add_to_upload_queue(self, remote_album, fullpathtofile):
        self.upload_queue.append((remote_album, fullpathtofile))

    def upload_everything_in_queue(self):
        print("Now uploading %d items..." % len(self.upload_queue))
        for (cnt,f) in enumerate(self.upload_queue[:]):
            print("%d/%d" % (cnt+1, len(self.upload_queue)))
            self.cl.upload_file_to_picasa_album(*f)
        # eo upload_everything_in_queue

class PicasaSyncError(BaseException):
    quiet = False
    value = None
    def __init__(self, value, quiet=False):
        """        
        Arguments:
        - `quiet`: Whether or not we should print 'Error...' to the output
        """
        self.value = value
        self.quiet = quiet



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=PicasaSync.__doc__,
                                     epilog="by Mitchel Humpherys <mitch.special@gmail.com>")
    parser.add_argument('local', help="Local directory you'd like to sync")
    parser.add_argument('remote', nargs="+",
                        help="""Remote album(s) to which you'd like to sync.
                        (Note, each remote album can only hold up to 1,000 photos, so if you
                        will be uploading more than this you should supply several albums here)""")
    parser.add_argument('-d', '--dry-run', action='store_true',
                        help="Only print what we would sync, don't actually sync")
    parser.add_argument('-c', action='store_true', dest='create_needed',
                        help="Create albums that don't exist")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Be verbose")

    args = parser.parse_args()

    printer = Printer(args.verbose)

    try:
        PicasaSync(args.local, args.remote, dry_run=args.dry_run, create_needed=args.create_needed).run()
    except PicasaSyncError as e:
        if not e.quiet:
            print('\nError:')
            print(e.value)
            print("Exiting...")
    except:
        print('unhandled crappiness')
        raise
        
    

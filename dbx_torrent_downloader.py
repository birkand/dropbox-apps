"""Upload the contents of your Downloads folder to Dropbox.
This is an example app for API v2.
"""

from __future__ import print_function

import argparse
import contextlib
import datetime
import os
import six
import sys
import time
import unicodedata

if sys.version.startswith('2'):
    input = raw_input  # noqa: E501,F821; pylint: disable=redefined-builtin,undefined-variable,useless-suppression

import dropbox

# OAuth2 access token.  TODO: login etc.
TOKEN = ''

parser = argparse.ArgumentParser(description='Download new torrents from Dropbox')
parser.add_argument('folder', nargs='?', 
    # default='/undefined',
                    help='Folder name in your Dropbox')
# parser.add_argument('rootdir', nargs='?', default='~/birkan-app',
parser.add_argument('rootdir', nargs='?', default='/undefined',
                    help='Local directory to download')
parser.add_argument('--token', default=TOKEN,
                    help='Access token '
                    '(see https://www.dropbox.com/developers/apps)')
parser.add_argument('--yes', '-y', action='store_true',
                    help='Answer yes to all questions')
parser.add_argument('--no', '-n', action='store_true',
                    help='Answer no to all questions')
parser.add_argument('--default', '-d', action='store_true',
                    help='Take default answer on all questions')

def main():
    """Main program.
    Parse command line, then iterate over files and directories under
    rootdir and upload all files.  Skips some temporary files and
    directories, and avoids duplicate uploads by comparing size and
    mtime with the server.
    """
    args = parser.parse_args()
    if sum([bool(b) for b in (args.yes, args.no, args.default)]) > 1:
        print('At most one of --yes, --no, --default is allowed')
        sys.exit(2)
    if not args.token:
        print('--token is mandatory')
        sys.exit(2)

    dbx_folder = args.folder
    rootdir = os.path.expanduser(args.rootdir)
    print('Dropbox folder name:', dbx_folder)
    print('Local directory:', rootdir)
    if not os.path.exists(rootdir):
        print(rootdir, 'does not exist on your filesystem')
        sys.exit(1)
    elif not os.path.isdir(rootdir):
        print(rootdir, 'is not a folder on your filesystem')
        sys.exit(1)

    dbx = dropbox.Dropbox(args.token)

    subfolder = ''
    sync_folder(dbx, dbx_folder, subfolder, rootdir)


         
            

def sync_folder(dbx, dbx_folder, subfolder, rootdir, recursive=True, mirror=True):
    #print(list_folder(dbx, dbx_folder, subfolder))
    print("\n")
    print('listing dbx_folder:', dbx_folder, 'subfolder:', subfolder)
    local_dir = os.path.join(rootdir, subfolder)
    listing = list_folder(dbx, dbx_folder, subfolder)
    dirs = []
    for name in listing:
        print('name:', name)
        md = listing[name]
        #print('md:', md)
        local_path = os.path.join(local_dir,name)
        local_done_path = os.path.join(local_dir, 'done', name)
        print('local_path', local_path)
        path_exists = os.path.exists(local_path)
        done_path_exists = os.path.exists(local_done_path)
        print('local path exists:', path_exists)
        if isinstance(md, dropbox.files.FileMetadata):
            if not path_exists:
                if not done_path_exists:
                    with stopwatch('download'):
                        try:
                            md, res = dbx.files_download(md.path_display)
                            with open(local_path, 'w') as f:
                                f.write(res.content)
                                print('saved file:', local_path)
                        except dropbox.exceptions.HttpError as err:
                            print('*** HTTP error', err)
                            return None
                    data = res.content
                    print(len(data), 'bytes; md:', md)
                else:
                    print('already done at:', local_done_path)    
            print('remote is a file')
        elif isinstance(md, dropbox.files.FolderMetadata):
            print('remote is a folder')
            #TODO yesno include this dir?
            if not path_exists:
                os.mkdir(local_path)
                print('created dir:', local_path)
            dirs.append(name)
    print('dirs:', dirs)        
    for dir in dirs:
        sync_folder(dbx, os.path.join(dbx_folder,subfolder),dir, rootdir)

def list_folder(dbx, dbx_folder, subfolder):
    """List a folder.
    Return a dict mapping unicode filenames to
    FileMetadata|FolderMetadata entries.
    """
    path = '/%s/%s' % (dbx_folder, subfolder.replace(os.path.sep, '/'))
    while '//' in path:
        path = path.replace('//', '/')
    path = path.rstrip('/')
    try:
        with stopwatch('list_folder'):
            res = dbx.files_list_folder(path)
    except dropbox.exceptions.ApiError as err:
        print('Folder listing failed for', path, '-- assumed empty:', err)
        return {}
    else:
        rv = {}
        for entry in res.entries:
            rv[entry.name] = entry
        return rv

def download(dbx, dbx_folder, subfolder, name):
    """Download a file.
    Return the bytes of the file, or None if it doesn't exist.
    """
    path = '/%s/%s/%s' % (dbx_folder, subfolder.replace(os.path.sep, '/'), name)
    while '//' in path:
        path = path.replace('//', '/')
    with stopwatch('download'):
        try:
            md, res = dbx.files_download(path)
        except dropbox.exceptions.HttpError as err:
            print('*** HTTP error', err)
            return None
    data = res.content
    print(len(data), 'bytes; md:', md)
    return data

def upload(dbx, fullname, dbx_folder, subfolder, name, overwrite=False):
    """Upload a file.
    Return the request response, or None in case of error.
    """
    path = '/%s/%s/%s' % (dbx_folder, subfolder.replace(os.path.sep, '/'), name)
    while '//' in path:
        path = path.replace('//', '/')
    mode = (dropbox.files.WriteMode.overwrite
            if overwrite
            else dropbox.files.WriteMode.add)
    mtime = os.path.getmtime(fullname)
    with open(fullname, 'rb') as f:
        data = f.read()
    with stopwatch('upload %d bytes' % len(data)):
        try:
            res = dbx.files_upload(
                data, path, mode,
                client_modified=datetime.datetime(*time.gmtime(mtime)[:6]),
                mute=True)
        except dropbox.exceptions.ApiError as err:
            print('*** API error', err)
            return None
    print('uploaded as', res.name.encode('utf8'))
    return res

def yesno(message, default, args):
    """Handy helper function to ask a yes/no question.
    Command line arguments --yes or --no force the answer;
    --default to force the default answer.
    Otherwise a blank line returns the default, and answering
    y/yes or n/no returns True or False.
    Retry on unrecognized answer.
    Special answers:
    - q or quit exits the program
    - p or pdb invokes the debugger
    """
    if args.default:
        print(message + '? [auto]', 'Y' if default else 'N')
        return default
    if args.yes:
        print(message + '? [auto] YES')
        return True
    if args.no:
        print(message + '? [auto] NO')
        return False
    if default:
        message += '? [Y/n] '
    else:
        message += '? [N/y] '
    while True:
        answer = input(message).strip().lower()
        if not answer:
            return default
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no'):
            return False
        if answer in ('q', 'quit'):
            print('Exit')
            raise SystemExit(0)
        if answer in ('p', 'pdb'):
            import pdb
            pdb.set_trace()
        print('Please answer YES or NO.')

@contextlib.contextmanager
def stopwatch(message):
    """Context manager to print how long a block of code took."""
    t0 = time.time()
    try:
        yield
    finally:
        t1 = time.time()
        print('Total elapsed time for %s: %.3f' % (message, t1 - t0))

if __name__ == '__main__':
    main()

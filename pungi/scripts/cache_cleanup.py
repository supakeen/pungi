import argparse
import os
import re
import time

from pungi.util import format_size


LOCK_RE = re.compile(r".*\.lock(\|[A-Za-z0-9]+)*$")


def should_be_cleaned_up(path, st, threshold):
    if st.st_nlink == 1 and st.st_mtime < threshold:
        # No other instances, older than limit
        return True

    if LOCK_RE.match(path) and st.st_mtime < threshold:
        # Suspiciously old lock
        return True

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("CACHE_DIR")
    parser.add_argument("-n", "--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--max-age",
        help="how old files should be considered for deletion",
        default=7,
        type=int,
    )

    args = parser.parse_args()

    topdir = os.path.abspath(args.CACHE_DIR)
    max_age = args.max_age * 24 * 3600

    cleaned_up = 0

    threshold = time.time() - max_age
    for dirpath, dirnames, filenames in os.walk(topdir):
        for f in filenames:
            filepath = os.path.join(dirpath, f)
            st = os.stat(filepath)
            if should_be_cleaned_up(filepath, st, threshold):
                if args.verbose:
                    print("RM %s" % filepath)
                cleaned_up += st.st_size
                if not args.dry_run:
                    os.remove(filepath)
        if not dirnames and not filenames:
            if args.verbose:
                print("RMDIR %s" % dirpath)
            if not args.dry_run:
                os.rmdir(dirpath)

    if args.dry_run:
        print("Would reclaim %s bytes." % format_size(cleaned_up))
    else:
        print("Reclaimed %s bytes." % format_size(cleaned_up))

======================
Getting data from koji
======================

When Pungi is configured to get packages from a Koji tag, it somehow needs to
access the actual RPM files.

Historically, this required the storage used by Koji to be directly available
on the host where Pungi was running. This was usually achieved by using NFS for
the Koji volume, and mounting it on the compose host.

The compose could be created directly on the same volume. In such case the
packages would be hardlinked, significantly reducing space consumption.

The compose could also be created on a different storage, in which case the
packages would either need to be copied over or symlinked. Using symlinks
requires that anything that accesses the compose (e.g. a download server) would
also need to mount the Koji volume in the same location.

There is also a risk with symlinks that the package in Koji can change (due to
being resigned for example), which would invalidate composes linking to it.


Using Koji without direct mount
===============================

It is possible now to run a compose from a Koji tag without direct access to
Koji storage.

Pungi can download the packages over HTTP protocol, store them in a local
cache, and consume them from there. To enable this behavior, set the
:ref:`koji_cache <koji-settings>` option in the compose configuration.

The local cache has similar structure to what is on the Koji volume.

When Pungi needs some package, it has a path on Koji volume. It will replace
the ``topdir`` with the cache location. If such file exists, it will be used.
If it doesn't exist, it will be downloaded from Koji (by replacing the
``topdir`` with ``topurl``).

::

    Koji path                            /mnt/koji/packages/foo/1/1.fc38/data/signed/abcdef/noarch/foo-1-1.fc38.noarch.rpm
    Koji URL    https://kojipkgs.fedoraproject.org/packages/foo/1/1.fc38/data/signed/abcdef/noarch/foo-1-1.fc38.noarch.rpm
    Local path                  /mnt/compose/cache/packages/foo/1/1.fc38/data/signed/abcdef/noarch/foo-1-1.fc38.noarch.rpm

The packages can be hard- or softlinked from this cache directory
(``/mnt/compose/cache`` in the example).


Cleanup
-------

While the approach above allows each RPM to be downloaded only once, it will
eventually result in the Koji volume being mirrored locally. Most of the
packages will however no longer be needed.

There is a script ``pungi-cache-cleanup`` that can help with that. It can find
and remove files from the cache that are no longer needed.

A file is no longer needed if it has a single link (meaning it is only in the
cache, not in any compose), and it has mtime older than a given threshold.

It doesn't make sense to delete files that are hardlinked in an existing
compose as it would not save any space anyway.

The mtime check is meant to preserve files that are downloaded but not actually
used in a compose, like a subpackage that is not included in any variant. Every
time its existence in the local cache is checked, the mtime is updated.


Race conditions?
----------------

It should be safe to have multiple compose hosts share the same storage volume
for generated composes and local cache.

If a cache file is accessed and it exists, there's no risk of race condition.

If two composes need the same file at the same time and it is not present yet,
one of them will take a lock on it and start downloading. The other will wait
until the download is finished.

The lock is only valid for a set amount of time (5 minutes) to avoid issues
where the downloading process is killed in a way that blocks it from releasing
the lock.

If the file is large and network slow, the limit may not be enough finish
downloading. In that case the second process will steal the lock while the
first process is still downloading. This will result in the same file being
downloaded twice.

When the first process finishes the download, it will put the file into the
local cache location. When the second process finishes, it will atomically
replace it, but since it's the same file it will be the same file.

If the first compose already managed to hardlink the file before it gets
replaced, there will be two copies of the file present locally.


Integrity checking
------------------

There is minimal integrity checking. RPM packages belonging to real builds will
be check to match the checksum provided by Koji hub.

There is no checking for scratch builds or any images.

# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Utilities for image bundling tool."""

import logging
import os
import subprocess
import time
import urllib2

METADATA_URL_PREFIX = 'http://169.254.169.254/computeMetadata/'
METADATA_V1_URL_PREFIX = METADATA_URL_PREFIX + 'v1/'


class MakeFileSystemException(Exception):
  """Error occurred in file system creation."""


class TarAndGzipFileException(Exception):
  """Error occurred in creating the tarball."""


class LoadDiskImage(object):
  """Loads raw disk image using kpartx."""
 
  def __init__(self, file_path, part_offset = 1024*1024):
    """Initializes LoadDiskImage object.

    Args:
      file_path: a path to a file containing raw disk image.
      
      virtual_image: a boolean specifying whether the file is virtual image (not raw file) supported by qemu-img

    Returns:
      A list of devices for every partition found in an image.
    """
    self._file_path = file_path
    self._part_offset = part_offset
    self._base_loop = "";
    self._part_loop = "";

  def __enter__(self):
    """Map disk image as a device."""
    SyncFileSystem()

    mountpath = self._file_path
    offset = self._part_offset
    #create base loop for the whole file
    losetup_cmd = ['losetup' , "--show" , "-f" , self._file_path]
    output = RunCommand(losetup_cmd)
    if not "/dev/loop" in output:
        raise OSError("Unknown loop device is built")
    self._base_loop = str(output).strip()
    # create a loop for partition
    losetup_cmd = ['losetup' , '--offset' , str(offset) , "--show" , "-f" , self._base_loop]
    output = RunCommand(losetup_cmd)
    if not "/dev/loop" in output:
        raise OSError("Unknown loop device is built")
    self._part_loop = str(output).strip()

    #feoff: !kpartx is shit, grub doesn't work with it at all
    #kpartx_cmd = ['kpartx', '-a', '-v', '-s', mountpath]
    #output = RunCommand(kpartx_cmd)
    # 
    devs = [self._part_loop]
    #for line in output.splitlines():
    #  split_line = line.split()
    #  if (len(split_line) > 2 and split_line[0] == 'add'
    #      and split_line[1] == 'map'):
          #feoff: we add an extra loopdev here - sometimes grub won't install on /dev/mapper-like links for the uncertain reason 
          #self._loop_dev = RunCommand(["losetup" , '--show', '--find' , '/dev/mapper/' + split_line[2]])
          #self._loop_dev = str(self._loop_dev).strip()
          # try to do it without loop dev
    #      devs.append('/dev/mapper/' + split_line[2])
    #      self._loop_dev = ""
          #devs.append(self._loop_dev)
    #time.sleep(2)
    return devs

  def __exit__(self, unused_exc_type, unused_exc_value, unused_exc_tb):
    """Unmap disk image as a device.

    Args:
      unused_exc_type: unused.
      unused_exc_value: unused.
      unused_exc_tb: unused.
    """
    SyncFileSystem()
    time.sleep(2)

    if self._part_loop:
        try:
            RunCommand(["losetup" , '-d' , self._part_loop ])
        except Exception as e:
            logging.debug("Cannot detach, waiting for more 2 mins till sync is done")
            sleep(120)
            RunCommand(["losetup" , '-d' , self._part_loop ])

    time.sleep(2)

    if self._base_loop:
        RunCommand(["losetup" , '-d' , self._base_loop ])
    

  


class MountFileSystem(object):
  """Mounts a file system."""

  def __init__(self, dev_path, dir_path, fs_type):
    """Initializes MountFileSystem object.

    Args:
      dev_path: A path to a device to mount.
      dir_path: A path to a directory where a device is to be mounted.
    """
    self._dev_path = dev_path
    self._dir_path = dir_path
    self._fs_type = fs_type

  def __enter__(self):
    """Mounts a device.
    """
    # Since the bundled image can have the same uuid as the root disk,
    # we should prevent uuid conflicts for xfs mounts.
    if self._fs_type is 'xfs':
      mount_cmd = ['mount', '-o', 'nouuid', self._dev_path, self._dir_path]
    else:
      mount_cmd = ['mount', self._dev_path, self._dir_path]
    RunCommand(mount_cmd)

  def __exit__(self, unused_exc_type, unused_exc_value, unused_exc_tb):
    """Unmounts a file system.

    Args:
      unused_exc_type: unused.
      unused_exc_value: unused.
      unused_exc_tb: unused.
    """
    umount_cmd = ['umount', self._dir_path]
    RunCommand(umount_cmd)
    SyncFileSystem()


def SyncFileSystem():
  RunCommand(['sync'])

def GetMounts(root='/'):
  """Find all mount points under the specified root.

  Args:
    root: a path to look for a mount points.

  Returns:
    A list of mount points.
  """
  output = RunCommand(['mount', '-l'])
  mounts = []
  for line in output.splitlines():
    split_line = line.split()
    mount_point = split_line[2]
    if mount_point == root:
      continue
    # We are simply ignoring the fs_type of fs for now. But we can use that
    # later Just verify that these are actually mount points.
    if os.path.ismount(mount_point) and mount_point.startswith(root):
      mounts.append(mount_point)
  return mounts


def MakePartitionTable(file_path):
  """Create a partition table in a file.

  Args:
    file_path: A path to a file where a partition table will be created.
  """
  RunCommand(['parted', '-s' , file_path, 'mklabel', 'msdos'])


def MakePartition(file_path, partition_type, fs_type, start, end):
  """Create a partition in a file.

  Args:
    file_path: A path to a file where a partition will be created.
    partition_type: A type of a partition to be created. Tested option is msdos.
    fs_type: A type of a file system to be created. For example, ext2, ext3,
      etc.
    start: Start offset of a partition in bytes.
    end: End offset of a partition in bytes.
  """
  parted_cmd = ['parted', '-s', file_path, 'unit B', 'mkpart', partition_type,
                fs_type, str(start), str(end)]
  RunCommand(parted_cmd)
  # set boot 
  # TODO: move to separate function
  parted_cmd = ['parted', '-s', file_path, 'set', '1'  , 'boot' , 'on']
  RunCommand(parted_cmd)


def MakeFileSystem(dev_path, fs_type, uuid=None):
  """Create a file system in a device.

  Args:
    dev_path: A path to a device.
    fs_type: A type of a file system to be created. For example ext2, ext3, etc.
    uuid: The value to use as the UUID for the filesystem. If none, a random
          UUID will be generated and used.

  Returns:
    The uuid of the filesystem. This will be the same as the passed value if
    a value was specified. If no uuid was passed in, this will be the randomly
    generated uuid.

  Raises:
    MakeFileSystemException: If mkfs encounters an error.
  """
  if uuid is None:
    uuid = RunCommand(['uuidgen']).strip()
  if uuid is None:
    raise MakeFileSystemException(dev_path)
  # TODO: make fs options parametrizable 
  mkfs_cmd = ['mkfs', '-t', fs_type, "-E", "lazy_itable_init=1", dev_path]
  RunCommand(mkfs_cmd)

  if fs_type is 'xfs':
    set_uuid_cmd = ['xfs_admin', '-U', uuid, dev_path]
  else:
    set_uuid_cmd = ['tune2fs', '-U', uuid, dev_path]
  RunCommand(set_uuid_cmd)

  return uuid


def Rsync(src, dest, exclude_file, ignore_hard_links, recursive, xattrs, verbose=False):
  """Copy files from specified directory using rsync.

  Args:
    src: Source location to copy.
    dest: Destination to copy files to.
    exclude_file: A path to a file which contains a list of exclude from copy
      filters.
    ignore_hard_links: If True a hard links are copied as a separate files. If
      False, hard link are recreated in dest.
    recursive: Specifies if directories are copied recursively or not.
    xattrs: Specifies if extended attributes are preserved or not.
    verbose: if true, verboses the output and progress while rsync works
  """
  rsync_cmd = ['rsync', '--times', '--perms', '--owner', '--group', '--links',
               '--devices', '--acls', '--sparse']
  if not ignore_hard_links:
    rsync_cmd.append('--hard-links')
  if recursive:
    rsync_cmd.append('--recursive')
  else:
    rsync_cmd.append('--dirs')
  if xattrs:
    rsync_cmd.append('--xattrs')
  if exclude_file:
    rsync_cmd.append('--exclude-from=' + exclude_file)
  if verbose:
    rsync_cmd.extend(['--stats', '--progress' , '-v'])
  rsync_cmd.extend([src, dest])

  logging.debug('Calling: %s', repr(rsync_cmd))
  if exclude_file:
    logging.debug('Contents of exclude file %s:', exclude_file)
    with open(exclude_file, 'rb') as excludes:
      for line in excludes:
        logging.debug('  %s', line.rstrip())
  try:
    RunCommand(rsync_cmd , poll_stdout=verbose)
  except subprocess.CalledProcessError as e:
    raise Exception("rsync return error(%i). Maybe not enough disk space to copy files into '%s' directory" % (e.returncode, str(dest)))


def GetUUID(partition_path):
  """Fetches the UUID of the filesystem on the specified partition.

  Args:
    partition_path: The path to the partition.

  Returns:
    The uuid of the filesystem.
  """
  output = RunCommand(['blkid', partition_path])
  for token in output.split():
    if token.startswith('UUID='):
      uuid = token.strip()[len('UUID="'):-1]

  logging.debug('found uuid = %s', uuid)
  return uuid


def CopyBytes(src, dest, count):
  """Copies count bytes from the src to dest file.

  Args:
    src: The source to read bytes from.
    dest: The destination to copy bytes to.
    count: Number of bytes to copy.
  """
  block_size = 4096
  block_count = count / block_size
  dd_command = ['dd',
                'if=%s' % src,
                'of=%s' % dest,
                'conv=notrunc',
                'bs=%s' % block_size,
                'count=%s' % block_count]
  RunCommand(dd_command)
  remaining_bytes = count - block_count * block_size
  if remaining_bytes:
    logging.debug('remaining bytes to copy = %s', remaining_bytes)
    dd_command = ['dd',
                  'if=%s' % src,
                  'of=%s' % dest,
                  'seek=%s' % block_count,
                  'skip=%s' % block_count,
                  'conv=notrunc',
                  'bs=1',
                  'count=%s' % remaining_bytes]
    RunCommand(dd_command)


def GetPartitionStart(disk_path, partition_number):
  """Returns the starting position in bytes of the partition.

  Args:
    disk_path: The path to disk device.
    partition_number: The partition number to lookup. 1 based.

  Returns:
    The starting position of the first partition in bytes.

  Raises:
    subprocess.CalledProcessError: If running parted fails.
    IndexError: If there is no partition at the given number.
  """
  parted_cmd = ['parted', '-s',
                disk_path,
                'unit B',
                'print']
  # In case the device is not valid and parted throws the retry/cancel prompt
  # write c to stdin.
  output = RunCommand(parted_cmd, input_str='c')
  for line in output.splitlines():
    split_line = line.split()
    if len(split_line) > 4 and split_line[0] == str(partition_number):
      return int(split_line[1][:-1])
  raise IndexError()


def RemovePartition(disk_path, partition_number):
  """Removes the partition number from the disk.

  Args:
    disk_path: The disk to remove the partition from.
    partition_number: The partition number to remove.
  """
  parted_cmd = ['parted',
                disk_path,
                'rm',
                str(partition_number)]
  # In case the device is not valid and parted throws the retry/cancel prompt
  # write c to stdin.
  RunCommand(parted_cmd, input_str='c')


def GetDiskSize(disk_file):
  """Returns the size of the disk device in bytes.

  Args:
    disk_file: The full path to the disk device.

  Returns:
    The size of the disk device in bytes.

  Raises:
    subprocess.CalledProcessError: If fdisk command fails for the disk file.
  """
  output = RunCommand(['fdisk', '-s', disk_file])
  return int(output) * 1024


def RunCommand(command, input_str=None , poll_stdout=False, ignore_non_existant=False):
  """Runs the command and returns the output printed on stdout.

  Args:
    command: The command to run.
    input_str: The input to pass to subprocess via stdin.
    poll_stdout: If set to True, polls stdout and outputs to the log on info level while subprocess is running
    ignore_non_existant: If set to True, ignores any errors if cannot run the program- just returns None in the output
  Returns:
    The stdout from running the command.

  Raises:
    subprocess.CalledProcessError: if the command fails.
  """
  logging.debug('running %s with input=%s', command, input_str)
  try:
    p = subprocess.Popen(command, stdin=subprocess.PIPE,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  except Exception as e:
    if ignore_non_existant:
        return None
    logging.error("!!!ERROR: Cannot run " + str(command) + " . Please check it installed");
    raise
  if poll_stdout:
    while p.poll() == False:
          logging.info("%s" , p.stdout.read())
  cmd_output = p.communicate(input_str)
  logging.debug('stdout %s', cmd_output[0])
  logging.debug('stderr %s', cmd_output[1])
  logging.debug('returncode %s', p.returncode)
  if p.returncode:
    logging.warning('Error while running %s return_code = %s\n'
                    'stdout=%s\nstderr=%s',
                    command, p.returncode, cmd_output[0],
                    cmd_output[1])
    raise subprocess.CalledProcessError(p.returncode,
                                        cmd=command)
  return cmd_output[0]


def TarAndGzipFile(src_paths, dest):
  """Pack file in tar archive and optionally gzip it.

  Args:
    src_paths: A list of files that will be archived.
               (Must be in the same directory.)
    dest: An archive name. If a file ends with .gz or .tgz an archive is gzipped
      as well.

  Raises:
    TarAndGzipFileException: If tar encounters an error.
  """
  if dest.endswith('.gz') or dest.endswith('.tgz'):
    mode = 'czSf'
  else:
    mode = 'cSf'
  src_names = [os.path.basename(src_path) for src_path in src_paths]
  # Take the directory of the first file in the list, all files are expected
  # to be in the same directory.
  src_dir = os.path.dirname(src_paths[0])
  tar_cmd = ['tar', mode, dest, '-C', src_dir] + src_names
  retcode = subprocess.call(tar_cmd)
  if retcode:
    raise TarAndGzipFileException(','.join(src_paths))


class Http(object):
  def Get(self, request, timeout=None):
    return urllib2.urlopen(request, timeout=timeout).read()

  def GetMetadata(self, url_path, recursive=False, timeout=None):
    """Retrieves instance metadata.

    Args:
      url_path: The path of the metadata url after the api version.
                http://169.254.169.254/computeMetadata/v1/url_path
      recursive: If set, returns the tree of metadata starting at url_path as
                 a json string.
      timeout: How long to wait for blocking operations (in seconds).
               A value of None uses urllib2's default timeout.
    Returns:
      The metadata returned based on the url path.

    """
    # Use the latest version of the metadata.
    suffix = ''
    if recursive:
      suffix = '?recursive=true'
    url = '{0}{1}{2}'.format(METADATA_V1_URL_PREFIX, url_path, suffix)
    request = urllib2.Request(url)
    request.add_unredirected_header('Metadata-Flavor', 'Google')
    return self.Get(request, timeout=timeout)


def IsRunningOnGCE():
  """Detect if we are running on GCE.

  Returns:
    True if we are running on GCE, False otherwise.
  """
  # Try accessing DMI/SMBIOS informations through dmidecode first
  try:
    dmidecode_cmd = ['dmidecode', '-s', 'bios-vendor']
    output = RunCommand(dmidecode_cmd , ignore_non_existant=True)
    if output:
        return 'Google' in output
    else:
        return False
  except Exception as e:
    # We fail if dmidecode doesn't exist or we have insufficient privileges
    pass

  # If dmidecode is not working, fallback to contacting the metadata server
  try:
    Http().GetMetadata('instance/id', timeout=1)
    return True
  except urllib2.HTTPError as e:
    logging.warning('http status code=%s' % e.code)
  except urllib2.URLError as e:
    logging.warning('Cannot reach metadata server: %s' % e.reason)
  except Exception as e:
    logging.warning('Cannot reach metadata server ' + str(e))
    pass

  return False


# Copyright 2015 M2IAAS Inc. All Rights Reserved.
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


"""This file defines some functions to handle grub installation to the disk"""

from utils import *
#from gcimagebundlelib.utils import *
import logging
import re


 #recordfail
  #  insmod ext2
  # insmod ext3
  # insmod xfs
  #  set root='(hd0,1)'
  #  search --no-floppy --fs-uuid --set {UUID}

  # Patching Legacy Grub
def _patchGrubLegacyConfig(grub_conf_path , partition_uuid):
    """
    Rewrites grub config and points default entry to the partition identified by uuid
    The function searches for default grub entry and modifies it with partiton entry given
    """

    grub_conf_file = open(grub_conf_path, "r")
    grub_conf = grub_conf_file.read()
    grub_conf_file.close()

    # seek for default entry
    match = re.search("default=[0-9]", grub_conf, re.MULTILINE)
    default = 0
    if match == None:
        default = 0
        logging.info("Found no default entry in grub config")
    else:
        default = match.group(0)
        default = int(default.split("=")[1])

    matches = re.findall("title*\s.*\n.*\n.*\n.*", grub_conf, re.MULTILINE)
    original_menuentry = str(matches[default])
    original_menu_contents = original_menuentry[original_menuentry.find("$") + 1:]

    # Default opts
    defgrubparms = "\t recordfail\n\
    \t module ext2\n\
    \t module xfs\n\
    \t module gzio\n\
    \t module part_msdos\n"
    searchuuid = "\t search --no-floppy --fs-uuid --set " + partition_uuid + "\n"

    entry_contents = defgrubparms + searchuuid
    # we use the same linux kernel and parms just switching its root
    # regexp supports linux and linux16 dericitives
    matches = re.findall("kernel*\s.*$", original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No linux entry found! ")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    linux_row = matches[0]
    # replace any path to /boot (sometimes grub points to / instead of /boot)
    linux_row = re.sub("\s/(?!boot)", " /boot/", linux_row)
    root_row = re.findall("root *\s.*", original_menu_contents, re.MULTILINE)[0]
    root_row = re.sub("root *\s.*", "root=/dev/disk/by-uuid/" + partition_uuid, root_row)
    #turn fastboot to switch of fsck (check of all filesystems.
    #if more than one fs available it may start complaining during the boot)
    linux_row = linux_row + " fastboot"
    linux_row = root_row + "\n" + linux_row
    entry_contents = entry_contents + linux_row + "\n"

    #then we add initrd entry as-is
    matches = re.findall("initrd.*$", original_menu_contents, re.MULTILINE)
    if matches == None:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No initrd entry found")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    initrd_row = matches[0]
    #replace any path to /boot (sometimes grub points to / instead of /boot)
    initrd_row = re.sub("\s/(?!boot)", " /boot/", initrd_row)#

    entry_contents = entry_contents + initrd_row + "\n"
    entry_contents = entry_contents + "boot\n"

    replaced_grub = re.sub("(menuentry\s[^{]*){[^}]*}", "\g<1>{\n" + entry_contents + "}", grub_conf, re.MULTILINE)
    logging.info("grub.conf processed")
    logging.debug("grub conf contains: " + replaced_grub)
    if replaced_grub == grub_conf:
        logging.warn("! No data was replaced in the config. Boot failures are highly possible")
    grub_conf_file = open(grub_conf_path, "w")
    grub_conf_file.write(replaced_grub)
    grub_conf_file.close()

## Patching Grub2
def _patchGrubConfig(grub_conf_path, partition_uuid):
    """
    Rewrites grub config and points default entry to the partition identified by uuid
    The function searches for default grub entry and modifies it with partiton entry given
    """

    grub_conf_file = open(grub_conf_path, "r")
    grub_conf = grub_conf_file.read()
    grub_conf_file.close()

    # seek for default entry
    match = re.search( "set default=\\\"([0-9]*)\\\"", grub_conf, re.MULTILINE )
    default = 0
    if match == None:
        logging.info("Found no default entry in grub config")
    else:
        default = int(match.group(1))

    matches = re.findall("menuentry\s[^{]*{[^}]*}" , grub_conf, re.MULTILINE)

    original_menuentry = str(matches[default])
    original_menu_contents = original_menuentry[original_menuentry.find("{")+1:]

    # Default opts
    defgrubparms = "\t recordfail\n\
    \t insmod ext2\n\
    \t insmod xfs\n\
    \t insmod gzio\n\
    \t insmod part_msdos\n"
    searchuuid = "\t search --no-floppy --fs-uuid --set " + partition_uuid + "\n"

    entry_contents = defgrubparms + searchuuid

    # we use the same linux kernel and parms just switching its root
    # regexp supports linux and linux16 dericitives
    matches = re.findall("\slinux[1-9]*\s.*$", original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No linux entry found! ")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    linux_row = matches[0]
    linux_row = re.sub("\s/(?!boot)", " /boot/", linux_row) # replace any path to /boot (sometimes grub points to / instead of /boot)
    linux_row = re.sub("root=([^\s]*)", "root=UUID="+partition_uuid, linux_row)
    linux_row = linux_row.replace("console=ttyS0", "") #switch serial console off
    linux_row = linux_row + " fastboot" #turn fastboot to switch of fsck (check of all filesystems. if more than one fs available it may start complaining during the boot)

    entry_contents = entry_contents + linux_row + "\n"

    #then we add initrd entry as-is
    matches = re.findall("\sinitrd[1-9]*\s.*$", original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No initrd entry found")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    initrd_row = matches[0]
    initrd_row = re.sub("\s/(?!boot)", " /boot/", initrd_row)# replace any path to /boot (sometimes grub points to / instead of /boot)

    entry_contents = entry_contents + initrd_row + "\n"
    entry_contents = entry_contents + "boot\n"

    replaced_grub = re.sub("(menuentry\s[^{]*){[^}]*}", "\g<1>{\n"+entry_contents+"}", grub_conf, re.MULTILINE)
    logging.info("grub.conf processed")
    logging.debug("grub conf contains: " + replaced_grub)
    if replaced_grub == grub_conf:
        logging.warn("! No data was replaced in the config. Boot failures are highly possible")


    grub_conf_file = open(grub_conf_path, "w")
    grub_conf_file.write(replaced_grub)
    grub_conf_file.close()

def InstallGrub(mount_point, partition_dev):
    """Adds Grub boot loader to the disk and points it to boot from the partition"""
    logging.info(">>> Applying GRUB configuration")
    partition_path = partition_dev
    logging.info("The partition is " + partition_path)
    if "/dev/loop" in str(partition_path) and len(str(partition_path)) == len("/dev/loop") + 1: # to distinguish /dev/loop1p1 from /dev/loop1
        #in case we use extra loop for mapping the partition
        losetup_out = RunCommand(["losetup", partition_path])
        #we deduce the disk path
        partition_path = losetup_out[losetup_out.find('(')+1:losetup_out.find(')')]
        diskpath = str(partition_path).replace("/dev/mapper/", "")
        if not ("/dev/" in diskpath):
            diskpath = "/dev/" + diskpath
    if str(partition_path).endswith("p1"):
        diskpath = str(partition_path).replace("p1", "").replace("/dev/mapper/", "")
        diskpath = "/dev/" + diskpath
    else:
        logging.error("!!!ERROR: cannot find a partition \ disk to install GRUB")
        raise OSError("Cannot find partition to install GRUB")
    devmap = mount_point+"/boot/device.map"
    with open(devmap,"w") as f:
        f.write("(hd0)   "+str(diskpath)+"\n(hd0,1) "+str(partition_dev))
        f.close()
    # install grub there
    # NOTE: GRUB2 settings and kernel\initrd images should be imported from the local disk!
    grub_command = "grub2-install"
    try:
        version = RunCommand([grub_command, "--version"])
    except OSError as e:
        #then there is no such command, try other one
        grub_command = "grub-install"
    version = RunCommand([grub_command, "--version"])
    logging.info(">>>> Using Grub 0.9 Installing profile")
    version = version.strip()
    logging.info(">>> Grub version detected: " + version + " (0.9+ is required)")
    legacy = 0
    if os.path.exists(mount_point+"/boot/grub/grub.conf"):
        legacy = 1
        logging.info(">>>> Grub Legacy has been detected")
    if legacy == 1:
        RunCommand([grub_command, "--root-directory=" + mount_point, str(diskpath)])
    else:
        RunCommand([grub_command, "--root-directory=" + mount_point, "--modules=ext2 linux part_msdos xfs gzio normal", str(diskpath)])
    uuid = RunCommand(["blkid", "-s", "UUID", "-o", "value", partition_dev])
    uuid = str(uuid).strip()
    if legacy == 1:
        _patchGrubLegacyConfig(mount_point + "/boot/grub/grub.conf", uuid)
    else:
        if os.path.exists(mount_point + "/boot/grub2/grub.cfg"):
            _patchGrubConfig(mount_point + "/boot/grub2/grub.cfg", uuid)
        else:
            _patchGrubConfig(mount_point + "/boot/grub/grub.cfg", uuid)
    return

#for initial debug
if __name__ == '__main__':
    _patchGrubLegacyConfig("/boot/grub/grub.conf", "EDA")

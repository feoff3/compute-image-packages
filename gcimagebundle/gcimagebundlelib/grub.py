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

def _patchGrubConfig(grub_conf_path , partition_uuid):
    """
    Rewrites grub config and points default entry to the partition identified by uuid
    The function searches for default grub entry and modifies it with partiton entry given
    """
    
    grub_conf_file = open(grub_conf_path, "r")
    grub_conf = grub_conf_file.read()
    grub_conf_file.close()

    match = re.search( "set default=\\\"([0-9]*)\\\"", grub_conf , re.MULTILINE )
    if match == None:
        logging.error("!!!ERROR: Couldn't parse grub config! ")
        logging.error("Config " + grub_conf)
        raise LookupError()

    default = int(match.group(1))
    matches = re.findall("menuentry\s[^{]*{[^}]*}"  , grub_conf , re.MULTILINE)
    
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
    matches = re.findall("\slinux\s.*$" , original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No linux entry found! ")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    linux_row = matches[0]
    linux_row = re.sub("root=([^\s]*)" , "root=UUID="+partition_uuid , linux_row)
    linux_row = linux_row.replace("console=ttyS0" , "") #switch serial console off

    entry_contents = entry_contents + linux_row + "\n"
    
    #then we add initrd entry as-is
    matches = re.findall("\sinitrd\s.*$" , original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No initrd entry found")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    initrd_row = matches[0]

    entry_contents = entry_contents + initrd_row + "\n"
    entry_contents = entry_contents + "boot\n"

    replaced_grub = re.sub("(menuentry\s[^{]*){[^}]*}" , "\g<1>{\n"+entry_contents+"}" , grub_conf , re.MULTILINE)
    logging.info("grub.conf processed")
    logging.debug("grub conf contains: " + replaced_grub)
    if replaced_grub == grub_conf:
        logging.warn("! No data was replaced in the config. Boot failures are highly possible")

    
    grub_conf_file = open(grub_conf_path, "w")
    grub_conf_file.write(replaced_grub)
    grub_conf_file.close()

def InstallGrub(mount_point , partition_dev):
    """Adds Grub boot loader to the disk and points it to boot from the partition"""
    logging.info(">>> Installing grub")
    partition_path = partition_dev
    logging.info("The partition is " + partition_path)
    if "/dev/loop" in str(partition_path) and len(str(partition_path)) == len("/dev/loop") + 1: # to distinguish /dev/loop1p1 from /dev/loop1
        #in case we use extra loop for mapping the partition
        losetup_out = RunCommand(["losetup" , partition_path])
        #we deduce the disk path
        partition_path = losetup_out[losetup_out.find('(')+1:losetup_out.find(')')]
        diskpath = str(partition_path).replace("/dev/mapper/" , "")
        if not ("/dev/" in diskpath):
            diskpath = "/dev/" + diskpath
    elif str(partition_path).endswith("p1"):
        diskpath = str(partition_path).replace("p1" , "").replace("/dev/mapper/" , "")
        diskpath = "/dev/" + diskpath
    else:
        logging.error("!!!ERROR: cannot find a partition \ disk to install GRUB")
        raise OSError("Cannot find partition to install GRUB")
    
    # install grub2 there
    # NOTE: GRUB2 settings and kernel\initrd images should be imported from the local disk!
    RunCommand(["grub-install" , str(diskpath), "--root-directory=" + mount_point , "--recheck"])
          
    uuid = RunCommand(["blkid", "-s", "UUID", "-o" , "value", partition_dev])
    uuid = str(uuid).strip()

    _patchGrubConfig(mount_point + "/boot/grub/grub.cfg" , uuid)

    #TODO: generate config
    #TODO: 1. make grub template
    #TODO: 2. set linux boot options there
    #TODO: 3. find initrd to match linux
    #TODO: 4. drive name (should be /dev/sda1 in most cases, but should be parm-able)

    # RunCommand(["grub-mkconfig",  "-o" , mount_point+"/boot/grub/grub.cfg"])
    return

   



#for initial debug
if __name__ == '__main__':
    _patchGrubConfig("/grub.conf" , "EDA")

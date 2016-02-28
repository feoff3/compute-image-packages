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
import os
import stat

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
    match=re.search("default=[0-9]", grub_conf , re.MULTILINE)
    default = 0
    if match == None:
        default = 0
        logging.info("Found no default entry in grub config")
    else:
        default = match.group(0)
        default = int(default.split("=")[1])

    matches = re.findall("title(?:(?!\ntitle).[^\n])*", grub_conf, re.MULTILINE)
    #*\s.*\n.*\n.*\n.*",grub_conf, re.MULTILINE)
    
    # getting the default entry
    original_title = str(matches[default])
    logging.debug("Found title " + original_title)
    original_menu_entry = grub_conf[grub_conf.find(original_title):]
    #find the next title after that
    original_menu_entry = original_menu_entry[:original_menu_entry.find("title" , 6)]
    original_menu_contents = original_menu_entry[original_menu_entry.find("\n")+1:]

    # we use the same linux kernel and parms just switching its root
    # regexp supports linux and linux16 dericitives
    matches = re.findall("kernel*\s.*$" , original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No kernel entry found! ")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    linux_row = matches[0]
    linux_row = re.sub("\s/(?!boot)" , " /boot/" , linux_row) # replace any path to /boot (sometimes grub points to / instead of /boot)
    linux_row = re.sub("root=([^\s]*)" , "root=/dev/disk/by-uuid/"+partition_uuid , linux_row)
    linux_row = linux_row.replace("console=ttyS0" , "") #switch serial console off
    linux_row = linux_row + " fastboot" #turn fastboot to switch of fsck (check of all filesystems. if more than one fs available it may start complaining during the boot)
    
    # see uuid options for various ubuntu distros here https://forums.opensuse.org/showthread.php/414356-Correct-menu-lst
    # TODO: check if it works on non-ubuntu kernels
    if original_menu_contents.find("uuid ") != -1:
        root_row = "uuid " + partition_uuid 
    else:
        root_row = "root (hd0,1)"

    entry_contents = "\n" + root_row+ "\n"+linux_row + "\n"
    
    #then we add initrd entry as-is
    matches = re.findall("initrd.*$" , original_menu_contents, re.MULTILINE)
    if matches == None:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No initrd entry found")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    initrd_row = matches[0]
    initrd_row = re.sub("\s/(?!boot)" , " /boot/" , initrd_row)# replace any path to /boot (sometimes grub points to / instead of /boot)

    entry_contents = entry_contents + initrd_row + "\n"
    entry_contents = entry_contents + "boot\n"

    replaced_grub = grub_conf.replace(original_menu_entry, original_title+" Migrated\n"+entry_contents)

    logging.info("grub.conf processed")
    logging.debug("grub conf contains: " + replaced_grub)
    if replaced_grub == grub_conf:
        logging.warn("! No data was replaced in the config. Boot failures are highly possible")
    grub_conf_file = open(grub_conf_path, "w")
    grub_conf_file.write(replaced_grub)
    grub_conf_file.close()

## Patching Grub2
def _patchGrubConfig(grub_conf_path , partition_uuid):
    """
    Rewrites grub config and points default entry to the partition identified by uuid
    The function searches for default grub entry and modifies it with partiton entry given
    """
    
    grub_conf_file = open(grub_conf_path, "r")
    grub_conf = grub_conf_file.read()
    grub_conf_file.close()

    # seek for default entry
    match = re.search( "set default=\\\"([0-9]*)\\\"", grub_conf , re.MULTILINE )
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
    matches = re.findall("\slinux[1-9]*\s.*$" , original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No linux entry found! ")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    linux_row = matches[0]
    linux_row = re.sub("\s/(?!boot)" , " /boot/" , linux_row) # replace any path to /boot (sometimes grub points to / instead of /boot)
    linux_row = re.sub("root=([^\s]*)" , "root=UUID="+partition_uuid , linux_row)
    linux_row = linux_row.replace("console=ttyS0" , "") #switch serial console off
    linux_row = linux_row + " fastboot" #turn fastboot to switch of fsck (check of all filesystems. if more than one fs available it may start complaining during the boot)

    entry_contents = entry_contents + linux_row + "\n"
    
    #then we add initrd entry as-is
    matches = re.findall("\sinitrd[1-9]*\s.*$" , original_menu_contents, re.MULTILINE)
    if len(matches) == 0:
        logging.error("!!!ERROR: Couldn't parse grub config menu entry! No initrd entry found")
        logging.error("Config " + original_menuentry)
        raise LookupError()
    initrd_row = matches[0]
    initrd_row = re.sub("\s/(?!boot)", " /boot/", initrd_row)# replace any path to /boot (sometimes grub points to / instead of /boot)

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

def DetectDisk(partition_dev):
    """detects disk device by a partition dev"""
    partition_path = partition_dev

    # here we get basic disk of the partition
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

    return diskpath

def DetectBackingFile(diskpath):
    """detects disk device by a partition dev"""
    real_diskpath = diskpath
    # here we check if disk is represented by a loopback to a file - grub 1 will need a path to file not disk
    if "/dev/loop" in diskpath: 
        #in case we use extra loop for mapping the partition
        losetup_out = RunCommand(["losetup" , diskpath])
        #we deduce the disk path
        real_diskpath = losetup_out[losetup_out.find('(')+1:losetup_out.find(')')]
        logging.info(real_diskpath + " is a backing dev/file behind the disk dev " + diskpath)
    return real_diskpath

def PrepareLegacyCommands(real_diskpath):
    """prepares commands to path to grub utility"""
    return "device (hd0) " + real_diskpath +  "\nroot (hd0,0)\n setup (hd0)\nquit\n"

def InstallGrub(mount_point , partition_dev):
    """Adds Grub boot loader to the disk and points it to boot from the partition"""
    logging.info(">>> Applying GRUB configuration")
    
    diskpath = DetectDisk(partition_dev)
    
    # choose grub1 or grub2
    legacy = 0
    if not (os.path.exists(mount_point+"/boot/grub/grub.cfg") or os.path.exists(mount_point + "/boot/grub2/grub.cfg")):
        legacy = 1
        logging.info(">>>> Grub Legacy has been detected")
        #prepare grub command line
        real_diskpath = DetectBackingFile(diskpath)
        legacy_commands = PrepareLegacyCommands(real_diskpath)

    grub_command = "grub2-install"
    version = RunCommand([grub_command , "--version"], ignore_non_existant=True)
    if not version:
        grub_command = "grub-install"
    version = RunCommand([grub_command , "--version"])
    version = version.strip()
    logging.info(">>> Grub version detected: " + version + " (0.9+ is required)")
    
    if legacy == 1:
        RunCommand(["grub" , "--batch" , "--device-map=/dev/null"] , input_str=legacy_commands)
    else:
        RunCommand([grub_command , "--root-directory=" + mount_point , "--modules=ext2 linux part_msdos xfs gzio normal" , str(diskpath)])
    uuid = RunCommand(["blkid", "-s", "UUID", "-o" , "value", partition_dev])
    uuid = str(uuid).strip()
    if legacy == 1:
        _patchGrubLegacyConfig(mount_point + "/boot/grub/grub.conf", uuid)
    else:
        if os.path.exists(mount_point + "/boot/grub2/grub.cfg"):
            _patchGrubConfig(mount_point + "/boot/grub2/grub.cfg" , uuid)
        else:
            _patchGrubConfig(mount_point + "/boot/grub/grub.cfg" , uuid)
    return

   
test_script = "deviceName=`losetup --show --find /cloudscraper-images/vda.sparsed.raw\
/dev/loop0`|sed s/\n// #sometimes get really sick\
deviceName=/dev/loop0\
string=`fdisk -l $deviceName |grep $deviceName`\
partitionName=$(echo $string | cut -f8 -d\ )|sed s/\n//\
deviceSize=$(echo $string | cut -f1 -d\ )|sed s/\n//\
echo $deviceName $deviceSize\
echo 0 $deviceSize linear $deviceName 0 | dmsetup create l$(echo $deviceName|sed s/.*l//)\
kpartx -a $deviceName\
tempdir='/tmp/mnt'\
loopId=`echo $deviceName | sed s/.*loop// |sed s/\n//`\
mapperName=\"/dev/mapper/loop\"$loopId\"p1\"\
mount $mapperName $tempdir\
losetup /dev/loop1 $mapperName"

#for initial debug
if __name__ == '__main__':
    #with open("/tmp/script.sh", "w") as f:
    #    f.write(test_script)
    #os.chmod("/tmp/script.sh", stat.S_IRWXU)
    #RunCommand(["bash" , "/tmp/script.sh"])
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(handler)
    InstallGrub("/tmp/mnt" , "/dev/loop1")
    #_patchGrubLegacyConfig("/boot/grub/grub.conf" , "EDA")

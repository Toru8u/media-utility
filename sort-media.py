##
# Program for sorting media files: jpg, jpeg, (png), mov, mp4 in sub directories yyyy-MM-dd
# 
# description:
# 1. two input parameters <src dir> and <dest dir>
# 2. get list of files of type: jpg, jpeg, mov and mp4
# 3. read for each file meta infomration and get directory name as yyyy-MM-dd
# 4. does directory exist in src? create directory... and move file
#
# Invoke with: python .\sort-media.py u:/temp/import_copy_test  u:/temp/dest
#


import sys, getopt
import os
import glob
import shutil
import PIL.Image
from pathlib import Path

##https://exiv2.org/tags.html
# Returns date as YYYY-MM-dd
def get_jpg_timestamps(filename):
    img = PIL.Image.open(filename)
    exif_data = img._getexif()
    # Exif Numeric Tags  https://www.exiv2.org/tags.html
    # print (exif_data.get(272)) # Name of the Campera

    if exif_data == None: # No EXIF Data available...
        result = "0000-00-00"
    else:
        # 306 The date and time of image creation. In Exif standard, it is the date and time the file was changed.
        result = exif_data.get(306) 

        if result == None:
            result = "0000-00-00"
        else:
            result = result[0:10].replace(":", "-") 
    return result 

# 
# Returns date_time as YYYY-MM-dd_hh
def get_jpg_timestamps_long(filename):
    img = PIL.Image.open(filename)
    exif_data = img._getexif()
    # Exif Numeric Tags  https://www.exiv2.org/tags.html
    # print (exif_data.get(272)) # Name of the Campera

    if exif_data == None: # No EXIF Data available...
        result = "0000-00-00"
    else:
        # 306 The date and time of image creation. In Exif standard, it is the date and time the file was changed.
        result = exif_data.get(306) 

        if result == None:
            result = "0000-00-00"
        else:
            result = result[0:19].replace(":", "-") 
            result = result.replace(" ", "_")
    return result 

def get_mov_timestamps(filename):
    ''' Get the creation and modification date-time from .mov metadata.

        Returns None if a value is not available.
    '''
    from datetime import datetime as DateTime
    import struct

    ATOM_HEADER_SIZE = 8
    # difference between Unix epoch and QuickTime epoch, in seconds
    EPOCH_ADJUSTER = 2082844800

    creation_time = modification_time = None

    # search for moov item
    with open(filename, "rb") as f:
        while True:
            atom_header = f.read(ATOM_HEADER_SIZE)
            #~ print('atom header:', atom_header)  # debug purposes
            if atom_header[4:8] == b'moov':
                break  # found
            else:
                atom_size = struct.unpack('>I', atom_header[0:4])[0]
                f.seek(atom_size - 8, 1)

        # found 'moov', look for 'mvhd' and timestamps
        atom_header = f.read(ATOM_HEADER_SIZE)
        if atom_header[4:8] == b'cmov':
            raise RuntimeError('moov atom is compressed')
        elif atom_header[4:8] != b'mvhd':
            raise RuntimeError('expected to find "mvhd" header.')
        else:
            f.seek(4, 1)
            creation_time = struct.unpack('>I', f.read(4))[0] - EPOCH_ADJUSTER
            creation_time = DateTime.fromtimestamp(creation_time)
            if creation_time.year < 1990:  # invalid or censored data
                creation_time = None

            modification_time = struct.unpack('>I', f.read(4))[0] - EPOCH_ADJUSTER
            modification_time = DateTime.fromtimestamp(modification_time)
            if modification_time.year < 1990:  # invalid or censored data
                modification_time = None

        result = creation_time or modification_time
        if result == None:
            result = "0000-00-00"

    return result.strftime('%Y-%m-%d')

## 
## Beginning of the program
## 

# Check for two parameters
if len(sys.argv) <2:
    print("At least one parameter is required, usage: <src dir> (<dest dir>) ")
    sys.exit(0)

srcDir = sys.argv[1]
if len(sys.argv) == 2:
    destDir = srcDir
else:
    destDir = sys.argv[2] 

print ("src  dir: "+ srcDir)
print ("dest dir: "+ destDir)

# check if both parameters are directories
if not os.path.isdir(srcDir) or not os.path.isdir(destDir):
    print ("The paramters are not directories") 
    sys.exit(0)

# get list of all files in <src dir> 


# case insensitive
def insensitive_glob(pattern):
    def either(c):
        return '[%s%s]' % (c.lower(), c.upper()) if c.isalpha() else c
    return glob.glob(''.join(map(either, pattern)))

###
# Working part
###


# 1. mov
#movFileList = glob.glob(srcDir+"/*.mov")
movFileList = insensitive_glob(srcDir+"/*.mov")
print ("Number of MOV files: " + str(len(movFileList)))
for file in movFileList:
    dir = destDir+"/"+get_mov_timestamps(file)
    if not os.path.isdir(dir):
        os.mkdir(dir)

    new_file_name = get_mov_timestamps(file) + "_"+ Path(file).stem +".mov"
    shutil.move(file, dir+"/"+new_file_name)
    #shutil.move(file, dir)
print ("All MOV files done")

# 2. jpg
#jpgFileList = glob.glob(srcDir+"/*.jpg")
jpgFileList = insensitive_glob(srcDir+"/*.jpg")
print ("Number of JPG files: " + str(len(jpgFileList)))
for file in jpgFileList:
    dir = destDir+"/"+get_jpg_timestamps(file)
    if not os.path.isdir(dir):
        os.mkdir(dir)

    new_file_name = get_jpg_timestamps_long(file) + "_"+ Path(file).stem +".jpg"
    shutil.move(file, dir+"/"+new_file_name)
print ("All JPG files done")

# 3. jpeg
#jpegFileList = glob.glob(srcDir+"/*.jpeg")
jpegFileList = insensitive_glob(srcDir+"/*.jpeg")
print ("Number of JPG files: " + str(len(jpegFileList)))
for file in jpegFileList:
    dir = destDir+"/"+get_jpg_timestamps(file)
    if not os.path.isdir(dir):
        os.mkdir(dir)

    #print(get_jpg_timestamps_long(file)) ## print
    new_file_name = get_jpg_timestamps_long(file) + "_"+ Path(file).stem +".jpg"
    shutil.move(file, dir+"/"+new_file_name)

print ("All JPEG files done")

# 4. PNG

# 5. MP4


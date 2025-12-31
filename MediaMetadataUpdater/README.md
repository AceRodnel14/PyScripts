# MediaMetadataUpdater

This script automates the updating of .jpeg, .jpg, .mp4 or any media files. It uses exiftool.exe to update the media files. The python script focuses on checking provided folders (absolute path) and processes files that matches the required naming convention.

### Supported Patterns
\<username\>=_=YYYY-MM-DDThhmmss.msZ\<slug\><br/>
\<username\>__YYYY-MM-DDThhmmss.msZ\<slug\><br/>
YYYY-MM-DD hh.mm.ss \<image id\><br/>
YYMMDD \<image id\><br/>
YYMMDD-\<image id\><br/>

## exiftool installation
1. Download the 32-bit or 64-bit Windows Executable from the ExifTool home page.<br/>
2. Extract the "exiftool-13.41_xx" folder from the ".zip" file, and place it in the folder where MediaMetadataUpdater.py is saved.
3. Rename "exiftool(-k).exe" to "exiftool.exe".

## MediaMetadataUpdater.py 
### Usage
1. Update line 9 in MediaMetadataUpdater.py<br/>Update the folders variable
2. CD to the directory and run the script using the command below<br/>
>python MediaMetadataUpdater.py<br/>
### Additional parameters/ arguments
| | Description |
| ----------- | ----------- |
| --verbose | Add this to get logs for each files processed, <br/>instead of progress bar |
| --workers \<int\> | Add this with an integer for the percent of <br/>CPU cores to use for this script. <br/>Default is 80 or 80% |
| --workers all | Add this with \'all\' to use all available CPU cores<br/>Default is 80 or 80% |
## ConvertJpgToWebp.py 
### Usage
1. CD to the directory and run the script using the command below<br/>
>python ConvertJpgToWebp.py "\<absolute path for directory\/ directories \(comma delimited\)\>" <br/>
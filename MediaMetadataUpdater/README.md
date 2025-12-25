# MediaMetadataUpdater

This script automates the updating of .jpeg, .jpg, .mp4 or any media files. It uses exiftool.exe to update the media files. The python script focuses on checking provided folders (absolute path) and processes files that matches the required naming convention.

## Pattern
\<username\>__YYYY-MM-DDThhmmss.msZ
YYYY-MM-DD hh.mm.ss \<image id\>
YYMMDD \<image id\>

## exiftool installation
1. Download the 32-bit or 64-bit Windows Executable from the ExifTool home page.<br>
2. Extract the "exiftool-13.41_xx" folder from the ".zip" file, and place it in the folder where MediaMetadataUpdater.py is saved.
3. Rename "exiftool(-k).exe" to "exiftool.exe".

## Usage
1. Update line 9 in MediaMetadataUpdater.py<br>Update the folders variable
2. CD to the directory and run the script using the command below
```python MediaMetadataUpdater.py```
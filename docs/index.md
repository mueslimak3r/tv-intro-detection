# Project Overview

This project tries to detect intros of tv series by comparing pairs of episodes to find the largest common subset of frames.

### How the script compares videos
Each frame from the first quarter of each episode is extracted and a hash (https://pypi.org/project/ImageHash/) is made on the frame. Each frame hash is added to a long video hash.<br>
In pairs the longest identical string is searched from the two video hashes.<br>
Assumption: this is the intro

### How the script finds your videos
When using jellyfin.py, the script queries the jellyfin server and is sent a list of all the tv shows in your library. With that list of shows, it then queries the jellyfin server for the seasons and episodes for each of the shows. Included in the results of those queries is the location on the filesystem for each item (show, season, episode).

To account for jellyfin potentially using a different filesystem path to access the media than the system running the script would (eg: running in docker, running the script on a separate computer with the media drives mounted as network shares), path mapping is used to translate the path jellyfin sees into a path that the script can use.

When running decode.py on its own, the -i parameter is used to specify a folder that contains video files. decode.py doesn't do any searching beyond that single folder, so typically the provided folder will be a "season folder" that contains all the video files for that season of a show.

Individual shows or seasons can be ignored by creating an empty file named `.ignore-intros` inside its folder.

### Examples
scan your jellyfin library, store the result in json, verbose logging enabled, logging debug output to file enabled

`export JELLYFIN_URL="https://myurl" && export JELLYFIN_USERNAME="myusername" && export JELLYFIN_PASSWORD='mypassword'`

`jellyfin.py -j -v -l`

or in reverse order

`jellyfin.py -j -v -l --reverse`

monitor your jellyfin sessions and automatically skip intros using the stored json data

`export JELLYFIN_URL="https://myurl" && export JELLYFIN_USERNAME="myusername" && export JELLYFIN_PASSWORD='mypassword'`

`jellyfin_auto_skip.py`

manually scan a directory containing at least 2 video files, debug logging enabled, logging debug output to file enabled, delete fingerprint data afterward
`decode.py -i /path/to/tv/season -d -l -c`

make the script aware of your host:container path mapping by editing `path_map.txt`

```
# use this file if you run jellyfin in a container
# examples:
#
# linux client, Jellyfin on linux
#
# /host/system/tv/path::/jellyfin/container/tv/path
#
# or
# Windows client, Jellyfin on Windows
#
# X:\some\path\TV::Y:\some\path\TV
#
# or
# Windows client, Jellyfin on linux
#
# or
# X:\some\path\TV::/jellyfin/container/tv/path
```

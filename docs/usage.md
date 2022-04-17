# Running The Scripts

1. Install python3 (tested with 3.8.9+)
2. Install ffmpeg
3. Install python dependencies from `requirements.txt`
4. To use with Jellyfin, run `jellyfin.py`. This will query Jellyfin for a list of series and their paths.
5. To process a directory manually, run `decode.py` and pass the parameter `-i` with the path to a directory containing at least **two** episodes of the same season

By default there is little/no output to stdout or stderr until the script has finished processing some media. Run `jellyfin.py` or `decode.py` with the `-d` parameter for verbose output

When using `jellyfin.py`, the results can be saved to `json` using the `-j` parameter. These will be saved in a sub-directory in `pwd`. Saving the results as json also allows them to be checked in subsequent runs to skip already processed files.

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
# example:
# /host/system/tv/path::/jellyfin/container/tv/path

/srv/my-mnt-title/media/tv::/data/tv
```

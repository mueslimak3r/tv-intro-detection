# tv intro detection

This project tries to detect intros of tv series by comparing two episodes of the same series and trying to find the
largest common subset of frames with a bit of fuzziness.

## Running

1. Install python dependencies from `requirements.txt`
2. Install ffmpeg (optional)
3. To use with Jellyfin, run `jellyfin.py`. This will query Jellyfin for a list of series and their paths.
4. To process a directory manually, run `decode.py` and pass the parameter `-i` with the path to a directory containing at least **two** episodes of the same season

By default there is little/no output to stdout or stderr until the script has finished processing some media. Run `jellyfin.py` or `decode.py` with the `-d` parameter for verbose output

When using `jellyfin.py`, the results can be saved to `json` using the `-j` parameter. These will be saved in a sub-directory in `pwd`. Saving the results as json also allows them to be checked in subsequent runs to skip already processed files.

## Running Docker
  ## Scanner
  'docker run -d \
  --name=Jellyfin-intro-Scanner \
  -e JELLYFIN_URL=http://Jellyfin:port
  -e JELLYFIN_USERNAME=username
  -e JELLYFIN_PASSWORD=password
  -v /path/to/tv/shows/on/host:/path/to/tv/shows/on/Jellyfin/docker/container \
  --restart unless-stopped \
  mueslimak3r/tv-intro-detection:latest'
  
  ## Auto Skipper

## Examples
scan your jellyfin library, store the result in json, debug logging enabled

`jellyfin.py -d -j`

monitor your jellyfin sessions and automatically skip intros using the stored json data

`jellyfin_auto_skip.py`

manually scan a directory containing at least 2 video files, debug logging enabled, delete fingerpring data afterward
`decode.py -d -c -i /path/to/tv/season`

make the script aware of your host:container path mapping by editing `path_map.txt`

```
# use this file if you run jellyfin in a container
# example:
# /host/system/tv/path:/jellyfin/container/tv/path

/srv/my-mnt-title/media/tv:/data/tv
```

## Disclaimer

The decoder relies on comparing two video files to find the similar sections. Because of this, it only works if the intros are similar / identical from episode to episode.

## How it works
Each frame from the first quarter of each episode is extracted and a hash (https://pypi.org/project/ImageHash/) is made on the frame. Each frame hash is added to a long video hash.<br>
In pairs the longest identical string is searched from the two video hashes.<br>
Assumption: this is the intro

## Troubleshooting
If the script is killed while processing media you may encounter issues the next time you run it. This is because corrupt `fingerprint` files are likely left over from the killed session. Simply remove the directory `fingerprints` before running the script again. The same can be done for `jellyfin_cache` though it is less likely to become corrupted

## Improvements

1. Make educated guesses on which parts to fingerpint. At the moment the first quarter of an episode is fingerprinted. Might be to much for longer episodes. etc.
2. Create a fingerprint that works for the whole season instead of finding the same fingerprint for every file.

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

## Running in Docker
  ### Parameters

|| Parameter  | Function |
| ---                                        | ---                                        | ---       |
| Required | ```-e JELLYFIN_URL=http://Jellyfin:port``` | Jellyfin URL         |
| Required | ```-e JELLYFIN_USERNAME=username```        | Jellyfin User Username        |
| Required | ```-e JELLYFIN_PASSWORD='password'```      | Jellyfin User Password         |
| Required | ```-v /path/to/config:/app/config```      | Location of config/data on disk. Must use the same locations for Jellyfin-Intro-Scanner & Jellyfin-Intro-Skipper containers to work correctly together.       |
| Required | ```-v /path/to/media/on/host:/path/to/media/on/Jellyfin/container```      |  Location of media library on disk. If you use the same volume path for your Jellyfin container, you don't have to edit ```path_map.txt``` in your config folder. (If you need to change it you must first create a ```path_map.txt``` in your config folder. ***Not in the data subfolder***)        |
| Optional | ```-e CONFIG_DIR=/config```      |  Use a different directory to store config files. The directory specified should be reflected in the ```/app/config``` path mapping.          |
| Optional | ```-e DATA_DIR=/config/data```      | Use a different directory to store cached data. Modifying this will likely require a new path mapping such as ```-v /path/to/data:/data```.         |

  ### Scanner - Docker Run
```
docker run -d \
    --name=Jellyfin-Intro-Scanner \
    -e JELLYFIN_URL=http://Jellyfin:port \
    -e JELLYFIN_USERNAME=username \
    -e JELLYFIN_PASSWORD='password' \
    -v /path/to/media/on/host:/path/to/media/on/Jellyfin/container \
    -v /path/to/config:/app/config \
    --network=jellyfin-network \
    --restart unless-stopped \
    ghcr.io/mueslimak3r/jellyfin-intro-scanner:latest
```
  ### Skipper - Docker Run
```
docker run -d \
  --name=Jellyfin-Intro-Skipper \
  -e JELLYFIN_URL=http://Jellyfin:port \
  -e JELLYFIN_USERNAME=username \
  -e JELLYFIN_PASSWORD='password' \
  -v /path/to/config:/app/config \
  --network=jellyfin-network \
  --restart unless-stopped \
  ghcr.io/mueslimak3r/jellyfin-intro-skipper:latest
```
  ### Scanner & Skipper - Docker Compose
```
---
version: "3.8"

services:
  Jellyfin-Intro-Scanner:
    image: ghcr.io/mueslimak3r/jellyfin-intro-scanner:latest
    depends_on:
	- Jellyfin
    container_name: Jellyfin-Intro-Scanner
    environment:
      - JELLYFIN_URL=http://Jellyfin:port
      - JELLYFIN_USERNAME=username
      - JELLYFIN_PASSWORD='password'
    volumes:
      - /path/to/media/on/host:/path/to/media/on/Jellyfin/container
      - /path/to/config:/app/config
    restart: unless-stopped

  Jellyfin-Intro-Skipper:
    image: ghcr.io/mueslimak3r/jellyfin-intro-skipper:latest
    depends_on:
	- Jellyfin
    container_name: Jellyfin-Intro-Skipper
    environment:
      - JELLYFIN_URL=http://Jellyfin:port
      - JELLYFIN_USERNAME=username
      - JELLYFIN_PASSWORD='password'
    volumes:
	- /path/to/config:/app/config
    restart: unless-stopped
```

## Examples
scan your jellyfin library, store the result in json, debug logging enabled, logging debug output to file enabled

`jellyfin.py -j -d -l`

monitor your jellyfin sessions and automatically skip intros using the stored json data

`jellyfin_auto_skip.py`

manually scan a directory containing at least 2 video files, debug logging enabled, logging debug output to file enabled, delete fingerprint data afterward
`decode.py -i /path/to/tv/season -d -l -c`

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

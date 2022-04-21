# Running with Docker

### Docker Compose - Scanner & Skipper 

```
---
version: "3.8"

services:
  Jellyfin-Intro-Scanner:
    image: ghcr.io/mueslimak3r/jellyfin-intro-scanner:latest

    container_name: Jellyfin-Intro-Scanner
    environment:
      - JELLYFIN_URL=http://Jellyfin:port
      - JELLYFIN_USERNAME=username
      - JELLYFIN_PASSWORD=password
    volumes:
      - /path/to/media/on/host:/path/to/media/on/Jellyfin/container
      - /path/to/config:/app/config
    restart: unless-stopped

  Jellyfin-Intro-Skipper:
    image: ghcr.io/mueslimak3r/jellyfin-intro-skipper:latest

    container_name: Jellyfin-Intro-Skipper
    environment:
      - JELLYFIN_URL=http://Jellyfin:port
      - JELLYFIN_USERNAME=username
      - JELLYFIN_PASSWORD=password
    volumes:
      - /path/to/config:/app/config
    restart: unless-stopped
```

### Docker Run - Scanner
```
docker run -d \
    --name=Jellyfin-Intro-Scanner \
    -e JELLYFIN_URL=http://Jellyfin:port \
    -e JELLYFIN_USERNAME=username \
    -e JELLYFIN_PASSWORD='password' \
    -v /path/to/media/on/host:/path/to/media/on/Jellyfin/container \
    -v /path/to/config:/app/config \
    --restart unless-stopped \
    ghcr.io/mueslimak3r/jellyfin-intro-scanner:latest
```

### Docker Run - Skipper
```
docker run -d \
  --name=Jellyfin-Intro-Skipper \
  -e JELLYFIN_URL=http://Jellyfin:port \
  -e JELLYFIN_USERNAME=username \
  -e JELLYFIN_PASSWORD='password' \
  -v /path/to/config:/app/config \
  --restart unless-stopped \
  ghcr.io/mueslimak3r/jellyfin-intro-skipper:latest
```

### Parameters - used by both scanner and skipper

| Parameter | Function | Description |
|:-|:-:|-:|
| Required | ```-e JELLYFIN_URL=http://Jellyfin:port``` | Jellyfin URL |
|---
| Required | ```-e JELLYFIN_USERNAME=username``` | Jellyfin User Username |
|---
| Required | ```-e JELLYFIN_PASSWORD='password'``` | Jellyfin User Password |
|---
| Required | ```-v /path/to/config:/app/config``` | Location of config/data on disk. Must use the same locations for Jellyfin-Intro-Scanner & Jellyfin-Intro-Skipper containers to work correctly together. |
|---
| Required | ```-v /path/to/media/on/host:/path/to/media/on/Jellyfin/container``` |  Location of media library on disk. If you use the same volume path for your Jellyfin container, you don't have to edit ```path_map.txt``` in your config folder. (If you need to change it you must first create a ```path_map.txt``` in your config folder. ***Not in the data subfolder***). |
|---
| Optional | ```-e REVERSE_SORT=TRUE``` |  Process shows in reverse order |
|---
| Optional | ```-e PATH_MAP="/srv/mount1/tv::/data/tv1,/srv/mount2/tv::/data/tv2"``` | Specify host:container path mapping. Mappings specified here are added to those specified in ```path_map.txt``` |
|---
| Optional | ```-e CONFIG_DIR=/config``` | Use a different directory to store config files. The directory specified should be reflected in the ```/app/config``` path mapping. |
|---
| Optional | ```-e DATA_DIR=/config/data``` | Use a different directory to store cached data. Modifying this will likely require a new path mapping such as ```-v /path/to/data:/data``` |
|---
| Optional | ```-e LOG_LEVEL=INFO/VERBOSE/DEBUG``` | Change the log level (default is verbose for docker) |
| Optional | ```-e AUTO_SKIP_COOLDOWN=4``` | Specify the cooldown time (seconds) for the auto skipper (default 2) |
{:.table-striped}

### Docker with network shares

Network shares need to be mounted with a driver. This example uses a Windows host, two SMB shares, and a local drive.

```
---
version: "3.8"

volumes:
  mymount:
    name: mymount
    driver_opts:
      type: cifs
      o: "user=Guest,iocharset=utf8,vers=3.1.1,rw"
      device: //192.168.0.101/MyMount
  myothermount:
    name: myothermount
    driver_opts:
      type: cifs
      o: "user=Guest,iocharset=utf8,vers=3.1.1,rw"
      device: //192.168.0.102/MyOtherMount

services:
  Jellyfin-Intro-Scanner:
    image: ghcr.io/mueslimak3r/jellyfin-intro-scanner:latest

    container_name: Jellyfin-Intro-Scanner
    environment:
      - JELLYFIN_URL=http://192.168.0.1212:8096
      - JELLYFIN_USERNAME=myuser
      - JELLYFIN_PASSWORD=mypassword
      - PATH_MAP=/mnt/mymount/TV::/jellyfin-mymount/TV,/mnt/myothermount/TV::/jellyfin-myothermount/TV,/mnt/x/TV/::/jellyfin-x/TV
      # - LOG_LEVEL=DEBUG
    volumes:
      - mymount:/mnt/mymount
      - myothermount:/mnt/myothermount
      - /x/TV:/mnt/x/TV
      - /c/Tools/Jellyfin-Intro-Skip/config:/app/config
    restart: unless-stopped

  Jellyfin-Intro-Skipper:
    image: ghcr.io/mueslimak3r/jellyfin-intro-skipper:latest

    container_name: Jellyfin-Intro-Skipper
    environment:
      - JELLYFIN_URL=http://192.168.0.1212:8096
      - JELLYFIN_USERNAME=myuser
      - JELLYFIN_PASSWORD=mypassword
    volumes:
      - /c/Tools/Jellyfin-Intro-Skip/config:/app/config
    restart: unless-stopped
```

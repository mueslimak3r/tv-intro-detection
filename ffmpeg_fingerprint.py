import os
import re
import cv2
import imagehash
import shutil

import sys, getopt
import subprocess
from pathlib import Path
from PIL import Image
from datetime import datetime, timedelta

config_path = os.environ['CONFIG_DIR'] if 'CONFIG_DIR' in os.environ else './config'
data_path = os.environ['DATA_DIR'] if 'DATA_DIR' in os.environ else os.path.join(config_path, 'data')

def print_debug(*a):
    # Here a is the array holding the objects
    # passed as the argument of the function
    print(*a, file = sys.stderr)

def replace(s):
    return re.sub('[^A-Za-z0-9]+', '', s)

def get_frames(path, frame_nb, log_level):
    if path == None or path == '' or frame_nb == 0:
        return False
    print_debug('running ffmpeg')
    start = datetime.now()
    filename = os.path.join(data_path, "fingerprints/" + replace(path) + "/frames/frame-%08d.jpeg")
    with open(os.devnull, 'w') as fp:
        process = subprocess.Popen(args=["ffmpeg", "-i", path, "-frames:v", str(frame_nb), "-s", "384x216", filename], stdout=fp, stderr=fp)
        process.wait()
        end = datetime.now()
        if log_level > 0:
            print_debug("ran ffmpeg in %s" % str(end - start))
        return process.returncode == 0

def check_frames_already_exist(path, frame_nb):
    for ndx in range(1, frame_nb + 1):
        filename = os.path.join(data_path, "fingerprints/" + replace(path) + "/frames/frame-%s.jpeg" % str(ndx).rjust(8, "0"))
        if not os.path.exists(filename):
            return False
    return True

def get_fingerprint_ffmpeg(path, frame_nb, log_level=1):
    if path == None or path == '' or frame_nb == 0:
        return ''

    Path(os.path.join(data_path, "fingerprints/" + replace(path) + "/frames")).mkdir(parents=True, exist_ok=True)
    if not check_frames_already_exist(path, frame_nb):
        if not get_frames(path, frame_nb, log_level):
            if log_level > 0:
                print_debug('ffmpeg error')
            return ''
    elif log_level > 0:
        print_debug('skipping ffmpeg')
    
    start = datetime.now()
    video_fingerprint = ""
    for ndx in range(1, frame_nb + 1):
        filename = os.path.join(data_path, "fingerprints/" + replace(path) + "/frames/frame-%s.jpeg" % str(ndx).rjust(8, "0"))
        with Image.open(filename) as image:
            frame_fingerprint = str(imagehash.dhash(image))
            video_fingerprint += frame_fingerprint
    try:
        shutil.rmtree(os.path.join(data_path, "fingerprints/" + replace(path)  + "/frames"))
    except OSError as e:
        if log_level > 0:
            print_debug("Error: %s : %s" % (os.path.join(data_path, "fingerprints/" + replace(path) + "/frames"), e.strerror))
    end = datetime.now()
    if log_level > 0:
        print_debug("made hash in %s" % str(end - start))
    return video_fingerprint

def main(argv):

    dir = ''
    log_level = 0
    cleanup = False
    slow_mode = False
    try:
        opts, args = getopt.getopt(argv,"hi:dvc")
    except getopt.GetoptError:
        print_debug('decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode)\n')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_debug('decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode)\n')
            sys.exit()
        elif opt == '-i':
            dir = arg
        elif opt == '-d':
            log_level = 2
        elif opt == '-v':
            log_level = 1
        elif opt == '-c':
            cleanup = True
        elif opt == '-s':
            slow_mode = True

    if dir == '' or not os.path.isdir(dir):
        print_debug('decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode)\n')
        sys.exit(2)

    common_video_extensions = ['.webm', '.mkv', '.avi', '.mts', '.m2ts', '.ts', '.mov', '.wmv', '.mp4', '.m4v', '.mpg', '.mpeg', '.m2v' ]

    if os.path.isdir(dir):
        start = datetime.now()
        child_dirs = os.listdir(dir)
        for child in child_dirs:
            if child[0] == '.':
                continue
            matched_ext = False
            for ext in common_video_extensions:
                if child.endswith(ext):
                    matched_ext = True
            if matched_ext:
                max_fingerprint_mins = 10
                path = os.path.join(dir, child)
                video = cv2.VideoCapture(path)
                frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = video.get(cv2.CAP_PROP_FPS)
                quarter_frames_or_first_X_mins = min(int(frames / 4), int(fps * 60 * max_fingerprint_mins))
                video.release()
                result = get_fingerprint_ffmpeg(path, quarter_frames_or_first_X_mins)
        end = datetime.now()
        print_debug("total runtime %s" % str(end - start))
    else:
        print_debug('input directory invalid or cannot be accessed')
        return {}

if __name__ == "__main__":
   main(sys.argv[1:])
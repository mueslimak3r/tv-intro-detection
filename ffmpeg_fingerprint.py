import os
import re
import cv2
import imagehash
import shutil
import sys
import getopt
import subprocess

from pathlib import Path
from PIL import Image
from datetime import datetime

config_path = Path(os.environ['CONFIG_DIR']) if 'CONFIG_DIR' in os.environ else Path(Path.cwd() / 'config')
data_path = Path(os.environ['DATA_DIR']) if 'DATA_DIR' in os.environ else Path(config_path / 'data')

session_timestamp = datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p")


def print_debug(a=[], log=True, log_file=False):
    # Here a is the array holding the objects
    # passed as the argument of the function
    output = ' '.join([str(elem) for elem in a])
    if log:
        print(output, file=sys.stderr)
    if log_file:
        log_path = config_path / 'logs'
        log_path.mkdir(parents=True, exist_ok=True)
        with (log_path / ('log_%s.txt' % session_timestamp)).open('a') as logger:
            logger.write(output + '\n')


def replace(s):
    return re.sub('[^A-Za-z0-9]+', '', s)


def get_frames(path, frame_nb, log_level, log_file):
    if path is None or path == '' or frame_nb == 0:
        return False
    print_debug(a=['running ffmpeg'], log=log_level > 0, log_file=log_file)
    start = datetime.now()
    filename = Path(data_path / 'fingerprints' / replace(path) / '/frames/frame-%08d.jpeg')
    with Path(os.devnull).open('w') as fp:
        process = subprocess.Popen(args=["ffmpeg", "-i", path, "-frames:v", str(frame_nb), "-s", "384x216", filename.absolute()], stdout=fp, stderr=fp)
        process.wait()
        end = datetime.now()
        print_debug(a=["ran ffmpeg in %s" % str(end - start)], log=log_level > 0, log_file=log_file)
        return process.returncode == 0


def check_frames_already_exist(path, frame_nb):
    for ndx in range(1, frame_nb + 1):
        filename = Path(data_path / 'fingerprints' / replace(path) / 'frames' / ('frame-%s.jpeg' % str(ndx).rjust(8, '0')))
        if not filename.exists():
            return False
    return True


def get_fingerprint_ffmpeg(path, frame_nb, log_level=1, log_file=False, log_timestamp=None):
    global session_timestamp

    if path is None or path == '' or frame_nb == 0:
        return ''

    if log_timestamp is not None:
        session_timestamp = log_timestamp

    Path(data_path / 'fingerprints' / replace(path) / 'frames').mkdir(parents=True, exist_ok=True)
    if not check_frames_already_exist(path, frame_nb):
        if not get_frames(path, frame_nb, log_level, log_file):
            print_debug(a=['ffmpeg error'], log=log_level > 0, log_file=log_file)
            return ''
    else:
        print_debug(a=['skipping ffmpeg'], log=log_level > 0, log_file=log_file)
    
    start = datetime.now()
    video_fingerprint = ""
    for ndx in range(1, frame_nb + 1):
        filename = Path(data_path / 'fingerprints' / replace(path) / 'frames' / ('frame-%s.jpeg' % str(ndx).rjust(8, '0')))
        if not filename.exists():
            print_debug(a=["Error - Possible Corruption - frame file missing: %s for video %s" % (filename, path)], log=log_level > 0, log_file=log_file)
            break
        try:
            with Image.open(filename) as image:
                frame_fingerprint = str(imagehash.dhash(image))
                video_fingerprint += frame_fingerprint
        except BaseException as err:
            print_debug(a=["Error - Possible Corruption - frame file error: %s : %s" % (filename, err.strerror)], log=log_level > 0, log_file=log_file)
            break
    try:
        shutil.rmtree(Path(data_path / 'fingerprints' / replace(path) / 'frames'))
    except OSError as e:
        print_debug(a=["Error: %s : %s" % (Path(data_path / 'fingerprints' / replace(path) / 'frames'), e.strerror)], log=log_level > 0, log_file=log_file)
    end = datetime.now()
    print_debug(a=["made hash in %s" % str(end - start)], log=log_level > 0, log_file=log_file)
    return video_fingerprint


def main(argv):

    dir = ''
    log_level = 0
    cleanup = False
    slow_mode = False
    try:
        opts, args = getopt.getopt(argv, "hi:dvc")
    except getopt.GetoptError:
        print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode)\n'])
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode)\n'])
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

    if dir == '' or not Path(dir).is_dir():
        print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode)\n'])
        sys.exit(2)

    common_video_extensions = ['.webm', '.mkv', '.avi', '.mts', '.m2ts', '.ts', '.mov', '.wmv', '.mp4', '.m4v', '.mpg', '.mpeg', '.m2v']

    if Path(dir).is_dir():
        start = datetime.now()
        for child in Path(dir).iterdir():
            if child.name[0] == '.':
                continue
            matched_ext = False
            for ext in common_video_extensions:
                if child.name.endswith(ext):
                    matched_ext = True
            if matched_ext:
                max_fingerprint_mins = 10
                path = str(child.resolve())
                video = cv2.VideoCapture(path)
                frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
                fps = video.get(cv2.CAP_PROP_FPS)
                quarter_frames_or_first_X_mins = min(int(frames / 4), int(fps * 60 * max_fingerprint_mins))
                video.release()
                result = get_fingerprint_ffmpeg(path, quarter_frames_or_first_X_mins)
        end = datetime.now()
        print_debug(["total runtime %s" % str(end - start)])
    else:
        print_debug(['input directory invalid or cannot be accessed'])
        return {}


if __name__ == "__main__":
    main(sys.argv[1:])

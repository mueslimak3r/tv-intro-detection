import os
import re
import cv2
import imagehash
import sys
import getopt
from subprocess import Popen, PIPE, SubprocessError

from pathlib import Path
from PIL import Image
from datetime import datetime

config_path = Path(os.environ['CONFIG_DIR']) if 'CONFIG_DIR' in os.environ else Path(Path.cwd() / 'config')
data_path = Path(os.environ['DATA_DIR']) if 'DATA_DIR' in os.environ else Path(config_path / 'data')

session_timestamp = datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p")

img_extension = '.jpeg'
img_size = (384, 216)


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


def write_fingerprint(path, fingerprint):
    Path(data_path / 'fingerprints' / replace(str(path))).mkdir(parents=True, exist_ok=True)
    path = Path(data_path / 'fingerprints' / replace(str(path)) / 'fingerprint.txt')
    with path.open('w+') as text_file:
        text_file.write(fingerprint)


def replace(s):
    return re.sub('[^A-Za-z0-9]+', '', s)


def get_frames(path, hash_fps, frame_nb, log_level, log_file):
    if path is None or path == '' or frame_nb == 0:
        return False
    print_debug(a=['running ffmpeg'], log=log_level > 0, log_file=log_file)
    start = datetime.now()

    command = ["ffmpeg", "-i", path, "-vf", 'fps=%s' % str(hash_fps), "-frames:v", str(frame_nb), "-f", "image2pipe", "-pix_fmt", "rgb24", "-vcodec", "rawvideo", "-s", "384x216", "-"]

    with Path(os.devnull).open('w') as devnull_fp:
        proc = Popen(command, stdout=PIPE, stderr=devnull_fp, bufsize=10**8)

        filein = proc.stdout
        bytes_list = []
        for _ in range(frame_nb):
            try:
                output = filein.read(img_size[0] * img_size[1] * 3)
            except SubprocessError as err:
                filein.close()
                proc.kill()
                return [], False
            bytes_list.append(output)
        filein.close()
        proc.wait()
        end = datetime.now()
        print_debug(a=["ran ffmpeg in %s" % str(end - start)], log=log_level > 0, log_file=log_file)
        return bytes_list, proc.returncode == 0


def get_fingerprint_ffmpeg(path, hash_fps, frame_nb, log_level=1, log_file=False, log_timestamp=None):
    global session_timestamp

    if path is None or path == '' or frame_nb == 0:
        return []

    if log_timestamp is not None:
        session_timestamp = log_timestamp

    bytes_list, ret = get_frames(path, hash_fps, frame_nb, log_level, log_file)

    if not bytes_list or not ret:
        print_debug(a=['ffmpeg error'], log=log_level > 0, log_file=log_file)
        return []

    fingerprint_str = ""
    fingerprint_list = []

    start = datetime.now()
    ndx = 0
    for frame_bytes in bytes_list:
        img = Image.frombytes('RGB', img_size, frame_bytes)
        frame_fingerprint = imagehash.dhash(img)
        fingerprint_str += str(frame_fingerprint)
        fingerprint_list.append(frame_fingerprint)
        ndx += 1

    if fingerprint_str != '':
        write_fingerprint(path, fingerprint_str)
    end = datetime.now()
    print_debug(a=["made hash in %s" % str(end - start)], log=log_level > 0, log_file=log_file)
    return fingerprint_list


def main(argv):

    dir = ''
    log_level = 0
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
                result = get_fingerprint_ffmpeg(path, quarter_frames_or_first_X_mins, log_level, True, None)
        end = datetime.now()
        print_debug(["total runtime %s" % str(end - start)])
    else:
        print_debug(['input directory invalid or cannot be accessed'])
        return {}


if __name__ == "__main__":
    main(sys.argv[1:])

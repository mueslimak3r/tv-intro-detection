import re
import sys
from datetime import datetime
from os import path
from pathlib import Path

import cv2
import imagehash
import numpy
from PIL import Image


def dict_by_value(dict, value):
    for name, age in dict.items():
        if age == value:
            return name


def write_fingerprint(path, fingerprint):
    path = "fingerprints/" + replace(path) + "/fingerprint.txt"
    with open(path, "w+") as text_file:
        text_file.write(fingerprint)


def replace(s):
    return re.sub('[^A-Za-z0-9]+', '', s)


def create_video_fingerprint(path):
    video_fingerprint = ""
    video = cv2.VideoCapture(path)
    fps = video.get(cv2.CAP_PROP_FPS)
    success, frame = video.read()
    count = 0
    Path("fingerprints/" + replace(path) + "/frames").mkdir(parents=True, exist_ok=True)
    while count < int(300.0 * fps) + 1:
        if True:
            cv2.imwrite("fingerprints/" + replace(path) + "/frames/frame%d.jpg" % count, frame)
        image = Image.fromarray(numpy.uint8(frame))
        frame_fingerprint = str(imagehash.dhash(image))
        video_fingerprint += frame_fingerprint
        if count % 1000 == 0:
            print(path + " " + str(count) + "/" + str(int(300.0 * fps) + 1))
        success, frame = video.read()
        count += sample_frame
    return video_fingerprint


def get_equal_frames(print1, print2):
    equal_frames = []
    count = 0
    while min(len(print1), len(print2)) > count:
        if print1[count] == print2[count]:
            equal_frames.append(print1[count])
        count += 1
    return equal_frames


def tokenize_fingerprints(video_fingerprints):
    unique_prints = set()
    for fingerprint in video_fingerprints:
        for frame_print in re.findall("................", fingerprint):
            unique_prints.add(frame_print)
    matrix = {}
    counter = 60
    for unique_print in unique_prints:
        matrix[unique_print] = chr(counter)
        counter += 1
    tokenprints = []
    for fingerprint in video_fingerprints:
        t = fingerprint
        for key in matrix.items():
            t = t.replace(key[0], str(key[1]))
        tokenprints.append(t.replace(".", ""))
    return tokenprints, matrix


def get_start_end(print1, print2):
    offset = len(print1)
    highest_equal_frames = []
    for i in range(0, offset):
        equal_frames = get_equal_frames(print1[-i:], print2)
        if len(equal_frames) > len(highest_equal_frames):
            highest_equal_frames = equal_frames
    for i in range(0, offset):
        equal_frames = get_equal_frames(print1, print2[i:])
        if len(equal_frames) > len(highest_equal_frames):
            highest_equal_frames = equal_frames
    p = re.compile(".*?".join(highest_equal_frames))
    search = re.search(p, print1)
    search2 = re.search(p, print2)
    return (search.start(), search.end()), (search2.start(), search2.end())


def for_files(files):
    fingerprints = []
    for file in files:
        if path.exists("fingerprints/" + replace(file) + "/fingerprint.txt"):
            print(file + " fingerprint exists - loading it")
            with open("fingerprints/" + replace(file) + "/fingerprint.txt", "r") as text_file:
                fingerprint = text_file.read()
        else:
            print(file + " fingerprint does not exist - creating it")
            fingerprint = create_video_fingerprint(file)
            write_fingerprint(file, fingerprint)
        fingerprints.append(fingerprint)
    tokens, matrix = tokenize_fingerprints(fingerprints)
    #todo use files list to calculate entries and display. temp only
    print(str(get_start_end(tokens[0], tokens[1])))
    print(str(get_start_end(tokens[2], tokens[3])))
    print(str(get_start_end(tokens[4], tokens[3])))


print(datetime.now())
seconds_from_start = 300  # 5 minuets
# take every X frame
# 1 works the best
# 2 sometimes works as good as 1 but not always
# 3 and further not tested
sample_frame = 1
paths = [
]
for_files(paths)
print(datetime.now())

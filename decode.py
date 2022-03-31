import re
import os
import cv2
import imagehash
import shutil
import numpy
import json
import hashlib
from math import floor
import sys, getopt

from time import sleep
from concurrent.futures import ThreadPoolExecutor, process
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
import pandas

from ffmpeg_fingerprint import get_fingerprint_ffmpeg

FIRST = 0
SECOND = 1
BOTH = 2

config_path = os.environ['CONFIG_DIR'] if 'CONFIG_DIR' in os.environ else './config'
data_path = os.environ['DATA_DIR'] if 'DATA_DIR' in os.environ else os.path.join(config_path, 'data')

preroll_seconds = 0 # adjust the end time to return n seconds prior to the calculated end time
                    # jellyfin_auto_skip.py also handles pre-roll so adjust it there
                    # adjusting it here bakes the pre-rolled value into the result
max_fingerprint_mins = 10
min_intro_length_sec = 10
max_intro_length_sec = 180
check_frame = 10  # 1 (slow) to 10 (fast) is fine 
workers = 4 # number of executors to use
target_image_height = 180 # scale frames to height of 180px

def print_debug(*a):
    # Here a is the array holding the objects
    # passed as the argument of the function
    print(*a, file = sys.stderr)

def dict_by_value(dict, value):
    for name, age in dict.items():
        if age == value:
            return name

def write_fingerprint(path, fingerprint):
    path = os.path.join(data_path, "fingerprints/" + replace(path) + "/fingerprint.txt")
    with open(path, "w+") as text_file:
        text_file.write(fingerprint)

def replace(s):
    return re.sub('[^A-Za-z0-9]+', '', s)

def print_timestamp(name, start_frame, end_frame, fps):
    start_time = 0 if start_frame == 0 else round(start_frame / fps)
    end_time = 0 if end_frame == 0 else round(end_frame / fps)

    print_debug('[%s] has start %s end %s' % (name, str(timedelta(seconds=start_time)).split('.')[0], str(timedelta(seconds=end_time)).split('.')[0]))

def get_timestamp_from_frame(profile):
    start_time = 0 if profile['start_frame'] == 0 else round(profile['start_frame'] / profile['fps'])
    end_time = 0 if profile['end_frame'] == 0 else round(profile['end_frame'] / profile['fps'])

    profile['start_time_ms'] = start_time * 1000
    profile['end_time_ms'] = end_time * 1000
    profile['start_time'] = str(timedelta(seconds=start_time)).split('.')[0]
    profile['end_time'] = str(timedelta(seconds=end_time)).split('.')[0]

def create_video_fingerprint(profile, log_level):
    video_fingerprint = ''

    quarter_frames_or_first_X_mins = min(int(profile['total_frames'] / 4), int(profile['fps'] * 60 * max_fingerprint_mins))
    video_fingerprint = get_fingerprint_ffmpeg(profile['path'], quarter_frames_or_first_X_mins, log_level)

    if video_fingerprint == '':
        raise Exception("error creating fingerprint for video [%s]" % profile['path'])
    return video_fingerprint

def get_equal_frames(print1, print2):
    equal_frames = []
    for j in range(0, int(len(print1) / 16 / check_frame)):
        if print1[j * 16 * check_frame:j * 16 * check_frame + 16] == print2[
                                                                     j * 16 * check_frame:j * 16 * check_frame + 16]:
            equal_frames.append(print1[j * 16 * check_frame:j * 16 * check_frame + 16])
    return equal_frames

def get_start_end(print1, print2):
    highest_equal_frames = []
    for k in range(0, int(len(print1) / 16)):
        equal_frames = get_equal_frames(print1[-k * 16:], print2)
        if len(equal_frames) > len(highest_equal_frames):
            highest_equal_frames = equal_frames
        equal_frames = get_equal_frames(print1, print2[k * 16:])
        if len(equal_frames) > len(highest_equal_frames):
            highest_equal_frames = equal_frames
    regex_string = ".*?".join(highest_equal_frames) + "){1,}"
    regex_string = regex_string[:-21] + '(' + regex_string[-21:]
    p = re.compile(regex_string)
    search = re.search(p, "".join(print1))
    search2 = re.search(p, "".join(print2))
    return (int(search.start() / 16), int(search.end() / 16)), (int(search2.start() / 16), int(search2.end() / 16))

def get_or_create_fingerprint(file, cleanup, log_level):
    start = datetime.now()
    video = cv2.VideoCapture(file)
    fps = video.get(cv2.CAP_PROP_FPS)

    profile = {}
    profile['fps'] = fps
    profile['path'] = file
    profile['total_frames'] = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    video.release()

    if os.path.exists(os.path.join(data_path, "fingerprints/" + replace(file) + "/fingerprint.txt")):
        if log_level > 0:
            print_debug('loading existing fingerprint for [%s]' % file)
        with open(os.path.join(data_path, "fingerprints/" + replace(file) + "/fingerprint.txt"), "r") as text_file:
            fingerprint = text_file.read()
    else:
        if log_level > 0:
            print_debug('creating new fingerprint for [%s]' % file)
        
        fingerprint = create_video_fingerprint(profile, log_level)
        if not cleanup:
            write_fingerprint(file, fingerprint)
    
    end = datetime.now()
    if log_level > 0:
        print_debug("processed fingerprint for [%s] in %s" % (file, str(end - start)))
    return fingerprint, profile

def check_files_exist(file_paths = []):
    if not file_paths:
        return False
    for file in file_paths:
        if not os.path.exists(file):
            return False
    return True

def save_season_fingerprint(fingerprints, profiles, ndx, filtered_lengths, log_level):
    size = len(filtered_lengths)
    sum = 0
    for f in filtered_lengths:
        sum += f
    average = int(sum / size)

    name = ''
    for profile in profiles:
        name += replace(profile['path'])
    hash_object = hashlib.md5(name.encode())
    name = hash_object.hexdigest()

    season_fingerprint = {}
    season_fingerprint.update(profiles[ndx])
    season_fingerprint['fingerprint'] = fingerprints[ndx]
    season_fingerprint['average_frames'] = average
    season_fingerprint['average_sample_size'] = len(filtered_lengths)

    path = os.path.join(data_path, "fingerprints/" + name + ".json")
    Path(os.path.join(data_path, "fingerprints")).mkdir(parents=True, exist_ok=True)
    with open(path, "w+") as json_file:
        json.dump(season_fingerprint, json_file, indent = 4)


'''
def reject_outliers(data, m = 1.):
    if not isinstance(data, numpy.ndarray):
        data = numpy.array(data)
    d = numpy.abs(data - numpy.median(data))
    mdev = numpy.median(d)
    s = d / (mdev if mdev else 0.)
    output = data[s<m].tolist()

    # sometimes numpy tolist() returns a nested list
    if type(output[0]) == list:
        return output[0]
    return output
'''
def reject_outliers(input_list, iq_range=0.2):
    if not input_list:
        return input_list

    sr = pandas.Series(input_list, copy=True)
    pcnt = (1 - iq_range) / 2
    qlow, median, qhigh = sr.dropna().quantile([pcnt, 0.50, 1-pcnt])
    iqr = qhigh - qlow
    return sr[ (sr - median).abs() <= iqr].values.tolist()

def correct_errors(fingerprints, profiles, log_level):

    # build a list of intro lengths with outliers rejected
    lengths = []
    for profile in profiles:
        if profile['end_frame'] - profile['start_frame'] > 0 and profile['end_frame'] - profile['start_frame'] <= int(profile['fps'] * max_intro_length_sec):
            lengths.append(profile['end_frame'] - profile['start_frame'])
    filtered_lengths = reject_outliers(lengths)

    if len(filtered_lengths) < 1:
        for profile in profiles:
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        if log_level > 0:
            print_debug('failed to correct - could not establish consistency between episodes')
        return

    size = len(filtered_lengths)
    sum = 0
    for f in filtered_lengths:
        sum += f
    average = int(sum / size)

    if log_level > 0:
        print_debug('average length in frames [%s] from %s of %s files' % (average, len(filtered_lengths), len(profiles)))
        print_timestamp('average length (time)', 0, average, profiles[0]['fps'])

    # build a list of conforming and non conforming profiles (int indexes)
    # loop through profiles and check if their duration is in the filtered list of intro lengths
    conforming_profiles = []
    non_conforming_profiles = []
    for ndx in range(0, len(profiles)):
        diff_from_avg = abs(profiles[ndx]['end_frame'] - profiles[ndx]['start_frame'] - average)
        if log_level > 1:
            print_debug('file [%s] diff from average %s' % (profiles[ndx]['path'], diff_from_avg))
        if profiles[ndx]['end_frame'] - profiles[ndx]['start_frame'] in filtered_lengths or \
            diff_from_avg < int(15 * profiles[ndx]['fps']):

            conforming_profiles.append(ndx)
        else:
            print_debug('\nrejected file [%s] with start %s end %s' % (profiles[ndx]['path'], profiles[ndx]['start_frame'], profiles[ndx]['end_frame']))
            print_timestamp(profiles[ndx]['path'], profiles[ndx]['start_frame'], profiles[ndx]['end_frame'], profiles[ndx]['fps'])
            with open(os.path.join(data_path, 'rejects.txt'), "a") as logger:
                logger.write('rejected file [%s] diff from average %s start %s end %s average %s fps %s\n' % (profiles[ndx]['path'], diff_from_avg, profiles[ndx]['start_frame'], profiles[ndx]['end_frame'], average, profiles[ndx]['fps']))
            non_conforming_profiles.append(ndx)

    if log_level > 0:
        print_debug('\nrejected start frame values from %s of %s results\n' % (len(non_conforming_profiles), len(profiles)))

    if len(conforming_profiles) < 1:
        if log_level > 0:
            print_debug('all profiles were rejected')
        for profile in profiles:
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        return

    # sort the list of conforming profile indexes and find the mean value
    # this profile will be the reference profile used when repairing the rejected profiles
    conforming_profiles.sort()
    shortest_duration = profiles[conforming_profiles[0]]['end_frame'] - profiles[conforming_profiles[0]]['start_frame']
    if log_level > 0:
        print_debug('shortest duration %s from %s' % (shortest_duration, profiles[conforming_profiles[0]]['path']))
    ref_profile_ndx = conforming_profiles[int(floor(len(conforming_profiles) / 2))]

    save_season_fingerprint(fingerprints, profiles, ref_profile_ndx, filtered_lengths, log_level)

    if len(non_conforming_profiles) < 1:
        if log_level > 0:
            print_debug('no profiles were rejected!')
        return

    # reprocess the rejected profiles by comparing them to the reference profile
    for nprofile in non_conforming_profiles:
        if log_level > 0:
            print_debug('reprocessing %s by comparing to %s' % (profiles[nprofile]['path'], profiles[ref_profile_ndx]['path']))
        process_pairs(fingerprints, profiles, ref_profile_ndx, nprofile, SECOND, log_level)

    # repeat building a list of lengths and filtering them
    lengths = []
    for profile in profiles:
        lengths.append(profile['end_frame'] - profile['start_frame'])
    new_filtered_lengths = reject_outliers(lengths)
    
    # repeat checking each profile's duration against the new filtered list of lengths
    repaired = 0
    for nprofile in range(0, len(profiles)):
        diff_from_avg = abs(profiles[nprofile]['end_frame'] - profiles[nprofile]['start_frame'] - average)
        guessed_start = profiles[nprofile]['end_frame'] - shortest_duration
        if guessed_start < 0:
            guessed_start = 0
        guessed_start_diff = abs(profiles[nprofile]['end_frame'] - guessed_start - average)
        #print(shortest_duration, guessed_start, guessed_start_diff)
        if profiles[nprofile]['end_frame'] - profiles[nprofile]['start_frame'] in new_filtered_lengths and \
                diff_from_avg < int(15 * profiles[nprofile]['fps']):

            if nprofile in non_conforming_profiles:
                repaired += 1
                with open(os.path.join(data_path, 'rejects.txt'), "a") as logger:
                    logger.write('rejected file successfully reprocessed [%s] start %s end %s\n' % (profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame']))
                if log_level > 0:
                    print_debug('\nreprocess successful for file [%s] new start %s end %s' % (profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame']))
                    print_timestamp(profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'], profiles[nprofile]['fps'])
        elif guessed_start_diff < int(15 * profiles[nprofile]['fps']):
            if nprofile in non_conforming_profiles:
                repaired += 1
                profiles[nprofile]['start_frame'] = guessed_start
                with open(os.path.join(data_path, 'rejects.txt'), "a") as logger:
                    logger.write('reprocess successful by guessing start for file [%s] - start %s end %s\n' % (profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame']))
                if log_level > 0:
                    print_debug('\nreprocess successful by guessing start for file [%s] - new start %s end %s' % (profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame']))
                    print_timestamp(profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'], profiles[nprofile]['fps'])
        else:
            if nprofile in non_conforming_profiles:
                if log_level > 0:
                    print_debug('\nfailed to locate intro by reprocessing %s' % profiles[nprofile]['path'])
                    print_debug('file [%s] new start %s end %s' % (profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame']))
                    print_timestamp(profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'], profiles[nprofile]['fps'])
                with open(os.path.join(data_path, 'rejects.txt'), "a") as logger:
                    logger.write('rejected file failed to be reprocessed [%s] start %s end %s\n' % (profiles[nprofile]['path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame']))
                profiles[nprofile]['start_frame'] = 0
                profiles[nprofile]['end_frame'] = 0
    if log_level > 0:
        print_debug('\nrepaired %s/%s non conforming profiles\n' % (repaired, len(non_conforming_profiles)))

    if len(non_conforming_profiles) > 0:
        with open(os.path.join(data_path, 'rejects.txt'), "a") as logger:
            logger.write('\n')

def process_pairs(fingerprints, profiles, ndx_1, ndx_2, mode, log_level):
    try:
        start_end = get_start_end(fingerprints[ndx_1], fingerprints[ndx_2])
        
        if mode == BOTH or mode == FIRST:
            profiles[ndx_1]['start_frame'] = start_end[0][0] - check_frame + 1
            if profiles[ndx_1]['start_frame'] < 0:
                profiles[ndx_1]['start_frame'] = 0
            profiles[ndx_1]['end_frame'] = start_end[0][1]
            if profiles[ndx_1]['end_frame'] < 0:
                profiles[ndx_1]['end_frame'] = 0

        if mode == BOTH or mode == SECOND:
            profiles[ndx_2]['start_frame'] = start_end[1][0] - check_frame + 1
            if profiles[ndx_2]['start_frame'] < 0:
                profiles[ndx_2]['start_frame'] = 0
            profiles[ndx_2]['end_frame'] = start_end[1][1]
            if profiles[ndx_2]['end_frame'] < 0:
                profiles[ndx_2]['end_frame'] = 0

    except:
        if log_level > 0:
            print_debug("could not compare fingerprints from files " + profiles[ndx_1]['path'] + " " + profiles[ndx_2]['path'])

def process_directory(file_paths = [], log_level=0, cleanup=True):
    start = datetime.now()
    if log_level > 0:
        print_debug('started at', start)
        print_debug("Check Frame: %s\n" % str(check_frame))
        if cleanup:
            print_debug('fingerprint files will be cleaned up')

    if not check_files_exist(file_paths):
        if log_level > 0:
            print_debug('input files invalid or cannot be accessed')
        return {}
    
    if len(file_paths) < 2:
        if log_level > 0:
            print_debug('file list size is less than 2 - skipping')
        return {}
    
    if log_level > 0:
        print_debug('processing %s files' % len(file_paths))
    
    if cleanup and os.path.isdir(os.path.join(data_path, 'fingerprints')):
        try:
            shutil.rmtree(os.path.join(data_path, 'fingerprints'))
        except OSError as e:
            print_debug("Error: %s : %s" % ('fingerprints', e.strerror))

    profiles = [] # list of dictionaries containing path, start/end frame & time, fps
    fingerprints = [] # list of hash values

    for file_path in file_paths:
        fingerprint, profile = get_or_create_fingerprint(file_path, cleanup, log_level)
        fingerprints.append(fingerprint)
        profiles.append(profile)

    counter = 0

    # loop through each pair and store the start/end frames in their profiles
    # then do the same for the remaining profile if count is odd
    #
    # use mode: FIRST, SECOND, BOTH to decide whether to save the values to the first, second, or both profiles
    # changing modes is useful for processing a new profile against one that's already processed
    # for instance, if a profile is rejected it could be reprocessed against a different profile without risking...
    # ...overwriting the the start/end frame values for the reference profile
    process_pairs_start = datetime.now()
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        while len(fingerprints) - 1 > counter:
            futures.append(executor.submit(process_pairs, fingerprints, profiles, counter, counter + 1, BOTH, log_level))
            counter += 2
        if (len(fingerprints) % 2) != 0:
            futures.append(executor.submit(process_pairs, fingerprints, profiles, -2, -1, SECOND, log_level))
        for future in futures:
            future.result()
    process_pairs_end = datetime.now()
    if log_level > 0:
        print_debug("processed fingerprint pairs in: " + str(process_pairs_end - process_pairs_start))

    correct_errors_start = datetime.now()
    correct_errors(fingerprints, profiles, log_level)
    correct_errors_end = datetime.now()
    if log_level > 0:
        print_debug("finished error correction in: " + str(correct_errors_end - correct_errors_start))

    # finally, automatically reject episodes with intros shorted than a specified length (default 15 seconds)
    # apply pre-roll if wanted
    # use the fps and start/end frame values to calculate the timestamps for the intros and add them to the profiles
    for profile in profiles:
        if profile['end_frame'] - profile['start_frame'] < int(min_intro_length_sec * profile['fps']):
            if log_level > 1:
                print_debug('%s - intro is less than %s seconds - skipping' % (profile['path'], min_intro_length_sec))
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        elif preroll_seconds > 0 and profile['end_frame'] > profile['start_frame'] + int(profile['fps'] * preroll_seconds):
            profile['end_frame'] -= int(profile['fps'] * preroll_seconds)
        get_timestamp_from_frame(profile)
        if log_level > 1:
            print_debug(profile['path'] + " start time: " + profile['start_time'] + " end time: " + profile['end_time'])

    end = datetime.now()
    if log_level > 0:
        print_debug("ended at", end)
        print_debug("duration: " + str(end - start))

    if cleanup and os.path.isdir(os.path.join(data_path, 'fingerprints')):
        try:
            shutil.rmtree(os.path.join(data_path, 'fingerprints'))
        except OSError as e:
            print_debug("Error: %s : %s" % ('fingerprints', e.strerror))
    return profiles

def main(argv):

    path = ''
    log_level = 0
    cleanup = False
    slow_mode = False
    use_ffmpeg = True
    try:
        opts, args = getopt.getopt(argv,"hi:dvcl")
    except getopt.GetoptError:
        print_debug('decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode) -l (legacy mode - dont use ffmpeg)\n')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_debug('decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode) -l (legacy mode - dont use ffmpeg)\n')
            sys.exit()
        elif opt == '-i':
            path = arg
        elif opt == '-l':
            use_ffmpeg = False
        elif opt == '-d':
            log_level = 2
        elif opt == '-v':
            log_level = 1
        elif opt == '-c':
            cleanup = True
        elif opt == '-s':
            slow_mode = True

    if path == '' or not os.path.isdir(path):
        print_debug('decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode) -l (legacy mode - dont use ffmpeg)\n')
        sys.exit(2)

    common_video_extensions = ['.webm', '.mkv', '.avi', '.mts', '.m2ts', '.ts', '.mov', '.wmv', '.mp4', '.m4v', '.mpg', '.mpeg', '.m2v' ]

    file_paths = []
    if os.path.isdir(path):
        child_dirs = os.listdir(path)
        for child in child_dirs:
            if child[0] == '.':
                continue
            matched_ext = False
            for ext in common_video_extensions:
                if child.endswith(ext):
                    matched_ext = True
            if matched_ext:
                file_paths.append(os.path.join(path, child))
        file_paths.sort()
    else:
        print_debug('input directory invalid or cannot be accessed')

    result = process_directory(file_paths=file_paths, log_level=log_level, cleanup=cleanup)
    print(result)

if __name__ == "__main__":
   main(sys.argv[1:])

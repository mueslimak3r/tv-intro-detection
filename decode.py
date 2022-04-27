import os
import re
import sys
import getopt
import shutil
import json
import cv2
import hashlib
import pandas
import imagehash

from math import floor
from datetime import datetime, timedelta
from pathlib import Path

from ffmpeg_fingerprint import get_fingerprint_ffmpeg

FIRST = 0
SECOND = 1
BOTH = 2

config_path = Path(os.environ['CONFIG_DIR']) if 'CONFIG_DIR' in os.environ else Path(Path.cwd() / 'config')
data_path = Path(os.environ['DATA_DIR']) if 'DATA_DIR' in os.environ else Path(config_path / 'data')

preroll_seconds = 0     # adjust the end time to return n seconds prior to the calculated end time
                        # jellyfin_auto_skip.py also handles pre-roll so adjust it there
                        # adjusting it here bakes the pre-rolled value into the result
max_fingerprint_mins = 10
min_intro_length_sec = 10
max_intro_length_sec = 180
workers = 4  # number of executors to use
target_image_height = 180  # scale frames to height of 180px

check_frame = 1  # check_frame should be 1 if hash_fps is lower than video fps
hash_fps = 2

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


def dict_by_value(dict, value):
    for name, age in dict.items():
        if age == value:
            return name


def write_fingerprint(path, fingerprint):
    path = Path(data_path / 'fingerprints' / replace(path) / 'fingerprint.txt')
    with path.open('w+') as text_file:
        text_file.write(fingerprint)


def replace(s):
    return re.sub('[^A-Za-z0-9]+', '', s)


def print_timestamp(name, start_frame, end_frame, fps, log_level, log_file):
    start_time = 0 if start_frame == 0 else round(start_frame / fps)
    end_time = 0 if end_frame == 0 else round(end_frame / fps)

    print_debug(a=['[%s] has start %s end %s' % (name, str(timedelta(seconds=start_time)).split('.')[0], str(timedelta(seconds=end_time)).split('.')[0])], log=log_level > 0, log_file=log_file)


def get_timestamp_from_frame(profile):
    start_time = 0 if profile['start_frame'] == 0 else profile['start_frame'] / profile['fps']
    end_time = 0 if profile['end_frame'] == 0 else profile['end_frame'] / profile['fps']

    profile['start_time_ms'] = floor(start_time * 1000)
    profile['end_time_ms'] = floor(end_time * 1000)
    profile['start_time'] = str(timedelta(seconds=floor(start_time))).split('.')[0]
    profile['end_time'] = str(timedelta(seconds=floor(end_time))).split('.')[0]


def create_video_fingerprint(profile, hashfps, log_level, log_file):
    video_fingerprint = []

    quarter_frames_or_first_X_mins = min(floor(((profile['total_frames'] / profile['fps']) / 4) * hashfps), floor(max_fingerprint_mins * 60 * hashfps))
    video_fingerprint = get_fingerprint_ffmpeg(profile['Path'], hashfps, quarter_frames_or_first_X_mins, log_level, log_file, session_timestamp, True)

    return video_fingerprint


def get_equal_frames(print1, print2, start1, start2):
    equal_frames = []

    search_range = floor(min(len(print1), len(print2)) / check_frame)

    for j in range(0, search_range):
        frame1 = print1[j * check_frame]
        frame2 = print2[j * check_frame]
        if frame1 - frame2 < 8:
            equal_frames.append((int(start1 + (j * check_frame)), int(start2 + (j * check_frame))))

    return equal_frames


def get_start_end(print1, print1_fps, print2, print2_fps, log_level):
    if not print1 or not print2:
        return (0, 0), (0, 0)
    
    shortest_len = min(len(print1), len(print2))

    if len(print2) == shortest_len:
        longest = print1
        shortest = print2
        swap = False
    else:
        longest = print2
        shortest = print1
        swap = True
    print_debug(a=['swapped %s' % swap], log=log_level > 1)

    highest_equal_frames = []
    for k in range(1, len(longest)):
        equal_frames = get_equal_frames(longest[-k:], shortest, len(longest) - k, 1)
        if len(equal_frames) > len(highest_equal_frames):
            highest_equal_frames = equal_frames

        if k < len(shortest):
            equal_frames = get_equal_frames(longest, shortest[k:], 1, k)
            if len(equal_frames) > len(highest_equal_frames):
                highest_equal_frames = equal_frames

    if highest_equal_frames:
        if swap:
            return (floor(highest_equal_frames[0][1] * (print2_fps / hash_fps)), floor(highest_equal_frames[-1][1] * (print2_fps / hash_fps))), (floor(highest_equal_frames[0][0] * (print1_fps / hash_fps)), floor(highest_equal_frames[-1][0] * (print1_fps / hash_fps)))
        else:
            return (floor(highest_equal_frames[0][0] * (print1_fps / hash_fps)), floor(highest_equal_frames[-1][0] * (print1_fps / hash_fps))), (floor(highest_equal_frames[0][1] * (print2_fps / hash_fps)), floor(highest_equal_frames[-1][1] * (print2_fps / hash_fps)))
    else:
        return (0, 0), (0, 0)


def read_fingerprint(fingerprint_str, log_level, log_file):
    fingerprint = []
    if fingerprint_str != '' and len(fingerprint_str) % 16 == 0:
        try:
            for ndx in range(0, floor(len(fingerprint_str) / 16)):
                fingerprint.append(imagehash.hex_to_hash(fingerprint_str[ndx * 16:ndx * 16 + 16]))
            print_debug(a=['fingerprint looks valid'], log=log_level > 1, log_file=log_file)
        except BaseException as err:
            print_debug(a=['error reading season fingerprint'], log=log_level > 0, log_file=log_file)
            fingerprint = []
    return fingerprint


def read_fingerprint_file(file, log_level, log_file):
    if not Path(file).exists():
        return []

    fingerprint = []
    print_debug(a=['loading existing fingerprint for [%s]' % file], log=log_level > 1, log_file=log_file)
    with Path(data_path / 'fingerprints' / replace(file) / 'fingerprint.txt').open('r') as text_file:
        fingerprint_str = text_file.read()
        read_fingerprint(fingerprint_str, log_level, log_file)
    return fingerprint


def get_or_create_fingerprint(profile, log_level, log_file):
    start = datetime.now()
    video = cv2.VideoCapture(profile['Path'])
    fps = video.get(cv2.CAP_PROP_FPS)

    profile['fps'] = fps
    profile['total_frames'] = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    video.release()

    fingerprint = []

    if Path(data_path / 'fingerprints' / replace(profile['Path']) / 'fingerprint.txt').exists():
        fingerprint = read_fingerprint_file(Path(data_path / 'fingerprints' / replace(profile['Path']) / 'fingerprint.txt'), log_level, log_file)
    
    if not fingerprint:
        print_debug(a=['creating new fingerprint for [%s]' % profile['Path']], log=log_level > 1, log_file=log_file)
        fingerprint = create_video_fingerprint(profile, hash_fps, log_level, log_file)

    end = datetime.now()
    print_debug(a=["processed fingerprint in %s for [%s]" % (str(end - start), profile['Path'])], log=log_level > 0, log_file=log_file)
    return fingerprint


def check_files_exist(profiles=[]):
    if not profiles:
        return False
    for p in profiles:
        if 'Path' not in p or not Path(p['Path']).exists():
            return False
    return True


def save_season_fingerprint(fingerprints, profiles, ndx, filtered_lengths, shortest_duration):
    size = len(filtered_lengths)
    sum = 0
    for f in filtered_lengths:
        sum += f
    average = int(sum / size)

    name = ''
    for profile in profiles:
        name += replace(profile['Path'])
    hash_object = hashlib.md5(name.encode())
    name = hash_object.hexdigest()

    season_fingerprint = {}
    season_fingerprint.update(profiles[ndx])

    tmp_start_frame = floor(profiles[ndx]['start_frame'] / (profiles[ndx]['fps'] / hash_fps)) if profiles[ndx]['start_frame'] > 0 else 0
    tmp_end_frame = floor(profiles[ndx]['end_frame'] / (profiles[ndx]['fps'] / hash_fps)) if profiles[ndx]['end_frame'] > 0 else 0

    trimmed_fingerprint = fingerprints[ndx][tmp_start_frame:tmp_end_frame + 1]

    fingerprint_str = ''
    for f in trimmed_fingerprint:
        fingerprint_str += str(f)

    season_fingerprint['fingerprint'] = fingerprint_str
    season_fingerprint['reference_duration'] = shortest_duration
    season_fingerprint['average_frames'] = average
    season_fingerprint['average_sample_size'] = len(filtered_lengths)
    season_fingerprint['hash_fps'] = hash_fps

    path = Path(data_path / 'fingerprints' / (name + '.json'))
    Path(data_path / 'fingerprints').mkdir(parents=True, exist_ok=True)
    with path.open('w+') as json_file:
        json.dump(season_fingerprint, json_file, indent=4)


def intro_duration(profile):
    intro_duration = profile['end_frame'] - profile['start_frame']
    if intro_duration < 0:
        intro_duration = 0
    return intro_duration


def reject_outliers(input_list, iq_range=0.2):
    if not input_list:
        return input_list

    sr = pandas.Series(input_list, copy=True)
    pcnt = (1 - iq_range) / 2
    qlow, median, qhigh = sr.dropna().quantile([pcnt, 0.50, 1 - pcnt])
    iqr = qhigh - qlow
    return sr[(sr - median).abs() <= iqr].values.tolist()


def sort_conforming_profile(profile_tuple):
    return profile_tuple[1]


def correct_errors(fingerprints, profiles, ref_profile, log_level=0, log_file=False):

    # build a list of intro lengths with outliers rejected
    lengths = []
    for profile in profiles:
        if intro_duration(profile) <= int(profile['fps'] * max_intro_length_sec) and \
                intro_duration(profile) > int(profile['fps'] * 2):

            lengths.append(intro_duration(profile))
        else:
            print_debug(a=['excluding profile from pool of durations due to it being to long or short %s start %s end %s' % (profile['Path'], profile['start_frame'], profile['end_frame'])], log=log_level > 1, log_file=log_file)
            print_timestamp(profile['Path'], profile['start_frame'], profile['end_frame'], profile['fps'], log_level, log_file)
    filtered_lengths = reject_outliers(lengths)

    if len(filtered_lengths) < 1:
        for profile in profiles:
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        print_debug(a=['failed to correct - could not establish consistency between episodes'], log=log_level > 0, log_file=log_file)
        return

    size = len(filtered_lengths)
    sum = 0
    for f in filtered_lengths:
        sum += f
    average = int(sum / size)

    print_debug(a=['average length in frames [%s] from %s of %s files' % (average, len(filtered_lengths), len(profiles))], log=log_level > 0, log_file=log_file)
    print_timestamp('average length (time)', 0, average, profiles[0]['fps'], log_level, log_file)

    if average == 0 or int(round(average / profiles[0]['fps'])) < min_intro_length_sec:
        for profile in profiles:
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        print_debug(a=['skipping profiles - average duration is too short'], log=log_level > 0, log_file=log_file)
        return

    # build a list of conforming and non conforming profiles (int indexes)
    # loop through profiles and check if their duration is in the filtered list of intro lengths
    conforming_profiles = []
    non_conforming_profiles = []
    for ndx in range(0, len(profiles)):
        diff_from_avg = abs(intro_duration(profiles[ndx]) - average)
        print_debug(a=['file [%s] diff from average %s' % (profiles[ndx]['Path'], diff_from_avg)], log=log_level > 1, log_file=log_file)
        if intro_duration(profiles[ndx]) in filtered_lengths or \
                diff_from_avg < int(15 * profiles[ndx]['fps']):
            conforming_profiles.append((ndx, intro_duration(profiles[ndx])))
        else:
            print_debug(a=['\nrejected file [%s] with start %s end %s' % (profiles[ndx]['Path'], profiles[ndx]['start_frame'], profiles[ndx]['end_frame'])], log_file=log_file)
            print_timestamp(profiles[ndx]['Path'], profiles[ndx]['start_frame'], profiles[ndx]['end_frame'], profiles[ndx]['fps'], log_level, log_file)
            non_conforming_profiles.append(ndx)

    print_debug(a=['\nrejected start frame values from %s of %s results\n' % (len(non_conforming_profiles), len(profiles))], log=log_level > 0, log_file=log_file)

    if len(conforming_profiles) < 1:
        print_debug(a=['all profiles were rejected'], log=log_level > 0, log_file=log_file)
        for profile in profiles:
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        return

    # sort the list of conforming profile indexes and find the mean value
    # this profile will be the reference profile used when repairing the rejected profiles
    conforming_profiles.sort(key=sort_conforming_profile)
    shortest_duration = intro_duration(profiles[conforming_profiles[0][0]])
    print_debug(a=['shortest duration %s from %s' % (shortest_duration, profiles[conforming_profiles[0][0]]['Path'])], log=log_level > 0, log_file=log_file)
    ref_profile_ndx = conforming_profiles[int(floor(len(conforming_profiles) / 2))][0]

    if ref_profile is None:
        print_debug(a=['saving season fingerprint'], log=log_level > 0, log_file=log_file)
        save_season_fingerprint(fingerprints, profiles, ref_profile_ndx, filtered_lengths, shortest_duration)

    if len(non_conforming_profiles) < 1:
        print_debug(a=['no profiles were rejected!'], log=log_level > 0, log_file=log_file)
        return

    # reprocess the rejected profiles by comparing them to the reference profile
    for nprofile in non_conforming_profiles:
        print_debug(a=['reprocessing %s by comparing to %s' % (profiles[nprofile]['Path'], profiles[ref_profile_ndx]['Path'])], log=log_level > 0, log_file=log_file)
        tmp_profile = {}
        tmp_profile.update(profiles[ref_profile_ndx])
        tmp_index = len(fingerprints) - 1

        if ref_profile is None or profiles[ref_profile_ndx]['Path'] == ref_profile['Path']:
            tmp_start_frame = floor(profiles[ref_profile_ndx]['start_frame'] / (profiles[ref_profile_ndx]['fps'] / hash_fps)) if profiles[ref_profile_ndx]['start_frame'] > 0 else 0
            tmp_end_frame = floor(profiles[ref_profile_ndx]['end_frame'] / (profiles[ref_profile_ndx]['fps'] / hash_fps)) if profiles[ref_profile_ndx]['end_frame'] > 0 else 0
            fingerprints.append(fingerprints[ref_profile_ndx][tmp_start_frame:tmp_end_frame + 1])
        else:
            fingerprints.append(fingerprints[ref_profile_ndx])
        profiles.append(tmp_profile)

        print_timestamp(profiles[tmp_index]['Path'], profiles[tmp_index]['start_frame'], profiles[tmp_index]['end_frame'], profiles[tmp_index]['fps'], log_level, log_file)

        process_pairs(fingerprints, profiles, tmp_index, nprofile, SECOND, log_level, log_file)
        profiles.pop()
        fingerprints.pop()

    # repeat building a list of lengths and filtering them
    lengths = []
    for profile in profiles:
        lengths.append(intro_duration(profile))
    new_filtered_lengths = reject_outliers(lengths)
    
    # repeat checking each profile's duration against the new filtered list of lengths
    repaired = 0
    for nprofile in range(0, len(profiles)):
        diff_from_avg = abs(intro_duration(profiles[nprofile]) - average)
        guessed_start = profiles[nprofile]['end_frame'] - shortest_duration
        if guessed_start < 0:
            guessed_start = 0
        guessed_start_diff = abs(profiles[nprofile]['end_frame'] - guessed_start - average)
        if intro_duration(profiles[nprofile]) in new_filtered_lengths and \
                diff_from_avg < int(15 * profiles[nprofile]['fps']):
            if nprofile in non_conforming_profiles:
                repaired += 1
                print_debug(a=['\nreprocess successful for file [%s] new start %s end %s' % (profiles[nprofile]['Path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'])], log=log_level > 0, log_file=log_file)
                print_timestamp(profiles[nprofile]['Path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'], profiles[nprofile]['fps'], log_level, log_file)
        elif guessed_start_diff < int(15 * profiles[nprofile]['fps']):
            if nprofile in non_conforming_profiles:
                repaired += 1
                profiles[nprofile]['start_frame'] = guessed_start
                print_debug(a=['\nreprocess successful by guessing start for file [%s] - new start %s end %s' % (profiles[nprofile]['Path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'])], log=log_level > 0, log_file=log_file)
                print_timestamp(profiles[nprofile]['Path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'], profiles[nprofile]['fps'], log_level, log_file)
        elif nprofile in non_conforming_profiles:
            print_debug(a=['\nfailed to locate intro by reprocessing %s' % profiles[nprofile]['Path']], log_file=log_file)
            print_debug(a=['file [%s] new start %s end %s' % (profiles[nprofile]['Path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'])], log=log_level > 0, log_file=log_file)
            print_timestamp(profiles[nprofile]['Path'], profiles[nprofile]['start_frame'], profiles[nprofile]['end_frame'], profiles[nprofile]['fps'], log_level, log_file)
            profiles[nprofile]['start_frame'] = 0
            profiles[nprofile]['end_frame'] = 0
    print_debug(a=['\nrepaired %s/%s non conforming profiles\n' % (repaired, len(non_conforming_profiles))], log=log_level > 0, log_file=log_file)


def process_pairs(fingerprints, profiles, ndx_1, ndx_2, mode, log_level, log_file):

    start_end = get_start_end(fingerprints[ndx_1], profiles[ndx_1]['fps'], fingerprints[ndx_2], profiles[ndx_2]['fps'], log_level)

    if mode == BOTH or mode == FIRST:
        profiles[ndx_1]['start_frame'] = start_end[0][0]
        if profiles[ndx_1]['start_frame'] < 0:
            print_debug(a=["start frame is negative (%s), setting to 0 for [%s]" % (profiles[ndx_1]['start_frame'], profiles[ndx_1]['Path'])], log=log_level > 1)
            profiles[ndx_1]['start_frame'] = 0

        profiles[ndx_1]['end_frame'] = start_end[0][1]
        if profiles[ndx_1]['end_frame'] < 0:
            print_debug(a=["end frame is negative (%s), setting to 0 for [%s]" % (profiles[ndx_1]['end_frame'], profiles[ndx_1]['Path'])], log=log_level > 1)
            profiles[ndx_1]['end_frame'] = 0

        print_timestamp(profiles[ndx_1]['Path'], profiles[ndx_1]['start_frame'], profiles[ndx_1]['end_frame'], profiles[ndx_1]['fps'], log_level, log_file)

    if mode == BOTH or mode == SECOND:
        profiles[ndx_2]['start_frame'] = start_end[1][0]
        if profiles[ndx_2]['start_frame'] < 0:
            print_debug(a=["start frame is negative (%s), setting to 0 for [%s]" % (profiles[ndx_2]['start_frame'], profiles[ndx_2]['Path'])], log=log_level > 1)
            profiles[ndx_2]['start_frame'] = 0

        profiles[ndx_2]['end_frame'] = start_end[1][1]
        if profiles[ndx_2]['end_frame'] < 0:
            print_debug(a=["end frame is negative (%s), setting to 0 for [%s]" % (profiles[ndx_2]['end_frame'], profiles[ndx_2]['Path'])], log=log_level > 1)
            profiles[ndx_2]['end_frame'] = 0

        print_timestamp(profiles[ndx_2]['Path'], profiles[ndx_2]['start_frame'], profiles[ndx_2]['end_frame'], profiles[ndx_2]['fps'], log_level, log_file)


def process_directory(profiles=[], ref_profile=None, hashfps=2, log_level=0, log_file=False, cleanup=True, log_timestamp=None):
    global session_timestamp
    global hash_fps

    hash_fps = hashfps

    if log_timestamp is not None:
        session_timestamp = log_timestamp

    start = datetime.now()
    print_debug(a=['started at', start], log=log_level > 0, log_file=log_file)
    print_debug(a=["Check Frame: %s\n" % str(check_frame)], log=log_level > 0, log_file=log_file)
    if cleanup:
        print_debug(a=['fingerprint files will be cleaned up'], log=log_level > 0, log_file=log_file)

    if not check_files_exist(profiles):
        print_debug(a=['input files invalid or cannot be accessed'], log=log_level > 0, log_file=log_file)
        return {}
    
    if (ref_profile is not None and len(profiles) < 1) or (ref_profile is None and len(profiles) < 2):
        print_debug(a=['fewer than 2 valid fingerprints were found - skipping'], log=log_level > 0, log_file=log_file)
        return {}
    
    print_debug(a=['processing %s files' % len(profiles)], log=log_level > 0, log_file=log_file)
    
    if cleanup and Path(data_path / 'fingerprints').is_dir():
        try:
            shutil.rmtree(Path(data_path / 'fingerprints'))
        except OSError as e:
            print_debug(a=["Error: %s : %s" % ('fingerprints', e.strerror)], log_file=log_file)

    fingerprints = []  # list of hash values

    hashing_start = datetime.now()
    for p in profiles:
        fingerprint = get_or_create_fingerprint(p, log_level, log_file)
        if fingerprint:
            fingerprints.append(fingerprint)
    hashing_end = datetime.now()
    print_debug(a=["got or created fingerprints in %s" % str(hashing_end - hashing_start)], log=log_level > 0, log_file=log_file)

    if ref_profile is not None and 'hash_fps' in ref_profile and ref_profile['hash_fps'] == hash_fps:
        fingerprint = read_fingerprint(ref_profile['fingerprint'], log_level, log_file)
        if fingerprint and abs(len(fingerprint) - floor(intro_duration(ref_profile) / (ref_profile['fps'] / hash_fps))) < 2:
            print_debug(a=["loaded reference profile"], log=log_level > 0, log_file=log_file)
            print_timestamp(ref_profile['Path'], ref_profile['start_frame'], ref_profile['end_frame'], ref_profile['fps'], log_level, log_file)
            fingerprints.insert(0, fingerprint)
            ref_profile.pop('fingerprint', None)
            profiles.insert(0, ref_profile)
        else:
            ref_profile = None
    else:
        ref_profile = None

    if (ref_profile is not None and len(fingerprints) < 1) or (ref_profile is None and len(fingerprints) < 2):
        print_debug(a=['fewer than 2 valid fingerprints were found - skipping'], log=log_level > 0, log_file=log_file)
        return {}

    # loop through each pair and store the start/end frames in their profiles
    # then do the same for the remaining profile if count is odd
    #
    # use mode: FIRST, SECOND, BOTH to decide whether to save the values to the first, second, or both profiles
    # changing modes is useful for processing a new profile against one that's already processed
    # for instance, if a profile is rejected it could be reprocessed against a different profile without risking...
    # ...overwriting the the start/end frame values for the reference profile
    counter = 0
    process_pairs_start = datetime.now()

    if ref_profile is not None:
        for i in range(1, len(fingerprints)):
            process_pairs(fingerprints, profiles, 0, i, SECOND, log_level, log_file)
    else:
        while len(fingerprints) - 1 > counter:
            process_pairs(fingerprints, profiles, counter, counter + 1, BOTH, log_level, log_file)
            counter += 2
        if len(fingerprints) % 2 != 0:
            process_pairs(fingerprints, profiles, -2, -1, SECOND, log_level, log_file)

    process_pairs_end = datetime.now()
    print_debug(a=["processed fingerprint pairs in: " + str(process_pairs_end - process_pairs_start)], log=log_level > 0, log_file=log_file)

    correct_errors_start = datetime.now()
    correct_errors(fingerprints, profiles, ref_profile, log_level, log_file)
    correct_errors_end = datetime.now()
    print_debug(a=["finished error correction in: " + str(correct_errors_end - correct_errors_start)], log=log_level > 0, log_file=log_file)

    if ref_profile is not None:
        fingerprints.pop(0)
        profiles.pop(0)

    # finally, automatically reject episodes with intros shorted than a specified length (default 15 seconds)
    # apply pre-roll if wanted
    # use the fps and start/end frame values to calculate the timestamps for the intros and add them to the profiles
    for profile in profiles:
        if intro_duration(profile) < int(min_intro_length_sec * profile['fps']):
            print_debug(a=['%s - intro is less than %s seconds - skipping' % (profile['Path'], min_intro_length_sec)], log=log_level > 1, log_file=log_file)
            profile['start_frame'] = 0
            profile['end_frame'] = 0
        elif preroll_seconds > 0 and profile['end_frame'] > profile['start_frame'] + floor(profile['fps'] * preroll_seconds):
            profile['end_frame'] -= floor(profile['fps'] * preroll_seconds)
        get_timestamp_from_frame(profile)
        print_debug(a=[profile['Path'] + " start time: " + profile['start_time'] + " end time: " + profile['end_time']], log=log_level > 1, log_file=log_file)

    end = datetime.now()
    print_debug(a=["ended at", end], log=log_level > 0, log_file=True)
    print_debug(a=["run time: " + str(end - start)], log=log_level > 0, log_file=True)

    if cleanup and Path(data_path / 'fingerprints').is_dir():
        try:
            shutil.rmtree(Path(data_path / 'fingerprints'))
        except OSError as e:
            print_debug(a=["Error: %s : %s" % ('fingerprints', e.strerror)], log_file=log_file)
    return profiles


def main(argv):

    path = ''
    log_level = 0
    cleanup = False
    log = False
    try:
        opts, args = getopt.getopt(argv, "hi:dvcl")
    except getopt.GetoptError:
        print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode) -l (log to file)\n'])
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode) -l (log to file)\n'])
            sys.exit()
        elif opt == '-i':
            path = arg
        elif opt == '-l':
            log = True
        elif opt == '-d':
            log_level = 2
        elif opt == '-v':
            log_level = 1
        elif opt == '-c':
            cleanup = True

    if path == '' or not Path(path).is_dir():
        print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -c (cleanup) -s (slow mode) -l (log to file)\n'])
        sys.exit(2)

    common_video_extensions = ['.webm', '.mkv', '.avi', '.mts', '.m2ts', '.ts', '.mov', '.wmv', '.mp4', '.m4v', '.mpg', '.mpeg', '.m2v']

    profiles = []
    for child in Path(path).iterdir():
        if child.name[0] == '.':
            continue
        matched_ext = False
        for ext in common_video_extensions:
            if child.name.endswith(ext):
                matched_ext = True
        if matched_ext:
            profile = {}
            profile['Path'] = str(child.resolve())
            profiles.append(profile)

    result = process_directory(file_paths=profiles, log_level=log_level, log_file=log, cleanup=cleanup)
    print(result)


if __name__ == "__main__":
    main(sys.argv[1:])

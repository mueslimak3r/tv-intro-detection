import sys
import getopt
import json

from pathlib import Path
from math import floor
from datetime import timedelta


def get_timestamp(start_ms, end_ms):
    start_time = floor(start_ms / 1000) if start_ms != 0 else 0
    end_time = floor(end_ms / 1000) if end_ms != 0 else 0

    start = str(timedelta(seconds=start_time)).split('.')[0]
    end = str(timedelta(seconds=end_time)).split('.')[0]

    return (start, end)


def get_dir_contents(path: Path, fullpath: bool):
    file_paths = []
    for child in path.iterdir():
        if child.name[0] == '.':
            continue
        file_paths.append(str(child.resolve()) if fullpath else str(child.name))
    file_paths.sort()
    return file_paths


def print_dir_contents(path: Path, padding: int):
    if not path.is_dir():
        return

    contents = get_dir_contents(path, False)
    for c in contents:
        print('%s' % c.rjust(len(c) + padding))


def intro_duration(profile):
    intro_duration = profile['end_frame'] - profile['start_frame']
    if intro_duration < 0:
        intro_duration = 0
    return intro_duration


def get_item(path: Path):
    if not path.exists():
        return

    profile = None
    with path.open('r') as json_file:
        profile = json.load(json_file)

    if profile is None:
        return
    if 'start_time_ms' not in profile or 'end_time_ms' not in profile:
        return

    profile['intro_duration'] = intro_duration(profile)

    return profile


def get_season(path: Path):
    if not path.is_dir():
        return

    season = {
        'SeasonFingerprint': None,
        'Episodes': {},
        'SeriesName': None,
        'SeasonName': None,
        'SeriesId': None,
        'SeasonId': None,
    }

    contents = get_dir_contents(path, True)
    for c in contents:
        if c.endswith('.json'):
            item = get_item(Path(c))
            if not item:
                continue

            if 'SeriesName' in item and item['SeriesName'] != '':
                season['SeriesName'] = item['SeriesName']
            if 'SeasonName' in item and item['SeasonName'] != '':
                season['SeasonName'] = item['SeasonName']
            if 'SeasonId' in item and item['SeasonId'] != '':
                season['SeasonId'] = item['SeasonId']
            if 'SeriesId' in item and item['SeriesId'] != '':
                season['SeriesId'] = item['SeriesId']

            if c.endswith('season.json'):
                season['SeasonFingerprint'] = get_item(Path(c))
            else:
                season['Episodes'][item['EpisodeId']] = item
    return season


def get_series(path: Path):
    # print('%s:' % str(path).rjust(len(str(path)) + padding))
    if not path.is_dir():
        return

    series = {
        'Seasons': {},
        'SeriesName': None,
        'SeriesId': None,
    }

    contents = get_dir_contents(path, True)
    for c in contents:
        season = get_season(Path(c))
        if season is None:
            continue

        if 'SeriesName' in season and season['SeriesName'] != '':
            series['SeriesName'] = season['SeriesName']
        if 'SeriesId' in season and season['SeriesId'] != '':
            series['SeriesId'] = season['SeriesId']

        series['Seasons'][season['SeasonId']] = season

    return series


def print_series(path: Path, padding: int):
    if not path.is_dir():
        return

    series = get_series(path)
    if not series or not series['Seasons']:
        return

    seriesName = series['SeriesName']
    print('%s:' % str(seriesName).rjust(len(str(seriesName)) + padding))

    for season_key in series['Seasons']:
        season = series['Seasons'][season_key]
        if not season['Episodes']:
            continue

        seasonName = season['SeasonName']
        print('%s:' % str(seasonName).rjust(len(str(seasonName)) + padding + 2))
        episodes = season['Episodes']

        for episode_key in episodes:
            episode = episodes[episode_key]
            start, end = get_timestamp(episode['start_time_ms'], episode['end_time_ms'])
            print_str = '%s - start: %s end %s' % (episode['Name'], start, end)
            print(print_str.rjust(len(str(print_str)) + padding + 4))

        if 'SeasonFingerprint' in season and season['SeasonFingerprint'] is not None:
            seasonFingerprint = season['SeasonFingerprint']
            start, end = get_timestamp(seasonFingerprint['start_time_ms'], seasonFingerprint['end_time_ms'])
            print_str = 'season fingerprint [%s - start: %s end %s]' % (seasonFingerprint['Name'], start, end)
            print(print_str.rjust(len(str(print_str)) + padding + 4))


def filter_dirs(old_path: Path, new_path: Path):
    old_path_contents = get_dir_contents(old_path, False)
    new_path_contents = get_dir_contents(new_path, False)

    contents_in_both = list(set(old_path_contents).intersection(set(new_path_contents)))
    contents_in_both.sort()

    contents_not_in_both = list(set(old_path_contents).symmetric_difference(set(new_path_contents)))
    contents_not_in_both.sort()

    if contents_not_in_both:
        print('series not in both:')
        for e in contents_not_in_both:
            if e in old_path_contents:
                path = Path(old_path / e)
            else:
                path = Path(new_path / e)
            print('%s:' % str(path).rjust(len(str(path)) + 2))
            print_dir_contents(path, 4)
            print('\n')

            if path.is_dir():
                print_series(path, 4)
    return contents_in_both


def filter_ids(old_dict: dict, new_dict: dict):
    old_list = list(old_dict.keys())
    new_list = list(new_dict.keys())

    in_both = list(set(old_list).intersection(set(new_list)))
    not_in_both = list(set(old_list).symmetric_difference(set(new_list)))
    return in_both, not_in_both


def check_if_in_list_of_dict(dict_list, value):
    if dict_list is None:
        return -1

    for ndx in range(0, len(dict_list)):
        if value in dict_list[ndx].values():
            return ndx
    return -1


def diff_data(old_path: Path, new_path: Path):
    SeriesIds = filter_dirs(old_path, new_path)
    total_episodes = 0
    total_diffs = 0
    percent_diff = 0

    diff_threshold = 2

    print('\n\n------------------------------------------------\n\n')

    print('series in both:')

    for Id in SeriesIds:
        has_logged_series = False

        old_series = get_series(Path(old_path / Id))
        new_series = get_series(Path(new_path / Id))

        seasons, seasons_not_in_both = filter_ids(old_series['Seasons'], new_series['Seasons'])

        for season_id in seasons:
            has_logged_season = False

            episodes, episodes_not_in_both = filter_ids(old_series['Seasons'][season_id]['Episodes'], new_series['Seasons'][season_id]['Episodes'])
            for episode_id in episodes:
                total_episodes += 1
                old_ep = old_series['Seasons'][season_id]['Episodes'][episode_id]
                new_ep = new_series['Seasons'][season_id]['Episodes'][episode_id]

                old_duration = old_ep['intro_duration'] / old_ep['fps'] if old_ep['intro_duration'] > 0 else 0
                new_duration = new_ep['intro_duration'] / new_ep['fps'] if new_ep['intro_duration'] > 0 else 0

                diff = abs(old_duration - new_duration)
                if diff > diff_threshold:
                    total_diffs += 1
                    if not has_logged_series:
                        seriesName = old_series['SeriesName']
                        print('%s:' % str(seriesName).rjust(len(str(seriesName)) + 2))
                        has_logged_series = True
                    
                    if not has_logged_season:
                        seasonName = old_ep['SeasonName']
                        print('%s:' % str(seasonName).rjust(len(str(seasonName)) + 4))
                        has_logged_season = True

                    log_str = 'intro duration for episode [%s] of season [%s] series [%s] differs' % (old_ep['Name'], old_ep['SeasonName'], old_ep['SeriesName'])
                    print('%s' % str(log_str).rjust(len(str(log_str)) + 6))
                    start1, end1 = get_timestamp(old_ep['start_time_ms'], old_ep['end_time_ms'])
                    log_str = 'old start: %s end %s' % (start1, end1)
                    print('%s' % str(log_str).rjust(len(str(log_str)) + 6))
                    start2, end2 = get_timestamp(new_ep['start_time_ms'], new_ep['end_time_ms'])
                    log_str = 'new start: %s end %s\n' % (start2, end2)
                    print('%s' % str(log_str).rjust(len(str(log_str)) + 6))
                    log_str = 'diff %s seconds' % diff
                    print('%s' % str(log_str).rjust(len(str(log_str)) + 6))

    percent_diff = (total_diffs / total_episodes) * 100
    print('%s/%s episodes ( %s percent ) changed more than %s sec' % (total_diffs, total_episodes, percent_diff, diff_threshold))


def main(argv):
    old_cache_path_str = ''
    new_cache_path_str = ''

    try:
        opts, args = getopt.getopt(argv, "ho:n:")
    except getopt.GetoptError:
        print('diff_jellyfin_cache.py -o <old data> -n <new data>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print('diff_jellyfin_cache.py -o <old data> -n <new data>')
            sys.exit()
        elif opt == '-o':
            old_cache_path_str = arg
        elif opt == '-n':
            new_cache_path_str = arg

    if old_cache_path_str == '' or new_cache_path_str == '':
        print('enter both cache paths')
        return

    if not Path(old_cache_path_str).exists() or not Path(old_cache_path_str).is_dir() \
            or not Path(new_cache_path_str).exists() or not Path(new_cache_path_str).is_dir():
        print('cache paths aren\'t valid')
        return
    
    old_path = Path(old_cache_path_str)
    new_path = Path(new_cache_path_str)

    diff_data(old_path, new_path)


if __name__ == "__main__":
    main(sys.argv[1:])

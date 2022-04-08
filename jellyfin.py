import os
import re
import sys
import getopt
import jellyfin_queries
import json
import shutil
import hashlib


from time import sleep
from pathlib import Path
from datetime import datetime
from jellyfin_api_client import jellyfin_login, jellyfin_logout
from decode import process_directory

server_url = os.environ['JELLYFIN_URL'] if 'JELLYFIN_URL' in os.environ else ''
server_username = os.environ['JELLYFIN_USERNAME'] if 'JELLYFIN_USERNAME' in os.environ else ''
server_password = os.environ['JELLYFIN_PASSWORD'] if 'JELLYFIN_PASSWORD' in os.environ else ''
env_path_map_str = os.environ['PATH_MAP'] if 'PATH_MAP' in os.environ else ''

config_path = Path(os.environ['CONFIG_DIR']) if 'CONFIG_DIR' in os.environ else Path(Path.cwd() / 'config')
data_path = Path(os.environ['DATA_DIR']) if 'DATA_DIR' in os.environ else Path(config_path / 'data')

minimum_episode_duration = 15  # minutes
maximum_episodes_per_season = 30  # meant to skip daily shows like jeopardy

sleep_after_finish_sec = 300  # sleep for 5 minutes after the script finishes. If it runs automatically this prevents it rapidly looping

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


def get_path_map():
    path_map = []

    if env_path_map_str != '':
        env_maps = env_path_map_str.strip().split(',')
        for m in env_maps:
            map = m.strip().split('::')
            if len(map) != 2:
                continue
            path_map.append((Path(map[0]), Path(map[1])))

    if not (config_path / 'path_map.txt').exists():
        return path_map

    with (config_path / 'path_map.txt').open('r') as file:
        for line in file:
            if line.startswith('#'):
                continue
            map = line.strip().split('::')
            if len(map) != 2:
                continue
            path_map.append((Path(map[0]), Path(map[1])))
    return path_map


def get_jellyfin_shows():
    if server_url == '' or server_username == '' or server_password == '':
        print_debug(a=['missing server info'])
        return

    path_map = get_path_map()

    client = jellyfin_login(server_url, server_username, server_password)
    shows = jellyfin_queries.get_shows(client, path_map)
    if not shows:
        print_debug(a=['Error - got 0 shows from jellyfin'])
        return []
    print_debug(a=['found %s shows' % len(shows)])

    season_count = 0
    episode_count = 0
    for show in shows:
        seasons = jellyfin_queries.get_seasons(client, path_map, show)
        if seasons:
            season_count += len(seasons)
        for season in seasons:
            season['Episodes'] = jellyfin_queries.get_episodes(client, path_map, season)
        if season['Episodes']:
            episode_count += len(season['Episodes'])
        show['Seasons'] = seasons
    jellyfin_logout()

    print_debug(a=['found %s seasons' % season_count])
    print_debug(a=['found %s episodes\n' % episode_count])

    return shows


def copy_season_fingerprint(result: list = [], dir_path: Path = None, debug: bool = False, log_file: bool = False):
    if not result or dir_path is None:
        return

    name = ''
    for profile in result:
        name += replace(profile['path'])
    hash_object = hashlib.md5(name.encode())
    name = hash_object.hexdigest()

    src_path = Path(data_path / 'fingerprints' / (name + '.json'))
    dst_path = Path(dir_path / ('season' + '.json'))
    dir_path.mkdir(parents=True, exist_ok=True)
    if src_path.exists():
        if debug:
            print_debug(a=['saving season fingerprint to jellyfin_cache'], log_file=log_file)
        shutil.copyfile(src_path, dst_path)


def save_season(season=None, result=None, save_json=False, debug=False, log_file=False):
    if not result or season is None:
        return
    path = data_path / 'jellyfin_cache' / str(season['SeriesId']) / str(season['SeasonId'])
    if save_json:
        copy_season_fingerprint(result, path, debug, log_file)

    for ndx in range(0, len(season['Episodes'])):
        if ndx >= len(result):
            if debug:
                print_debug(a=['episode index past bounds of result'], log_file=log_file)
            break
        if season['Episodes'][ndx]['Path'] == result[ndx]['path']:
            season['Episodes'][ndx].update(result[ndx])
            season['Episodes'][ndx].pop('path', None)
            print(season['Episodes'][ndx])
            season['Episodes'][ndx]['created'] = str(datetime.now())
            if save_json:
                Path(path).mkdir(parents=True, exist_ok=True)
                with Path(path / (str(season['Episodes'][ndx]['EpisodeId']) + '.json')).open('w+') as json_file:
                    json.dump(season['Episodes'][ndx], json_file, indent=4)
        elif debug:
            print_debug(a=['index mismatch'], log_file=log_file)


def check_json_cache(season=None, log_file=False):
    path = data_path / 'jellyfin_cache' / str(season['SeriesId']) / str(season['SeasonId'])

    file_paths = []

    if path.exists():
        filtered_episodes = []
        for episode in season['Episodes']:
            if not Path(path / (str(episode['EpisodeId']) + '.json')).exists():
                filtered_episodes.append(episode)
        print_debug(a=['processing %s of %s episodes' % (len(filtered_episodes), len(season['Episodes']))], log_file=log_file)
        season['Episodes'] = filtered_episodes

    for episode in season['Episodes']:
        file_paths.append(episode['Path'])
    return file_paths


def process_jellyfin_shows(log_level=0, log_file=False, save_json=False):
    start = datetime.now()
    print_debug(a=["\n\nstarted new session at %s\n" % start], log_file=log_file)

    shows = get_jellyfin_shows()
    
    if (data_path / 'fingerprints').is_dir():
        try:
            shutil.rmtree(data_path / 'fingerprints')
        except OSError as e:
            print_debug(a=["Error: %s : %s" % ('deleting fingerprints directory', e.strerror)], log_file=log_file)

    show_ndx = 1
    for show in shows:
        print_debug(a=['%s/%s - %s' % (show_ndx, len(shows), show['Name'])], log_file=log_file)
        show_ndx += 1
        show_start_time = datetime.now()

        season_ndx = 1
        for season in show['Seasons']:
            print_debug(a=['%s/%s - %s - %s episodes' % (season_ndx, len(show['Seasons']), season['Name'], len(season['Episodes']))], log_file=log_file)
            season_ndx += 1

            if len(season['Episodes']) < 2:
                print_debug(a=['skipping season since it doesn\'t contain at least 2 episodes'], log_file=log_file)
                continue
            if len(season['Episodes']) > maximum_episodes_per_season:
                print_debug(a=['skipping season since it contains %s episodes (more than max %s)' % (len(season['Episodes']), maximum_episodes_per_season)], log_file=log_file)
                continue
            if season['Episodes'][0]['Duration'] < minimum_episode_duration * 60 * 1000:
                print_debug(a=['skipping season since episodes are too short (%s) (less than minimum %s minutes)' % (len(season['Episodes']), minimum_episode_duration)], log_file=log_file)
                continue

            season_start_time = datetime.now()
            file_paths = check_json_cache(season, log_file)
            if file_paths:
                result = process_directory(file_paths=file_paths, cleanup=False, log_level=log_level, log_file=log_file, log_timestamp=session_timestamp)
                if result:
                    save_season(season, result, save_json, log_level > 0, log_file)
                else:
                    print_debug(a=['no results - the decoder may not have access to the specified media files'], log_file=log_file)
            else:
                print_debug(a=['all files were excluded - they either can\'t be found or were previously processed'], log_file=log_file)
            if (data_path / 'fingerprints').is_dir():
                try:
                    shutil.rmtree(data_path / 'fingerprints')
                except OSError as e:
                    print_debug(a=["Error: %s : %s" % ('deleting fingerprints directory', e.strerror)], log_file=log_file)
            season_end_time = datetime.now()
            print_debug(a=['processed season [%s] in %s' % (season['Name'], str(season_end_time - season_start_time))], log_file=log_file)
            if file_paths:
                sleep(2)
        show_end_time = datetime.now()
        print_debug(a=['processed show [%s] in %s' % (show['Name'], str(show_end_time - show_start_time))], log_file=log_file)

    end = datetime.now()
    print_debug(a=["total runtime: " + str(end - start)], log_file=log_file)
    if sleep_after_finish_sec > 0:
        print_debug(a=['sleeping for %s seconds' % sleep_after_finish_sec])
        sleep(300)


def main(argv):
    log_level = 0
    save_json = False
    log = False

    try:
        opts, args = getopt.getopt(argv, "hdvjl")
    except getopt.GetoptError:
        print_debug(['jellyfin.py -d (debug) -j (save json) -l (log to file)'])
        print_debug(['saving to json is currently the only way to skip previously processed files in subsequent runs\n'])
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_debug(['jellyfin.py -d (debug) -j (save json) -l (log to file)'])
            print_debug(['saving to json is currently the only way to skip previously processed files in subsequent runs\n'])
            sys.exit()
        elif opt == '-d':
            log_level = 2
        elif opt == '-v':
            log_level = 1
        elif opt == '-j':
            save_json = True
        elif opt == '-l':
            log = True
    
    if server_url == '' or server_username == '' or server_password == '':
        print_debug(['you need to export env variables: JELLYFIN_URL, JELLYFIN_USERNAME, JELLYFIN_PASSWORD\n'])
        return

    process_jellyfin_shows(log_level, log, save_json)


if __name__ == "__main__":
    main(sys.argv[1:])

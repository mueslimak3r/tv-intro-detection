import os
import json
import arrow
import signal
import sys
import getopt

from pathlib import Path
from time import sleep
from datetime import datetime, timezone
from jellyfin_api_client import jellyfin_login, jellyfin_logout

server_url = os.environ['JELLYFIN_URL'] if 'JELLYFIN_URL' in os.environ else ''
server_username = os.environ['JELLYFIN_USERNAME'] if 'JELLYFIN_USERNAME' in os.environ else ''
server_password = os.environ['JELLYFIN_PASSWORD'] if 'JELLYFIN_PASSWORD' in os.environ else ''

mon_all_users = os.environ['MONITOR_ALL_USERS'] if 'MONITOR_ALL_USERS' in os.environ else ''

config_path = Path(os.environ['CONFIG_DIR']) if 'CONFIG_DIR' in os.environ else Path(Path.cwd() / 'config')
data_path = Path(os.environ['DATA_DIR']) if 'DATA_DIR' in os.environ else Path(config_path / 'data')

TICKS_PER_MS = 10000
preroll_seconds = 3
minimum_intro_length = 10  # seconds

client = None
should_exit = False


def monitor_sessions(monitor_all_users=False):
    global should_exit

    if client is None:
        return False

    start = datetime.now(timezone.utc)
    try:
        sessions = client.jellyfin.sessions()
    except BaseException as err:
        should_exit = True
        print("error communicating with the server %s" % err)
        print('will exit')
        return False

    for session in sessions:
        if not monitor_all_users and session['UserId'] != client.auth.jellyfin_user_id():
            continue
        if 'PlayState' not in session or session['PlayState']['CanSeek'] is False:
            continue
        if 'Capabilities' not in session or session['Capabilities']['SupportsMediaControl'] is False:
            continue
        if 'LastPlaybackCheckIn' not in session:
            continue
        if 'NowPlayingItem' not in session:
            continue

        sessionId = session['Id']

        # print('user id %s' % session['UserId'])
        print(session['DeviceName'])

        lastPlaybackTime = arrow.get(session['LastPlaybackCheckIn']).to('utc').datetime
        timeDiff = start - lastPlaybackTime

        item = session['NowPlayingItem']
        if not session['PlayState']['IsPaused'] and timeDiff.seconds < 5 and 'Id' in item:
            if 'SeriesName' in item and 'SeasonName' in item and 'Name' in item:
                print('currently playing %s - %s - Episode [%s]' % (item['SeriesName'], item['SeasonName'], item['Name']))
            print('item id %s' % item['Id'])
        else:
            print('not playing or hasn\'t checked in')
            continue

        if 'SeriesId' not in item or 'SeasonId' not in item:
            print('playing item isn\'t a series')
            continue

        position_ticks = int(session['PlayState']['PositionTicks'])
        print('current position %s minutes' % (((position_ticks / TICKS_PER_MS) / 1000) / 60))

        file_path = Path(data_path / 'jellyfin_cache' / str(item['SeriesId']) / str(item['SeasonId']) / (str(item['Id']) + '.json'))
        start_time_ticks = 0
        end_time_ticks = 0
        if file_path.exists():
            with file_path.open('r') as json_file:
                dict = json.load(json_file)
                if 'start_time_ms' in dict and 'end_time_ms' in dict:
                    start_time_ticks = int(dict['start_time_ms']) * TICKS_PER_MS
                    end_time_ticks = int(dict['end_time_ms']) * TICKS_PER_MS
        else:
            print('couldn\'t find json file for item. This likely means the episode hasn\'t been processed - checked for file [%s]' % str(file_path))
            continue

        if start_time_ticks == 0 and end_time_ticks == 0:
            print('no useable intro data - start_time and end_time are both 0')
            continue

        if position_ticks < start_time_ticks or position_ticks > end_time_ticks:
            continue

        if end_time_ticks - start_time_ticks < minimum_intro_length * 1000 * TICKS_PER_MS:
            print('ignoring episode - intro is less than %ss' % minimum_intro_length)
            continue

        preroll_ticks = preroll_seconds * 1000 * TICKS_PER_MS
        if end_time_ticks - preroll_ticks >= 0:
            end_time_ticks -= preroll_ticks

        print('trying to send seek to client')
        client.jellyfin.sessions(handler="/%s/Message" % sessionId, action="POST", json={
            "Text": "Skipping Intro",
            "TimeoutMs": 5000
        })

        sleep(1)
        params = {
            "SeekPositionTicks": end_time_ticks
        }
        client.jellyfin.sessions(handler="/%s/Playing/seek" % sessionId, action="POST", params=params)
        sleep(10)
    return True


def init_client():
    global client
    global should_exit

    print('initializing client')
    if client is not None and not should_exit:
        try:
            jellyfin_logout()
        except BaseException as err:
            print("error communicating with the server %s" % err)
            print('will exit')
            should_exit = True
            client = None
            return
    if not should_exit:
        sleep(1)
        try:
            client = jellyfin_login(server_url, server_username, server_password, "TV Intro Auto Skipper")
        except BaseException as err:
            print("error communicating with the server %s" % err)
            print('will exit')
            should_exit = True


def monitor_loop(monitor_all_users=False):
    global should_exit

    if server_url == '' or server_username == '' or server_password == '':
        print('missing server info')
        return
    
    init_client()
    if should_exit:
        return

    print('will monitor [%s]' % ('all users' if monitor_all_users else 'current user'))
    print('listening for jellyfin sessions...')
    while not should_exit:
        if not monitor_sessions(monitor_all_users) and not should_exit:
            init_client()
        sleep(5)
    if client is not None:
        try:
            jellyfin_logout()
        except BaseException as err:
            print("error communicating with the server %s" % err)
            print('will exit')
            return


def main(argv):
    all_users = mon_all_users

    try:
        opts, args = getopt.getopt(argv, "ha")
    except getopt.GetoptError:
        print('jellyfin_auto_skip.py -a (all users)\n')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print('jellyfin_auto_skip.py -a (all users)\n')
            sys.exit()
        elif opt == '-a':
            all_users = True
    
    if server_url == '' or server_username == '' or server_password == '':
        print('you need to export env variables: JELLYFIN_URL, JELLYFIN_USERNAME, JELLYFIN_PASSWORD\n')
        return
    
    if mon_all_users == 'TRUE':
        all_users = True
    elif mon_all_users == 'FALSE':
        all_users = False

    monitor_loop(all_users)


def receiveSignal(signalNumber, frame):
    global should_exit

    if signalNumber == signal.SIGINT:
        print('will exit')
        should_exit = True
    return


if __name__ == "__main__":
    signal.signal(signal.SIGINT, receiveSignal)
    main(sys.argv[1:])

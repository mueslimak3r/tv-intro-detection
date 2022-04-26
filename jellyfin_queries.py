from time import sleep
from pathlib import Path


def map_path(path, path_map):
    new_path = path

    repr_path = path.replace('\\', '/')
    for mapping in path_map:
        path_map_parts_list = list(Path(mapping[1]).parts)
        jellyfin_path_parts_list = list(Path(repr_path).parts)

        path_map_parts = set(path_map_parts_list)
        jellyfin_path_parts = set(jellyfin_path_parts_list)

        if path_map_parts.issubset(jellyfin_path_parts):
            new_path = str(Path(mapping[0]).joinpath(Path(*jellyfin_path_parts_list[len(path_map_parts_list):])))
            break
    return new_path


def get_shows(client=None, path_map=[], reverse_sort=False):
    if client is None:
        return []

    shows = []

    try:
        result = client.jellyfin.user_items(params={
            'Recursive': True,
            'includeItemTypes': (
                "Series"
            ),
            'SortBy': 'DateCreated,SortName',
            'SortOrder': 'Ascending' if reverse_sort else 'Descending',
            'enableImages': False,
            'enableUserData': False,
            'Fields': (
                "Path"
            ),
            # added this limit for safety in case someone runs this without understanding what it does
            # remove the limit to process all shows
            # 'Limit': 1
        })

        if 'Items' in result and result['Items']:
            for item in result['Items']:
                show = {}
                show['Name'] = item['Name']
                show['SeriesId'] = item['Id']
                show['Path'] = map_path(item['Path'], path_map) if 'Path' in item else None
                shows.append(show)
    except BaseException as err:
        return []
    sleep(0.2)
    return shows


def get_seasons(client=None, path_map=[], series=None):
    if client is None or series is None:
        return []

    seasons = []

    try:
        result = client.jellyfin.get_seasons(series['SeriesId'])

        if 'Items' in result and result['Items']:
            for item in result['Items']:
                season = {}
                season['Name'] = item['Name']
                season['SeriesName'] = series['Name']
                season['SeriesId'] = series['SeriesId']
                season['SeasonId'] = item['Id']
                season['Path'] = map_path(item['Path'], path_map) if 'Path' in item else None
                seasons.append(season)
    except BaseException as err:
        return []
    sleep(0.2)
    return seasons


def get_episodes(client=None, path_map=[], season=None):
    if client is None or season is None:
        return []

    episodes = []

    try:
        result = client.jellyfin.shows("/%s/Episodes" % season['SeriesId'], {
            'UserId': "{UserId}",
            'SeasonId': season['SeasonId'],
            'Fields': (
                "Path"
            )
        })
        
        if 'Items' in result and result['Items']:
            for item in result['Items']:
                episode = {}
                episode['Name'] = item['Name']
                episode['SeriesName'] = season['SeriesName']
                episode['SeasonName'] = season['Name']
                episode['Duration'] = int(item['RunTimeTicks']) / 10000
                episode['SeriesId'] = season['SeriesId']
                episode['SeasonId'] = season['SeasonId']
                episode['EpisodeId'] = item['Id']
                episode['ProviderIds'] = {}
                if 'ProviderIds' in item:
                    episode['ProviderIds'] = item['ProviderIds'].deepcopy()
                if 'Path' in item:
                    episode['Path'] = map_path(item['Path'], path_map)
                    episodes.append(episode)
    except BaseException as err:
        return []
    return episodes

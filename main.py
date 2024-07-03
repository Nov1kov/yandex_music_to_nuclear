import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DEFAULT_SOURCE = 'Youtube'


def parse_track_json(index, track_json):
    track = {
        "title": track_json['title'],
        "artist": ', '.join([a['name'] for a in track_json['artists']]),
        'index': index + 1,
    }

    if len(track_json.get('albums', [])) > 0:
        track['album'] = track_json['albums'][0]['title']

    if 'coverUri' in track_json or 'cover_uri' in track_json:
        track_uri = track_json.get('cover_uri') if track_json.get('coverUri') is None else track_json['coverUri']
        if track_uri:
            url = track_uri.replace('%', '').strip()
            track['thumbnail'] = urljoin(f'https://{url}', '50x50')
    return track


def save_to_file(tracks, tracklist_title):
    playlist_data = {'name': tracklist_title,
                     'numberOfTrack': len(tracks),
                     'source': DEFAULT_SOURCE,
                     'tracks': tracks}
    file_name = f"{tracklist_title}.json"
    print(f'Exported: {file_name} with {len(tracks)} tracks')
    json.dump(playlist_data, open(file_name, 'w', encoding='utf-8'))


def get_tracks_from_js(soup):
    tracks = []
    js_script = soup.find('script', string=re.compile('var Mu={'))
    tracklist_title = ''
    if js_script:
        json_text = re.findall(r'var Mu=(.*);', js_script.text)[0]
        json_data = json.loads(json_text)
        if 'playlist' not in json_data:
            return [], ''
        tracklist_title = json_data['pageData']['playlist']['title']
        for index, track_json in enumerate(json_data['pageData']['playlist']['tracks']):
            track = parse_track_json(index, track_json)
            tracks.append(track)
    return tracks, tracklist_title


def get_tracks_from_html(soup):
    tracks = []
    tracklist_title_element = soup.find(class_='page-playlist__title')
    if not tracklist_title_element:
        tracklist_title_element = soup.find('div', class_='sidebar__title typo-h2')

    tracklist_title = tracklist_title_element.text.strip()
    if not tracklist_title:
        tracklist_title = tracklist_title_element.attrs['value']

    for index, track_element in enumerate(soup.find_all('div', class_='d-track')):
        title_element = track_element.find('div', class_='d-track__name')
        artist_element = track_element.find('span', class_='d-track__artists')
        image = track_element.find('img', class_='entity-cover__image deco-pane')

        track = {
            "title": title_element.text.strip(),
            "artist": artist_element.text.strip(),
            'index': index + 1,
        }

        if image:
            track['thumbnail'] = 'https:' + image.attrs['src']

        tracks.append(track)
    return tracks, tracklist_title


def get_tracks_by_api(token):
    from yandex_music import Client

    client = Client(token).init()
    all_playlists = client.users_playlists_list()
    playlists = client.users_playlists(kind=[pl['kind'] for pl in all_playlists])
    for playlist in playlists:
        tracklist_title = playlist['title']
        tracks_list = client.tracks(track_ids=[t['id'] for t in playlist['tracks']])
        tracks = [parse_track_json(index, track_json.__dict__) for index, track_json in enumerate(tracks_list)]
        save_to_file(tracks, tracklist_title)


def get_html(url):
    headers = {
        "User-Agent": "curl/8.7.3",
        "Accept": "*/*",
        "Connection": "keep-alive",
    }

    session = requests.Session()
    session.headers = {}

    response = session.get(url, headers=headers)
    if response.ok:
        return response.text
    else:
        print(f"Couldn't load {url} - [{response.status_code}]")
        return None


def get_file(file):
    if Path(file).exists():
        return Path(file).read_text(encoding='utf-8')
    else:
        print(f"File {file} not exits!")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Парсер плейлистов Яндекс.Музыки')
    parser.add_argument('-u', '--urls', nargs='+', help='Ссылки на плейлисты')
    parser.add_argument("-f", "--files", nargs='+', help="Файлы с путем до html файла с плейлистом.")
    parser.add_argument("-t", "--token", help="Токен Яндекс.Музыки - для доступа к аккаунту через API")

    args = parser.parse_args()

    if args.token:
        get_tracks_by_api(args.token)
    elif args.urls or args.files:
        if args.urls:
            htmls = [get_html(url) for url in args.urls]
        else:
            htmls = [get_file(file) for file in args.files]
        for html in htmls:
            if html is None:
                continue
            soup = BeautifulSoup(html, 'lxml')
            if soup.find('div', class_='CheckboxCaptcha-Label') is not None:
                raise Exception("Captcha showed!")

            tracks, title = get_tracks_from_js(soup)
            if not tracks:
                tracks, title = get_tracks_from_html(soup)
            save_to_file(tracks, title)

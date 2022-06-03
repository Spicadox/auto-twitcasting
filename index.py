import time
import os
import requests
import json
import subprocess
from datetime import datetime
import const
from log import create_logger
import pytz
import asyncio
import aiohttp


SLEEP_TIME = const.SLEEP_TIME
bearer_token = const.bearer_token
WEBHOOK_URL = const.WEBHOOK_URL
PASSWORD_PATH = const.PASSWORD_PATH
COOKIES = []
if '--cookies-from-browser' in const.COOKIES:
    COOKIES = const.COOKIES.split(maxsplit=1)
else:
    COOKIES = ['--cookies', const.COOKIES]
tz = pytz.timezone('Asia/Tokyo')

# Dictionary comprehension of the list of twitcasting users
user_ids = {user_id: {"movie_id": None, "notified": False, "downloaded": False, "type": None} for user_id in const.user_ids}


def get_passwords():
    try:
        if PASSWORD_PATH is None or PASSWORD_PATH == "":
            return None
        with open(PASSWORD_PATH, mode='r', encoding="utf-8") as password_file:
            lines = password_file.readlines()
            passwords = {line.rstrip() for line in lines}
        return passwords
    except Exception as e:
        logger.error(e)
        logger.info("Error getting password list")
        return None


async def fetch_html(session, user_id):
    headers = {'Accept': 'application/json'}
    url = f"https://frontendapi.twitcasting.tv/users/{user_id}/latest-movie"
    res = await session.get(url, headers=headers)
    return res, user_id


async def fetch_html_2(session, user_id):
    headers = {'Accept': 'application/json'}
    url = f"https://twitcasting.tv/userajax.php?c=islive&u={user_id}"
    res = await session.get(url, headers=headers)
    return res, user_id


async def get_lives():
    tasks = []
    live_streams = []
    async with aiohttp.ClientSession() as session:
        for user_id in user_ids:
            # res = {}
            # Use the frontendapi to check for live streams as it has no known call limit but only useful for many streams
            # NOTE: Do not know if frontendapi can be used for member's only stream therefore there could be redundancy
            tasks.append(fetch_html_2(session, user_id))
        results = await asyncio.gather(*tasks)
    for result in results:
        res = await result[0].json(content_type=None)
        id = result[1]
        live_streams.append((res, id))
    return live_streams


# Used to check the latest movie to see if it's live and/or is a member's only stream
def check_latest_live(user_id):
    try:
        headers = {'Authorization': f'Bearer {bearer_token}',
                   'Accept': 'application/json',
                   'X-Api-Version': '2.0'}
        res = requests.get(f"https://apiv2.twitcasting.tv/users/{user_id}/movies?limit=1",
                           headers=headers).json()
        logger.debug(res)

        # If the stream is live then it's a member's only live stream
        if len(res['movies']) != 0 and res['movies'][0]['is_live']:
            return res
        else:
            return {}
    except requests.exceptions.ConnectionError as cError:
        logger.debug(cError)
        return {}
    except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as rerror:
        logger.error(rerror)
        return {}


def add_live_users(lives):
    for stream in lives:
        stream_json = stream[0]
        streamer_name = stream[1]
        try:
            if stream_json['movie']['is_on_live']:
                if stream_json['movie']['id'] != user_ids[streamer_name]['movie_id']:
                    user_ids[streamer_name] = {"movie_id": stream_json['movie']['id'],
                                               "notified": False,
                                               "downloaded": False}
            else:
                user_ids[streamer_name] = {"movie_id": None,
                                           "notified": False,
                                           "downloaded": False}
        except Exception as e:
            logger.debug(e)


def add_live_users_2(lives):
    for stream in lives:
        stream_json = stream[0]
        streamer_name = stream[1]
        try:
            if stream_json != 0:
                movie_id = stream_json['url'][-9:]
                if movie_id != user_ids[streamer_name]['movie_id']:
                    user_ids[streamer_name] = {"movie_id": movie_id,
                                               "notified": False,
                                               "downloaded": False,
                                               "type": stream_json['type']}
            else:
                user_ids[streamer_name] = {"movie_id": None,
                                           "notified": False,
                                           "downloaded": False,
                                           "type": None}
        except Exception as e:
            logger.debug(e)


if __name__ == "__main__":
    logger = create_logger()
    logger.info("Starting program")
    live_streams = set()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Get output path and if it ends with backward slash then remove it
    if const.OUTPUT_PATH is not None or "":
        output_path = const.OUTPUT_PATH
        if output_path[-1] == "\\":
            output_path = output_path[:-1]
    else:
        output_path = os.getcwd()

    while True:
        try:
            logger.debug(user_ids)
            time.sleep(1)
            logger.debug("Fetching Lives...")
            # Check whether user is currently like
            lives = asyncio.run(get_lives())
            logger.debug(lives)
            add_live_users_2(lives)
            for user_id, user_data in user_ids.items():
                try:
                    if user_data['movie_id'] is not None and not user_data['notified']:
                        # https://stackoverflow.com/questions/23267409/how-to-implement-retry-mechanism-into-python-requests-library
                        # Maybe use sessions so logger.error can be used to print error if retries fails
                        res = {}
                        headers = {'Authorization': f'Bearer {bearer_token}',
                                   'Accept': 'application/json',
                                   'X-Api-Version': '2.0'}
                        res = requests.get(f"https://apiv2.twitcasting.tv/users/{user_id}/current_live",
                                           headers=headers).json()
                        logger.debug(res)
                    elif user_data['movie_id'] is not None:
                        live_url = f"https://twitcasting.tv/{user_id}/movie/{user_data['movie_id']}"
                        logger.info(f"{user_id} is currently live at {live_url}")
                    else:
                        logger.info(f"{user_id} is currently offline...")
                        continue
                except requests.exceptions.ConnectionError as cError:
                    logger.debug(cError)
                except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as rerror:
                    logger.error(rerror)
                    continue
                # If res returns a json with an error key then it is not currently live
                if 'error' in res and res['error']['code'] == 404:
                    member_res = check_latest_live(user_id)
                    if len(member_res) != 0:
                        # For now use live thumbnail instead of pfp
                        res = {'movie': member_res['movies'][0],
                               'broadcaster': {'screen_id': user_id, 'image': member_res['movies'][0]['large_thumbnail']},
                               'member_only': True}
                    else:
                        logger.info(f"{user_id} is currently offline...")
                        continue
                    # If the request could not be sent due to an invalid bearer token
                    if res['error']['code'] == 1000:
                        logger.error("Invalid bearer token")
                        quit()

                member_only = res['member_only'] if 'member_only' in res else False
                protected = res['movie']['is_protected']
                live_id = res['movie']['id']
                screen_id = res['broadcaster']['screen_id']
                user_image = res['broadcaster']['image']
                live_thumbnail = f"https://apiv2.twitcasting.tv/users/{user_id}/live/thumbnail?size=large&position=latest"
                live_title = res['movie']['title']
                live_date = datetime.fromtimestamp(res['movie']['created'], tz=tz).strftime('%Y%m%d')
                live_url = f"https://twitcasting.tv/{screen_id}/movie/{live_id}"
                # If a live stream has been encountered for the first time
                if not user_data['notified']:
                    # Send notification to discord webhook
                    logger.info(f"{screen_id} is currently live at {live_url}")
                    if WEBHOOK_URL is not None:
                        if protected:
                            live_text = f"{screen_id} has a `protected` live stream at {live_url}"
                        elif member_only:
                            live_text = f"{screen_id} has a `member's only` live stream at {live_url}"
                        else:
                            live_text = f"{screen_id} is now live at {live_url}"
                        message = {"embeds": [{
                            "color": 13714,
                            "author": {
                                "name": screen_id,
                                "icon_url": user_image
                            },
                            "fields": [
                                {
                                    "name": res['movie']['title'],
                                    "value": live_text
                                }
                            ],
                            "image": {
                                "url": live_thumbnail
                            },
                            "thumbnail": {
                                "url": user_image
                            }
                        }]
                        }
                        requests.post(WEBHOOK_URL, json=message)
                        user_data['notified'] = True

                if not user_data['downloaded']:
                    # Get password list
                    passwords = None
                    if protected:
                        passwords = get_passwords()

                    # Download the live stream
                    logger.info(f"Downloading {live_url}")
                    if not protected and not member_only:
                        yt_dlp_args = ['start', '/min', 'cmd', '/c', 'yt-dlp',  *COOKIES, '--no-part', '--embed-metadata']
                        yt_dlp_args += ['-o', f'{output_path}\\{screen_id}\\{live_date} - {live_title} ({live_id}).%(ext)s', live_url]
                        result = subprocess.run(yt_dlp_args, shell=True)
                    elif protected and passwords is not None:
                        # Try downloading protected streams by trying all the passwords
                        # This will open up a console for each password so make sure the password list isn't too long...
                        for password in passwords:
                            # Scenario where cookies unlock the video but video-password is still called so error or not
                            yt_dlp_args = ['start', '/min', 'cmd', '/c', 'yt-dlp', *COOKIES, '--no-part', '--embed-metadata']
                            yt_dlp_args += ['--video-password', password, '-o',
                                            f'{output_path}\\{screen_id}\\{live_date} - {live_title} ({live_id}).%(ext)s',
                                            live_url]
                            result = subprocess.run(yt_dlp_args, shell=True)
                            # time.sleep(1)
                    elif member_only:
                        yt_dlp_args = ['start', '/min', 'cmd', '/c', 'yt-dlp',  *COOKIES, '--no-part']
                        yt_dlp_args += ['--embed-metadata', '-o',
                                        f'{output_path}\\{screen_id}\\{live_date} - {live_title} ({live_id}).%(ext)s',
                                        live_url]
                        result = subprocess.run(yt_dlp_args, shell=True)
                    else:
                        logger.error(f"Failed to download protected stream at {live_url}")
                    user_data['downloaded'] = True
        except KeyError:
            continue
        except Exception as e:
            logger.error(e, exc_info=True)


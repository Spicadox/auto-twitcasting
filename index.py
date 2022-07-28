import asyncio
import json
import os
import subprocess
import threading
import time
from datetime import datetime
import aiohttp
import dotenv
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
import const
import renew
from log import create_logger


def set_bearer_token():
    global bearer_token
    dotenv.load_dotenv(override=True)
    bearer_token = os.getenv("BEARER_TOKEN")


def loading_text():
    loading_string = "[INFO] Waiting for live twitcasting streams "
    animation = ["     ", ".    ", "..   ", "...  ", ".... ", "....."]
    idx = 0
    while True:
        print(loading_string + animation[idx % len(animation)], end="\r")
        time.sleep(0.3)
        idx += 1
        if idx == 6:
            idx = 0


def format_url_message(user_id, live_id, live_message, live_url):
    live_message = live_message.replace("protected", "`protected`").replace("member's only", "`member's only`")
    if "_" in user_id[0] or "_" in user_id[-1] or "__" in user_id:
        live_message = live_message.replace(user_id, f"`{user_id}`")
        if "__" not in user_id:
            live_url = f"`https://twitcasting.tv/{user_id}/movie/{live_id}`"
        return live_message, live_url
    return live_message, live_url


def get_secondary_title(res):
    temp_live_title = res['movie']['title']
    temp_live_comment = res['movie']['last_owner_comment']
    temp_live_subtitle = res['movie']['subtitle']
    if temp_live_comment is not None and temp_live_title != temp_live_comment:
        return temp_live_comment.replace("\\n", "\n")
    elif temp_live_subtitle is not None and temp_live_title != temp_live_subtitle:
        return temp_live_subtitle.replace("\\n", "\n")
    else:
        return res['broadcaster']['name']


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
        logger.error("Error getting password list")
        return None


# This endpoint can catch membership streams but may rate limit after a while
async def fetch_html(session, user_id):
    headers = {'Accept': 'application/json'}
    url = f"https://twitcasting.tv/streamserver.php?target={user_id}&mode=client"
    res = await session.get(url, headers=headers)
    return res, user_id


async def get_lives():
    tasks = []
    live_streams = []
    rate_limit = False
    async with aiohttp.ClientSession() as session:
        for user_id in user_ids:
            tasks.append(fetch_html(session, user_id))
        results = await asyncio.gather(*tasks)
    for result in results:
        try:
            res = await result[0].json(content_type=None)
        except json.JSONDecodeError as jsonDecodeError:
            logger.debug(jsonDecodeError)
            logger.debug(result)
            logger.debug(f"Error {result[0].status}: {result[0].reason}")
            rate_limit = True
            res = {}
            await asyncio.sleep(1)
        except aiohttp.ClientError as clientError:
            logger.debug(clientError)
            logger.debug(result)
            logger.debug(f"Error {result[0].status}: {result[0].reason}")
            rate_limit = True
            res = {}
            await asyncio.sleep(1)
        id = result[1]
        live_streams.append((res, id))
    if rate_limit:
        #     TODO maybe switch api instead
        time.sleep(5)
    return live_streams


# Used to check the latest movie to see if it's live and/or is a member's only stream
def check_latest_live(user_id, session, logger):
    try:
        headers = {'Authorization': f'Bearer {bearer_token}',
                   'Accept': 'application/json',
                   'X-Api-Version': '2.0'}
        response = session.get(f"https://apiv2.twitcasting.tv/users/{user_id}/movies?limit=1",
                               headers=headers)
        if response.status_code == 401:
            renew_status = renew.renew_token(logger=logger)
            set_bearer_token()
            if renew_status is None:
                logger.error("Error renewing bearer token")
        res = response.json()
        try:
            response = session.get(f"https://apiv2.twitcasting.tv/users/{user_id}", headers=headers).json()
            if response.status_code == 401:
                renew_status = renew.renew_token(logger=logger)
                set_bearer_token()
                if renew_status is None:
                    logger.error("Error renewing bearer token")
            user_res = response.json()
            # If the stream is live then it's a member's only live stream
            if len(res['movies']) != 0:
                res_data = {'movie': res['movies'][0], 'broadcaster': user_res['user']}
                logger.debug(res_data)
                return res_data
            else:
                return {}
        except TypeError:
            res_data = {'movie': data['movies'][0],
                        'broadcaster': {'screen_id': user_id, 'image': res['movies'][0]['large_thumbnail']}}
            return res_data

    except requests.exceptions.ConnectionError as cError:
        logger.debug(cError)
        return {}
    except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as rerror:
        logger.error(rerror)
        return {}
    except Exception as e:
        logger.debug(res)
        logger.debug(e)
        return {}


def poll_member_stream(user_id):
    membership_status = False
    member_data = {}
    try:
        page_res = requests.get(f"https://twitcasting.tv/{user_id}/show/").text
        soup = BeautifulSoup(page_res, "html.parser")
        first_video_element = soup.find("div", class_="recorded-movie-box").find("a", class_="tw-movie-thumbnail")
        member_icon_element = first_video_element.find("img", class_="tw-movie-thumbnail-title-icon")['src']
        membership_status = True if "member" in member_icon_element else False
        # If this endpoint returns False on is_on_live then it's likely a member only stream
        logger.debug(f"{user_id} member stream: {membership_status}")
        movie_title_element = first_video_element.find("span", class_="tw-movie-thumbnail-title")
        if movie_title_element is not None:
            movie_title = movie_title_element.text.strip()
        else:
            movie_title = user_id
        movie_subtitle_element = first_video_element.find("span", class_="tw-movie-thumbnail-label")
        if movie_subtitle_element is not None:
            movie_subtitle = first_video_element.find("span", class_="tw-movie-thumbnail-label").text.lstrip().rstrip()
        else:
            movie_subtitle = movie_title
        is_protected = True if len(first_video_element.find("span", class_="tw-movie-thumbnail-title")
                                   .find_all("img", class_="tw-movie-thumbnail-title-icon")) > 1 else False
        image = soup.find("a", class_="tw-user-nav-icon").find("img", recursive=False)['src']
        thumbnail = soup.find("img", class_="tw-movie-thumbnail-image")['src']
        date = first_video_element.find("img", class_="tw-movie-thumbnail-image")['title'][:10].replace("/", "")
        member_data = {'title': movie_title, 'subtitle': movie_subtitle, 'is_protected': is_protected, 'date': date,
                       'image': f'https:{image}', 'thumbnail': thumbnail}
    except KeyError as kError:
        logger.debug(page_res)
        logger.error(kError, exc_info=True)
    except AttributeError as aError:
        logger.debug(page_res)
        logger.error(aError, exc_info=True)
    except Exception as e:
        logger.debug(page_res)
        logger.error(e, exc_info=True)
    finally:
        return membership_status, member_data


def check_member_stream(user_id):
    headers = {'Accept': 'application/json'}
    url = f"https://frontendapi.twitcasting.tv/users/{user_id}/latest-movie"
    res = requests.get(url, headers=headers).json()
    try:
        # If this endpoint returns False on is_on_live then it's likely a member only stream
        if not res['movie']['is_on_live']:
            return True
        else:
            return False
    except KeyError as kError:
        # If this endpoint contains any empty movie dictionary then it's likely a member only stream
        logger.debug(kError)
        return True


def add_live_users(lives):
    for stream in lives:
        stream_json = stream[0]
        streamer_name = stream[1]
        try:
            if len(stream_json) != 0 and stream_json['movie']['live']:
                movie_id = stream_json['movie']['id']
                if movie_id != user_ids[streamer_name]['movie_id']:
                    user_ids[streamer_name] = {"movie_id": movie_id,
                                               "notified": False,
                                               "downloaded": False,
                                               "type": "Live"}
            else:
                user_ids[streamer_name] = {"movie_id": None,
                                           "notified": False,
                                           "downloaded": False,
                                           "type": None}
        except Exception as e:
            logger.debug(e)
            continue


if __name__ == "__main__":
    logger = create_logger()
    logger.info("Starting program")

    # Setup
    SLEEP_TIME = const.SLEEP_TIME
    WEBHOOK_URL = const.WEBHOOK_URL

    try:
        PASSWORD_PATH = Path(const.PASSWORD_PATH).resolve()
    except Exception:
        logger.error("There is a problem with the password path")

    try:
        dotenv.load_dotenv()
        if os.getenv("BEARER_TOKEN") is not None:
            bearer_token = os.getenv("BEARER_TOKEN")
        else:
            bearer_token = const.bearer_token
    except Exception as env_exception:
        logger.error(env_exception)

    COOKIES = []
    if const.COOKIES is not None:
        if '--cookies-from-browser' in const.COOKIES:
            COOKIES = const.COOKIES.split(maxsplit=1)
        else:
            COOKIES = ['--cookies', const.COOKIES]

    # Dictionary comprehension of the list of twitcasting users
    user_ids = {user_id: {"movie_id": None, "notified": False, "downloaded": False, "type": None} for user_id in
                const.user_ids}

    # Setup session
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=5))
    live_streams = set()
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    threading.Thread(target=loading_text).start()

    # Get output path and if it ends with backward slash then remove it
    if const.OUTPUT_PATH is not None or "":
        output_path = Path(const.OUTPUT_PATH).resolve()
    else:
        output_path = os.getcwd()

    while True:
        try:
            # logger.debug(user_ids)
            time.sleep(1)
            # logger.debug("Fetching Lives...")
            # Check whether user is currently like
            try:
                lives = asyncio.run(get_lives())
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError) as aiohttpError:
                logger.debug(aiohttpError)
                continue
            logger.debug(lives)
            add_live_users(lives)
            for user_id, user_data in user_ids.items():
                try:
                    if user_data['movie_id'] is not None and not user_data['notified']:
                        res = {}
                        headers = {'Authorization': f'Bearer {bearer_token}',
                                   'Accept': 'application/json',
                                   'X-Api-Version': '2.0'}
                        response = session.get(f"https://apiv2.twitcasting.tv/users/{user_id}/current_live",
                                               headers=headers)
                        if response.status_code == 401:
                            renew_status = renew.renew_token(logger=logger)
                            set_bearer_token()
                            if renew_status is None:
                                logger.error("Error renewing bearer token")
                            continue
                        res = response.json()
                        logger.debug(res)
                        live_url = f"https://twitcasting.tv/{user_id}/movie/{user_data['movie_id']}"
                        if 'movie_id' in res and res['movie_id'] is not None:
                            # Check if it's a member's only stream
                            is_member = check_member_stream(user_id)
                            logger.debug(is_member)
                            if is_member:
                                res['member_only'] = True
                    else:
                        # logger.info(f"{user_id} is currently offline...")
                        continue
                except requests.exceptions.ConnectionError as cError:
                    logger.error(cError)
                except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as rerror:
                    logger.error(rerror)
                    continue
                # If res returns a json with an error key then it is not currently live
                if 'error' in res and res['error']['code'] == 404:
                    error_res = res
                    res = check_latest_live(user_id, session, logger)
                    if res == {}:
                        member_res, data = poll_member_stream(user_id)
                        # maybe also checking member_res is not necessary
                        if member_res and user_ids[user_id]["type"] == "Live":
                            # For now use live thumbnail instead of pfp
                            try:
                                res = {'movie': {'id': user_ids[user_id]['movie_id'], 'title': data['title'],
                                                 'subtitle': data['subtitle'],
                                                 'last_owner_comment': None, 'is_protected': data['is_protected'],
                                                 'date': data['date'],
                                                 'member_thumbnail': data['thumbnail']},
                                       'broadcaster': {'screen_id': user_id,
                                                       'image': data['image']},
                                       'member_only': True}
                                logger.debug(res)
                            except Exception as e:
                                logger.error(e, exc_info=True)
                        else:
                            continue
                    else:
                        res['member_only'] = True
                        res['movie']['member_thumbnail'] = res['movie']['small_thumbnail']
                    # If the request could not be sent due to an invalid bearer token
                    if error_res['error']['code'] == 1000:
                        logger.error("Invalid bearer token")
                        quit()
                # TODO set default values in event not found
                try:
                    member_only = res['member_only'] if 'member_only' in res else False
                    protected = res['movie']['is_protected'] if 'is_protected' in res['movie'] else False
                    live_id = res['movie']['id']
                    screen_id = res['broadcaster']['screen_id']
                    user_image = res['broadcaster']['image']
                    live_title = res['movie']['title']
                    live_comment = get_secondary_title(res)
                    if 'member_thumbnail' not in res['movie']:
                        if 'large_thumbnail' in res['movie']:
                            live_thumbnail = res['movie']['large_thumbnail']
                        else:
                            live_thumbnail = f"https://apiv2.twitcasting.tv/users/{user_id}/live/thumbnail?size=large&position=latest"
                    else:
                        live_thumbnail = res['movie']['member_thumbnail']
                    if 'created' in res['movie']:
                        live_date = datetime.fromtimestamp(res['movie']['created']).strftime('%Y%m%d')
                    else:
                        live_date = res['movie']['date']
                    if "_" not in screen_id[0] or "_" not in screen_id[-1]:
                        live_url = f"https://twitcasting.tv/{screen_id}/movie/{live_id}"
                    else:
                        live_url = f"`https://twitcasting.tv/{screen_id}/movie/{live_id}`"
                    download_url = f"https://twitcasting.tv/{screen_id}/movie/{live_id}"
                except KeyError as kError:
                    logger.error(kError, exc_info=True)
                # If a live stream has been encountered for the first time
                if not user_data['notified']:
                    # Send notification to discord webhook
                    if WEBHOOK_URL is not None:
                        if protected and member_only:
                            live_text = f"{screen_id} has a protected member's only live stream at "
                        elif protected:
                            live_text = f"{screen_id} has a protected live stream at "
                        elif member_only:
                            live_text = f"{screen_id} has a member's only live stream at "
                        else:
                            live_text = f"{screen_id} is now live at "
                        logger.info(live_text + download_url)
                        live_text, live_url = format_url_message(screen_id, live_id, live_text, live_url)
                        message = {"embeds": [{
                            "color": 13714,
                            "author": {
                                "name": screen_id,
                                "icon_url": user_image
                            },
                            "fields": [
                                {
                                    "name": f"{live_title}\n{live_comment}\n\n{live_text}",
                                    "value": live_url
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
                        passwords.add(datetime.utcnow().strftime("%Y%m%d"))

                    # Download the live stream
                    logger.info(f"Downloading {download_url}")
                    output = f'{output_path}/{screen_id}/{live_date} - {live_title} ({live_id}).%(ext)s'
                    logger.debug(f"Download Path: {output}")
                    if not protected and not member_only:
                        yt_dlp_args = ['start', f'auto-twitcasting {screen_id} {live_id}', '/min', 'cmd', '/c',
                                       'yt-dlp', *COOKIES, '--no-part', '--embed-metadata']
                        yt_dlp_args += ['-o', output, download_url]
                        result = subprocess.run(yt_dlp_args, shell=True)
                    elif protected and passwords is not None:
                        # Try downloading protected streams by trying all the passwords
                        # If stream happens to also be a password protected member's only stream this should work too
                        # This will open up a console for each password so make sure the password list isn't too long...
                        for password in passwords:
                            # Scenario where cookies unlock the video but video-password is still called so error or not
                            yt_dlp_args = ['start', f'auto-twitcasting {screen_id} {live_id}', '/min', 'cmd', '/c',
                                           'yt-dlp', *COOKIES, '--no-part', '--embed-metadata']
                            yt_dlp_args += ['--video-password', password, '-o', output, download_url]
                            result = subprocess.run(yt_dlp_args, shell=True)
                            # time.sleep(1)
                    elif member_only:
                        yt_dlp_args = ['start', f'auto-twitcasting {screen_id} {live_id}', '/min', 'cmd', '/c',
                                       'yt-dlp', *COOKIES, '--no-part']
                        yt_dlp_args += ['--embed-metadata', '-o', output, download_url]
                        result = subprocess.run(yt_dlp_args, shell=True)
                    else:
                        logger.error(f"Failed to download protected stream at {download_url}")
                    user_data['downloaded'] = True
        except Exception as e:
            logger.error(e, exc_info=True)

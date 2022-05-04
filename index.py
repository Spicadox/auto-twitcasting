import time
import os
import requests
import json
import subprocess
from datetime import datetime
import const
from log import create_logger
import pytz


SLEEP_TIME = const.SLEEP_TIME
bearer_token = const.bearer_token
WEBHOOK_URL = const.WEBHOOK_URL
PASSWORD_PATH = const.PASSWORD_PATH

tz = pytz.timezone('Asia/Tokyo')

# Dictionary comprehension of the list of twitcasting users
user_ids = {user_id: [] for user_id in const.user_ids}


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


if __name__ == "__main__":
    logger = create_logger()
    logger.info("Starting program")

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
            # Check whether user is currently like
            for user_id in user_ids:
                time.sleep(1)
                try:
                    headers = {'Authorization': f'Bearer {bearer_token}',
                               'Accept': 'application/json',
                               'X-Api-Version': '2.0'}
                    res = requests.get(f"https://apiv2.twitcasting.tv/users/{user_id}/current_live",
                                       headers=headers).json()
                    logger.debug(res)
                except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as rerror:
                    logger.error(rerror)
                    continue

                # If res returns a json with an error key then it is not currently live
                if 'error' in res.keys():
                    # remove live from notified list if user is now offline if user_id key is found in the array of dict
                    user_ids[user_id] = []
                    # If channel is not live
                    if res['error']['code'] == 404:
                        logger.info(f"{user_id} is currently offline...")
                        logger.info(f"Sleeping for {SLEEP_TIME} secs...")
                        continue
                    # If the request could not be sent due to an invalid bearer token
                    if res['error']['code'] == 1000:
                        logger.error("Invalid bearer token")
                        quit()

                protected = res['movie']['is_protected']
                live_id = res['movie']['id']
                screen_id = res['broadcaster']['screen_id']
                user_image = res['broadcaster']['image']
                live_title = res['movie']['title']
                live_date = datetime.fromtimestamp(res['movie']['created'], tz=tz).strftime('%Y%m%d')
                live_url = f"https://twitcasting.tv/{screen_id}/movie/{live_id}"
                logger.info(f"{screen_id} is currently live at {live_url}")
                # If a live stream has been encountered for the first time
                if live_id not in user_ids[user_id]:
                    # Send notification to discord webhook
                    if WEBHOOK_URL is not None:
                        if protected:
                            live_text = f"{screen_id} has a `protected` live at {live_url}"
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
                            "thumbnail": {
                                "url": user_image
                            }
                        }]
                        }
                        requests.post(WEBHOOK_URL, json=message)

                    # Get password list
                    passwords = None
                    if protected:
                        passwords = get_passwords()

                    # Download the live stream
                    logger.info(f"Downloading {live_url}")
                    if not protected:
                        yt_dlp_args = ['start', 'cmd', '/c', 'yt-dlp', '--no-part', '--embed-metadata']
                        yt_dlp_args += ['-o', f'{output_path}\\{screen_id}\\{live_date} - {live_title} ({live_id}).%(ext)s', live_url]
                        result = subprocess.run(yt_dlp_args, shell=True)
                    elif protected and passwords is not None:
                        # Try downloading protected streams by trying all the passwords
                        # This will open up a console for each password so make sure the password list isn't too long...
                        for password in passwords:
                            yt_dlp_args = ['start', 'cmd', '/c', 'yt-dlp', '--no-part', '--embed-metadata']
                            yt_dlp_args += ['--video-password', password, '-o',
                                            f'{output_path}\\{screen_id}\\{live_date} - {live_title} ({live_id}).%(ext)s',
                                            live_url]
                            result = subprocess.run(yt_dlp_args, shell=True)
                    else:
                        logger.error(f"Failed to download protected stream at {live_url}")
                    user_ids[user_id].append(live_id)
                logger.info(f"Sleeping for {SLEEP_TIME} secs...")
        except Exception as e:
            logger.error(e)


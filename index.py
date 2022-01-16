import time
import requests
import json
import subprocess
from datetime import datetime
import const
from log import create_logger


SLEEP_TIME = const.SLEEP_TIME
bearer_token = const.bearer_token
WEBHOOK_URL = const.WEBHOOK_URL

# Dictionary comprehension of the list of twitcasting users
user_ids = {user_id: [] for user_id in const.user_ids}


if __name__ == "__main__":
    logger = create_logger("logfile.log")
    logger.info("Starting program")
    while True:
        try:
            logger.debug(user_ids)
            # Check whether user is currently like
            for user_id in user_ids:
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
                        time.sleep(1)
                        continue
                    # If the request could not be sent due to an invalid bearer token
                    if res['error']['code'] == 1000:
                        logger.error("Invalid bearer token")
                        quit()

                live_id = res['movie']['id']
                screen_id = res['broadcaster']['screen_id']
                user_image = res['broadcaster']['image']
                live_title = res['movie']['title']
                live_date = datetime.utcfromtimestamp(res['movie']['created']).strftime('%Y%m%d')
                live_url = f"https://twitcasting.tv/{screen_id}/movie/{live_id}"
                logger.info(f"{screen_id} is currently live at {live_url}")
                # If a live stream has been encountered for the first time
                if live_id not in user_ids[user_id]:
                    # Send notification to discord webhook
                    if WEBHOOK_URL is not None:
                        message = {"embeds": [{
                            "color": 13714,
                            "author": {
                                "name": screen_id,
                                "icon_url": user_image
                            },
                            "fields": [
                                {
                                    "name": res['movie']['title'],
                                    "value": f"{screen_id} is now live at {live_url}"
                                }
                            ],
                            "thumbnail": {
                                "url": user_image
                            }
                        }]
                        }
                        requests.post(WEBHOOK_URL, json=message)

                    # Download the live stream
                    yt_dlp_args = ['start', 'cmd', '/c', 'yt-dlp', '--no-part']
                    yt_dlp_args += ['-o', f'archive\\{screen_id}\\{live_date} - {live_title} ({live_id}).%(ext)s', live_url]
                    result = subprocess.run(yt_dlp_args, shell=True)
                    logger.info(f"Downloading {live_url}")
                    logger.info(f"Download Return Code: {result.returncode}")
                    user_ids[user_id].append(live_id)
                logger.info(f"Sleeping for {SLEEP_TIME} secs...")
                time.sleep(1)
        except Exception as e:
            logger.error(e)


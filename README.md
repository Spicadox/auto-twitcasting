# auto-twitcasting
### Overview
A script that tracks Twitcasting live streams(using the Twitcasting API) and sends it to a discord webhook. 
This script will also download the twitcasting streams that are live. 
This script checks whenever a stream goes live, then it can send the notification to a discord webhook, it can then also download the stream using yt-dlp, all while also logging all the information.

### Installation and Requirements
This program requires the requests module which can be installed using the requirements text file. A requirements text file has been included and the command `pip3 install -r requirements.txt` (or pip) can be used to install the required dependencies(except FFMPEG and yt-dlp).
[yt-dlp](https://github.com/yt-dlp/yt-dlp) is also required to download the livestream and must either be in the current working directory or added to PATH.

### How To Use
Since this program runs and obtains the Twitcasting live streams through the Twitcasting API, users must go to the Twitcasting developer page and create an application in order to obtain the `ClientID` and `ClientSecret`, both of which will be needed to obtain the `Access Token`(see the [Twitcasting API doc](https://apiv2-doc.twitcasting.tv/#get-access-token) for more detail) in order to use this script. 
Put the `Access Code` and configure all the necessary settings in the `const.py.example` file(if you haven't already renamed `const.py.example` to `const.py`, do so now).






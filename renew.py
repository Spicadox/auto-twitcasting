import datetime
import re
import json
import time
import dotenv
import logging
import os
import requests
from requests.adapters import HTTPAdapter
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


dotenv.load_dotenv()
dotenv_file = dotenv.find_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CALLBACK_URL = os.getenv("CALLBACK_URL")
USER_ID = os.getenv("USER_ID")
PASSWORD = os.getenv("PASSWORD")


def setup_selenium():
    try:
        print(" "*50, end='\r')
        logging.getLogger('WDM').setLevel(logging.ERROR)
        os.environ['WDM_LOG'] = "false"
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--lang=ja')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        return driver
    except WebDriverException as driverError:
        print(driverError)
        try:
            driver.quit()
        except NameError as nError:
            print(nError)
            pass
        return driverError


def accept_popup(driver):
    try:
        popup_button = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.ID, 'tw-dialog-0-result')))
        popup_button.click()
    except NoSuchElementException:
        try:
            popup_button = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.XPATH, '//button[text()="プライバシーポリシーに同意"]')))
            popup_button.click()
        except NoSuchElementException:
            pass
    finally:
        return


def login(driver, logger=None):
    try:
        login_button = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, '//span[text()="TwitCasting Account Login" or text()="キャスアカウント ログイン"]/parent::a')))
        login_button.click()
        driver.find_element(By.ID, "username").send_keys(USER_ID)
        driver.find_element(By.NAME, "password").send_keys(PASSWORD)
        driver.find_element(By.XPATH, "//input[@class='tw-button-primary tw-casaccount-button to-validate'] | //input[@value='ログイン']").click()
    except (NoSuchElementException, WebDriverException) as e:
        logger.error("Login Failed") if logger is not None else print("Login Failed")


def get_authorization_code(logger=None):
    url = f"https://apiv2.twitcasting.tv/oauth2/authorize?client_id={CLIENT_ID}&response_type=code"
    driver = setup_selenium()
    if isinstance(driver, WebDriverException):
        return None

    driver.get(url)
    try:
        accept_popup(driver)
        login(driver, logger)
        accept_popup(driver)
        if "login" in driver.current_url:
            return None
        try:
            accept_button = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, "//button[@class='tw-button-primary tw-button-large']")))
            accept_button.click()
        except NoSuchElementException as nError:
            print(nError)
            driver.find_element(By.XPATH, '//button[text()="連携アプリを許可"]')
    except WebDriverException as wdException:
        print(wdException)
        logger.error(wdException) if logger is not None else print(wdException)
        return None
    while driver.current_url == url:
        time.sleep(5)
    res_url = driver.current_url
    code = re.search(pattern="(.*code=)(.*)", string=res_url).group(2)
    logger.debug(f"Code: {code}") if logger is not None else print(f"Code: {code}")
    try:
        driver.quit()
    except Exception as e:
        logger.error(e)
    return code


def get_token_res(logger=None):
    code = get_authorization_code(logger)
    if code is None:
        return None

    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=5))
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    datas = {"code": code,
             "grant_type": "authorization_code",
             "client_id": CLIENT_ID,
             "client_secret": CLIENT_SECRET,
             "redirect_uri": CALLBACK_URL}
    try:
        res = session.post(headers=headers, data=datas, url="https://apiv2.twitcasting.tv/oauth2/access_token")
    except requests.exceptions.ConnectionError as cError:
        logger.debug(cError) if logger is not None else print(cError)
        return None
    except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as rError:
        logger.debug(rError) if logger is not None else print(rError)
        return None

    logger.debug(res.json()) if logger is not None else print(res.json())
    if res.status_code == 200:
        return res.json()
    else:
        logger.error(res.json()) if logger is not None else print(res.json())
        return None


def renew_token(logger=None):
    logger.info("Renewing bearer token...") if logger is not None else print("Renewing bearer token...")
    res = get_token_res(logger)
    if res is None:
        return None
    token = res['access_token']
    expire = res['expires_in']
    dotenv.set_key(dotenv_path=dotenv_file, key_to_set="BEARER_TOKEN", value_to_set=token)
    if logger is not None:
        logger.info(f"Renewed bearer token that expires in {datetime.timedelta(seconds=expire).days} days")
    return "Success"


if __name__ == "__main__":
    if dotenv_file == "" or CLIENT_ID is not None:
        USERNAME = input("Username: ")
        PASSWORD = input("Password: ")
        CLIENT_ID = input("Client ID: ")
        CLIENT_SECRET = input("Client Secret: ")
        CALLBACK_URL = input("Callback URL: ")
    res = get_token_res()
    BEARER_TOKEN = res['access_token']
    expire = res['expires_in']
    print(f"Renewed Bearer Token(expires in {datetime.timedelta(seconds=expire).days} days): {BEARER_TOKEN}")

import os
import datetime
import glob
import logging
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from stem import Signal
from stem.control import Controller
import requests
import time
import yaml
from yaml import load
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

time_format = '%Y-%m-%d %H:%M:%S'

def read_links(setlist_file):
    all_links = []
    with open(setlist_file,'r') as file:
        for link in file:
            all_links.append(link.strip())
    return all_links


def download_from_yout(webdriver, logger, link):

    logger.info(f"opening https://yout.com/video/?url={link}")
    webdriver.get(f"https://yout.com/video/?url={link}")

    try:
        wait = WebDriverWait(webdriver, 600)
        element = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[class='btn btn-primary btn-block btn-yout btn-recorder']")))
        element.click()
    except Exception as e:
        logger.error(e)

    return datetime.datetime.now().strftime(time_format)


def reset_circuit(logger):
    # signal TOR for a new connection 
    try:
        logger.info("\tresetting circuit")
        with Controller.from_port(port = 9050) as controller:
            controller.authenticate()
            controller.signal(Signal.NEWNYM)
    except Exception as e:
        logger.error(e)
    time.sleep(5)
    

def read_config(config_path):
    stream = open(config_path, 'r')
    configs = yaml.load(stream, Loader)
    return configs


def main():
    logger = logging.getLogger(__name__)
    log_format = '%(message)s'
    logging.basicConfig(filename='app.log', encoding='utf-8', level=logging.INFO, format=log_format)

    configs = read_config('.\\config.yaml')
    downloads_folder_path = configs['downloads_folder_path']
    setlist_path = configs['setlist_path']
    tor_browser_path = configs['tor_browser_path']
    tor_profile_path = configs['tor_profile_path']
    gecko_driver_path = configs['gecko_driver_path']

    logger.info("-----------------------------------------------------")
    logger.info(f"detecting downloads from {downloads_folder_path}")
    logger.info(f"setlist path at {setlist_path}")
    
    if (os.path.isdir(fr'{downloads_folder_path}') and os.path.exists(fr'{setlist_path}')):
        # open tor
        os.popen(fr'{tor_browser_path}')
        tor_start_time = datetime.datetime.now().strftime(time_format)
        logger.info(f"{tor_start_time}: tor started")

        # selenium initialization
        profile = webdriver.FirefoxProfile(fr'{tor_profile_path}')
        profile.set_preference('network.proxy.type', 1)
        profile.set_preference('network.proxy.socks', '127.0.0.1')
        profile.set_preference('network.proxy.socks_port', 9051)
        profile.set_preference("network.proxy.socks_remote_dns", False)
        profile.update_preferences()
        service = Service(executable_path=fr'{gecko_driver_path}')
        driver = webdriver.Firefox(service = service)

        # get all links to download
        all_links = read_links(setlist_path)
        logger.info("setlist links:")
        for link in all_links:
            logger.info(f"\t{link}")

        count = 1
        download_limit = 3

        # main file detector logic
        for link_to_download in all_links:
            all_files = glob.glob(downloads_folder_path + "\\*.mp3")

            try:
                if len(all_files) > 0:
                    all_files.sort(key=os.path.getmtime, reverse=True)
                    latest_filename = all_files[0]
                    latest_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(latest_filename)).strftime(time_format)

                    download_from_yout(driver, logger, link_to_download)

                    # wait for .mp3 to completely download before looping again (occurs when part file no longer exists)
                    exists_part = False
                    while True:
                        part_files = glob.glob(downloads_folder_path + "\\*.part")
                        print(len(part_files), exists_part)
                        if len(part_files) > 0:
                            exists_part = True
                        if exists_part and len(part_files) == 0:
                            break

                    logger.info(f"\t{latest_mtime}: {latest_filename} download completed")

                    if count == download_limit:
                        count = 1
                        reset_circuit(logger)
                    
                    else:
                        count += 1
            
            except FileNotFoundError:
                logger.error(f"{datetime.datetime.now().strftime(time_format)}: 404")


def get_tor_session():
    session = requests.session()
    session.proxies = {'http':  'socks5h://127.0.0.1:9051',
                       'https': 'socks5h://127.0.0.1:9051'}
    return session

main()
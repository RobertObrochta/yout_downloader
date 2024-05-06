import os
import subprocess
import datetime
import glob
import logging
import keyboard
import pygetwindow
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from stem import Signal
from stem.control import Controller
import time
import yaml
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

time_format = '%Y-%m-%d %H:%M:%S'

def read_setlist(setlist_file):
    '''Returns (track, artist, url)'''
    song_data = []
    with open(setlist_file,'r') as file:
        for link in file:
            url_start_index = link.find("https://")
            track_info = link[ : url_start_index].strip()
            url = link[url_start_index : ].strip()
            track, artist = get_track_and_artist(track_info)
            song_data.append((track, artist, url))
    return song_data


def get_track_and_artist(track_info):
    '''
    Returns artist and track information with the format "Track Title - Artist" (or just assumes track name if no '-' is given)
    '''
    if track_info.find("-") != -1:
        artist_track_split = track_info.split("-")
        artist = artist_track_split[0].strip()
        track = artist_track_split[1].strip()
    else:
        artist = ""
        track = track_info

    return track, artist


def download_from_yout(webdriver, logger, link, track, artist):
    '''
    Opens yout.com at the given link with the given track info, autofills, and downloads
    '''
    logger.info(f"opening https://yout.com/video/?url={link}")
    #song, artist = get_yt_song_and_artist(link)
    webdriver.get(f"https://yout.com/video/?url={link}")

    try:
        wait = WebDriverWait(webdriver, 600)
        download_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[class='btn btn-primary btn-block btn-yout btn-recorder']")))
        title_input = webdriver.find_element(By.NAME, "settings_title")
        artist_input = webdriver.find_element(By.NAME, "settings_artist")
        if len(track) > 0:
            title_input.clear()
            title_input.send_keys(track)

        if len(artist) > 0:
            artist_input.clear()
            artist_input.send_keys(artist)
        download_btn.click()
    except Exception as e:
        logger.error(e)


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


def reopen_tor(logger, driver, tor_process):
    # closes and reopens tor, webdriver 
    try:
        time.sleep(1.5)
        driver.close()
        time.sleep(1.5)
        tor_process.terminate()
        tor_process.kill()
        time.sleep(1.5)
    except Exception as e:
        logger.error(e)


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
        p = subprocess.Popen(fr"{tor_browser_path}")
        tor_start_time = datetime.datetime.now().strftime(time_format)
        logger.info(f"{tor_start_time}: tor started")

        # selenium initialization
        profile = webdriver.FirefoxProfile(fr'{tor_profile_path}')
        options = webdriver.FirefoxOptions()
        profile.set_preference("browser.download.dir", downloads_folder_path)
        profile.set_preference('profile', tor_profile_path)
        profile.set_preference('network.proxy.type', 1)
        profile.set_preference('network.proxy.socks', '127.0.0.1')
        profile.set_preference('network.proxy.socks_port', 9051)
        profile.set_preference("network.proxy.socks_remote_dns", False)
        profile.update_preferences()
        options.profile = profile
        service = Service(executable_path=fr'{gecko_driver_path}')
        driver = webdriver.Firefox(service = service, options=options)

        # get all song data for download
        song_data = read_setlist(setlist_path)
        logger.info("setlist links:") 
        for data in song_data:
            logger.info(f"\t{data[0], data[1], data[2]}")

        count = 1
        download_limit = 3

        # main file detector logic
        for data in song_data:
            all_files = glob.glob(downloads_folder_path + "\\*.mp3")
            track = data[0]
            artist = data[1]
            link_to_download = data[2]
            try:
                if len(all_files) > 0:
                    all_files.sort(key=os.path.getmtime, reverse=True)
                    latest_filename = all_files[0]
                    latest_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(latest_filename)).strftime(time_format)

                    download_from_yout(driver, logger, link_to_download, track, artist)

                    # wait for .mp3 to completely download before looping again (occurs when part file no longer exists)
                    exists_part = False
                    while True:
                        part_files = glob.glob(downloads_folder_path + "\\*.part")
                        if len(part_files) > 0:
                            exists_part = True
                        if exists_part and len(part_files) == 0:
                            break

                    logger.info(f"\t{latest_mtime}: {latest_filename} download completed")

                    if count == download_limit:
                        count = 1
                        reopen_tor(logger, driver, p)
                        driver = webdriver.Firefox(service = service, options=options)
                    
                    else:
                        count += 1
            
            except FileNotFoundError:
                logger.error(f"{datetime.datetime.now().strftime(time_format)}: 404")


main()
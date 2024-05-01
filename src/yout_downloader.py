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
import time
import yaml
try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader
import json
import re
import requests

time_format = '%Y-%m-%d %H:%M:%S'

def read_setlist(setlist_file):
    '''Returns (track, artist, url)'''
    song_data = []
    with open(setlist_file,'r') as file:
        for link in file:
            track_info_url_split = link.split("*")
            track_info = track_info_url_split[0].strip()
            track, artist = get_track_and_artist(track_info)
            if len(track_info_url_split) > 1:
                url = track_info_url_split[1].strip()
                song_data.append((track, artist, url))
            else:
                print("missing data in setlist")
    return song_data


def get_yt_song_and_artist(youtube_url):
    # big thanks for u/JoshIsMahName for this function
    song_name = None
    artist_name = None
 
    r = requests.get(youtube_url)
 
    raw_matches = re.findall('(\\{"metadataRowRenderer":.*?\\})(?=,{"metadataRowRenderer")', r.text)
    json_objects = [json.loads(m) for m in raw_matches if '{"simpleText":"Song"}' in m or '{"simpleText":"Artist"}' in m] # [Song Data, Artist Data]
 
    if len(json_objects) == 2:
        song_contents = json_objects[0]["metadataRowRenderer"]["contents"][0]
        artist_contents = json_objects[1]["metadataRowRenderer"]["contents"][0]
 
        if "runs" in song_contents:
            song_name = song_contents["runs"][0]["text"]
        else:
            song_name = song_contents["simpleText"]
            
        if "runs" in artist_contents:
            artist_name = artist_contents["runs"][0]["text"]
        else:
            artist_name = artist_contents["simpleText"]
 
    print(song_name, artist_name)
    return song_name, artist_name


def get_track_and_artist(track_info):
    artist_track_split = track_info.split("-")
    artist = artist_track_split[0].strip()
    track = artist_track_split[1].strip()

    return track, artist


def download_from_yout(webdriver, logger, link, track, artist):

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
                        reset_circuit(logger)
                    
                    else:
                        count += 1
            
            except FileNotFoundError:
                logger.error(f"{datetime.datetime.now().strftime(time_format)}: 404")


main()
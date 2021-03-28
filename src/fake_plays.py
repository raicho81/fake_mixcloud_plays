from selenium import webdriver
from selenium.common.exceptions import WebDriverException
import time
import random
import math
import json
import itertools
import signal
import os
import sys


stop = False
if os.name == "posix":
    handled_signals = {
                        signal.SIGTERM: "SIGTERM",
                        signal.SIGHUP:  "SIGHUP",
                        signal.SIGKILL: "SIGKILL"
                       }
else:
    handled_signals = None


# Flush print output ;)
def print_flush(*args):
    print(*args, flush=True)


def signal_handler(signum, frame):
    print_flush('Signal handler called with signal {}'.format(handled_signals[signum]))
    global stop
    stop = True


def install_signal_handlers():
    # Install signal handler(s) to leverage grace-full stop if OS is POSIX
    if os.name == "posix":
        print_flush(">>> Installing signal handlers START >>>")
        for signal_code in handled_signals.keys():
            print_flush("Installing signal handler for signal {}".format(handled_signals[signal_code]))
            signal.signal(signal_code, signal_handler)
            print_flush("Installed signal handler for signal {}".format(handled_signals[signal_code]))
        print_flush("<<< Installing signal handlers END <<<")


def load_config():
    config = None
    try:
        with open('config.json') as json_file:
            config = json.load(json_file)
            print_flush(">>> Loaded configuration START >>>")
            for _ in config:
                print_flush("{0: <20}: {1}".format(_, config[_]))
            print_flush("<<< Loaded configuration END <<<")
    except IOError as e:
        print(e)
    return config


def check_config(config):
    if config is None:
        print_flush("Config not loaded! Aborting.")
        sys.exit(1)
    if config['mix_url'] == "":
        print_flush("mix_url can't be empty! Aborting.")
        sys.exit(1)
    if config['speed'] != "fast" and config['speed'] != "random":
        print_flush("Invalid configuration: 'speed' must be 'fast' or 'random'")
        print_flush("Defaulting to speed=fast")
        config['speed'] = 'fast'
    # Other unimplemented checks


def make_chrome_options(config):
    # Add Chrome arguments
    chrome_options = webdriver.ChromeOptions()
    chrome_options.headless = config['headless_chrome']
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    if config['proxy_address'] != "" and config['proxy_port'] != 0:
        chrome_options.add_argument("--proxy-server={}:{}".format(config['proxy_address'], config['proxy_port']))

    print_flush(">>> Chrome arguments START >>>")

    for a in chrome_options.arguments:
        print("{}".format(a))
    print_flush("<<< Chrome arguments END <<<")

    return chrome_options


def start_play_if_stopped(browser, config):
    print_flush("Trying to start playback if not started")
    try:
        play_btn = browser.find_element_by_xpath(config['play_button_xpath'])
        play_btn.click()    # start playback if not started
        print_flush("Playback started")
    except WebDriverException as e:
        print_flush(e)


def main():
    install_signal_handlers()

    refresh_count = itertools.count(1)

    # Load config and then check it for errors
    config = load_config()
    check_config(config)

    # Make Chrome options
    chrome_options = make_chrome_options(config)

    # Start Chrome etc.
    try:
        print_flush("Trying to start Chrome")
        browser = webdriver.Chrome(options=chrome_options)
        print_flush("Chrome started")
        print_flush("Trying to open URL: {}".format(config['mix_url']))
        browser.get(config['mix_url'])
        print_flush("Loaded: {}".format(config['mix_url']))
        time.sleep(config['wait_time_before_try_play'])
        start_play_if_stopped(browser, config)
    except WebDriverException as e:
        print_flush(e)

    # Start reloading the page after random time (speed=slow) or fixed time (speed=fast)
    while not stop:
        if config['speed'] == 'random':
            time.sleep(abs(math.ceil(random.gauss(config['random_wait_mu'], config['random_wait_sigma']))))
        if config['speed'] == 'fast':
            time.sleep(config['fast_wait_time'])

        try:
            browser.refresh()
            print_flush("Refreshed page (count={})".format(refresh_count.__next__()))
            browser.switch_to.alert.accept()
            print_flush("Closed Alert")
        except WebDriverException as e:
            s = str(e)
            if not s.find("no such alert"):
                print_flush(s)

        time.sleep(config['wait_time_before_try_play'])
        start_play_if_stopped(browser, config)

    try:
        print_flush("Trying to close Chrome")
        browser.close()
        print_flush("Closed Chrome")
    except WebDriverException as e:
        print_flush(e)

    print_flush("Stopped")


if __name__ == "__main__":
    main()

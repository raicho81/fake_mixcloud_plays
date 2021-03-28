from selenium import webdriver
from selenium.common.exceptions import WebDriverException
import random
import math
import json
import itertools
import signal
import os
import sys
import threading
from datetime import datetime
import inspect


# More verbose log
DEBUG = False

# These 2 variables are used to create interruptable timed-waits instead of time.sleep
# which is not interruptable so we can stop grace-fully when an appropriate OS signal is received.
stop = False
wait_cond = threading.Condition()
# # #

if os.name == "posix":
    handled_signals = {
                        signal.SIGTERM: "SIGTERM",
                        signal.SIGHUP:  "SIGHUP",
                        signal.SIGABRT: "SIGABRT"
                       }
else:
    handled_signals = None  # Only signals on POSIX systems are handled for now


# Add time and etc. and then flush the print output
def log(*args):
    t = datetime.now().time()
    if DEBUG:
        caller_frame_record = inspect.stack()[1]    # 0 represents this line, 1 represents line at caller
        frame = caller_frame_record[0]              # get the caller stack frame
        info = inspect.getframeinfo(frame)          # parse some info from the caller stack frame
        current_time_etc = "[{0:02}:{1:02}:{2:02}:{3:06}, " \
                           "{4}:{5:<25}:{6:<5}]".format(t.hour, t.minute, t.second, t.microsecond,
                                                                 info.filename, info.function, info.lineno)
    else:
        current_time_etc = "[{0:02}:{1:02}:{2:02}:{3:06}]".format(t.hour, t.minute, t.second, t.microsecond)

    print(current_time_etc, *args, flush=True)


def notify_wait_cond(cond):
    with cond:
        cond.notifyAll()


def signal_handler(signum, frame):
    log('{} signal received. Will try to stop grace-fully'.format(handled_signals[signum]))
    global stop
    stop = True
    notify_wait_cond(wait_cond)


def install_signal_handlers():
    # Install signal handler(s) to leverage grace-full stop if OS is POSIX
    if os.name == "posix":
        log(">>> Installing signal handlers START >>>")
        for signal_code in handled_signals.keys():
            try:
                signal.signal(signal_code, signal_handler)
                log("Installed signal handler for signal {}".format(handled_signals[signal_code]))
            except OSError as e:
                log(e)
        log("<<< Installing signal handlers END <<<")


def load_config():
    global DEBUG
    config = None
    try:
        with open('config.json') as json_file:
            config = json.load(json_file)
            if not ('debug' in config.keys()) or not isinstance(config['debug'], bool):
                log("Error: 'debug' attribute missing in config file or is with invalid value! Defaulting to config["
                    "'debug']==False")
            else:
                DEBUG = config['debug']
            log(">>> Loaded configuration START >>>")
            for _ in config:
                log("{0: <30}: {1}".format(_, config[_]))
            log("<<< Loaded configuration END <<<")
    except IOError as e:
        print(e)
    return config


def check_config(config):
    if config is None:
        log("Config not loaded! Aborting.")
        sys.exit(1)
    if config['mix_url'] == "":
        log("mix_url can't be empty! Aborting.")
        sys.exit(1)
    if not ('speed' in config.keys()) or config['speed'] != "fast" and config['speed'] != "random":
        log("Error: invalid or missing 'speed' parameter in config must be 'fast' or 'random'")
        log("Defaulting to config['speed']=='fast'")
        config['speed'] = 'fast'
    if not ('headless_chrome' in config.keys()) or not isinstance(config['headless_chrome'], bool):
        log("Error: invalid or missing 'headless_chrome' parameter in config must be boolean")
        log("Defaulting to config['headless_chrome']==True")
        config['headless_chrome'] = True
    # Other unimplemented checks and defaults and etc. Well, I was too lazy to make them all :D
    # This a POC anyway (I am trying to coin a decent excuse :D)


def make_chrome_options(config):
    # Add Chrome arguments
    chrome_options = webdriver.ChromeOptions()
    chrome_options.headless = config['headless_chrome']
    chrome_options.add_argument("--mute-audio")
    if os.name == "posix":
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    if config['proxy_address'] != "" and config['proxy_port'] != 0:
        chrome_options.add_argument("--proxy-server={}:{}".format(config['proxy_address'], config['proxy_port']))

    log(">>> Chrome arguments START >>>")
    for a in chrome_options.arguments:
        log("{}".format(a))
    log("<<< Chrome arguments END <<<")

    return chrome_options


def start_play_if_stopped(browser, config):
    if stop:
        return
    log("Trying to start playback if not started")
    try:
        play_btn = browser.find_element_by_xpath(config['play_button_xpath'])
        play_btn.click()    # start playback if not started
        log("Playback started")
    except WebDriverException as e:
        msg = str(e)
        if msg.find("no such element:"):
            log("Playback is already started")
        else:
            log(msg)


# Start an interruptable timed-wait on Condition (Variable) instead of time.sleep, which is not interruptable.
# To interrupt a timed-wait we need to simply call notify_wait_cond before the duration has expired
# I did this to implement grace-full stops when an appropriate signal is received from the OS.
def wait_for(duration, cond):
    if stop:
        return
    if duration <= 0:
        return
    log("Will stay Idle for {0}h {1}m {2}s ({3} second(s))".format(duration // (60 * 60), (duration // 60) % 60, duration % 60, duration))
    with cond:
        cond.wait(duration)


def main():
    log("[    *** *** *** Starting *** *** ***    ]")
    refresh_count = itertools.count(1)

    # Load config and then check it for errors
    config = load_config()
    check_config(config)

    install_signal_handlers()

    # Make Chrome options
    chrome_options = make_chrome_options(config)

    # Start Chrome etc.
    try:
        log("Trying to start Chrome")
        browser = webdriver.Chrome(options=chrome_options)
        log("Chrome started")
        log("Trying to open URL: {}".format(config['mix_url']))
        browser.get(config['mix_url'])
        log("Loaded: {}".format(config['mix_url']))
        wait_for(config['wait_time_before_try_play'], wait_cond)
        start_play_if_stopped(browser, config)
    except WebDriverException as e:
        log(e)

    # Reload the page after random time (config['speed']=='slow') or fixed time (config['speed']=='fast')
    while not stop:
        if config['speed'] == 'random':
            wait_for(abs(math.ceil(random.gauss(config['random_wait_mu'], config['random_wait_sigma']))), wait_cond)
        if config['speed'] == 'fast':
            wait_for(config['fast_wait_time'], wait_cond)

        if stop:
            break

        try:
            browser.refresh()
            log("Refreshed page (count={})".format(refresh_count.__next__()))
            browser.switch_to.alert.accept()
            log("Closed Alert")
        except WebDriverException as e:
            msg = str(e)
            if not msg.find("no such alert"):
                log(msg)

        wait_for(config['wait_time_before_try_play'], wait_cond)
        start_play_if_stopped(browser, config)

    try:
        log("Trying to close Chrome")
        browser.close()
        log("Killed Chrome{} Whew :) It wasn't so hard, was it :)".format(' - The Head-Less :)' if config['headless_chrome'] else "."))
    except WebDriverException as e:
        log(e)

    log("[    *** *** *** Stopped *** *** ***    ]")


if __name__ == "__main__":
    main()

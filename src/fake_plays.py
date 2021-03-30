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
import functools

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
        signal.SIGHUP: "SIGHUP",
        signal.SIGABRT: "SIGABRT"
    }
else:
    handled_signals = None  # Only signals on POSIX systems are handled for now


# Add time and etc. and then flush the print output
def log(*args):
    t = datetime.now().time()
    if DEBUG:
        caller_frame_record = inspect.stack()[1]  # 0 represents this line, 1 represents line at caller
        frame = caller_frame_record[0]  # get the caller stack frame
        info = inspect.getframeinfo(frame)  # parse some info from the caller stack frame
        current_time_etc = "[{0:02}:{1:02}:{2:02}:{3:06}, " \
                           "{4}:{5:<25}:{6:<5}]".format(t.hour, t.minute, t.second, t.microsecond,
                                                        info.filename, info.function, info.lineno)
    else:
        current_time_etc = "[{0:02}:{1:02}:{2:02}:{3:06}]".format(t.hour, t.minute, t.second, t.microsecond)
    print(current_time_etc, *args, flush=True)


def notify_wait_cond(cond):
    with cond:
        cond.notifyAll()


def global_stop():
    log("Setting global stop=true. Will stop soon.")
    global stop
    stop = True


def signal_handler(signum, frame):
    log('{} signal received. Will try to stop grace-fully'.format(handled_signals[signum]))
    global_stop()
    notify_wait_cond(wait_cond)


def install_signal_handlers():
    # Install signal handler(s) to leverage grace-full stop if OS is POSIX
    os_name = os.name
    log("os.name=={}".format(os_name))
    if os_name == "posix":
        log(">>> Installing signal handlers START >>>")
        for signal_code in handled_signals.keys():
            try:
                signal.signal(signal_code, signal_handler)
                log("Installed signal handler for signal {}".format(handled_signals[signal_code]))
            except OSError as e:
                log(e)
        log("<<< Installing signal handlers END <<<")


def make_next_proxy_pair_func(proxy_list, usage=None):
    def wrapper(gen):
        for x in gen():
            return x

    def make_proxy_pairs_generator(proxy_list, usage=None):
        if usage == 'cycle':
            cycle_proxy_gen = itertools.cycle(proxy_list)

            def cycle_proxy_pairs_generator():
                for proxy_pair in cycle_proxy_gen:
                    yield proxy_pair
                yield [None, None]

            return cycle_proxy_pairs_generator
        elif usage == 'one_shot':
            one_shot_count = itertools.count(0)

            def one_shot_proxy_pairs_generator():
                for c in one_shot_count:
                    try:
                        yield proxy_list[c]
                    except IndexError as e:
                        yield [None, None]

            return one_shot_proxy_pairs_generator
        else:
            raise NotImplementedError

    pg = make_proxy_pairs_generator(proxy_list, usage)
    wrapper_partial = functools.partial(wrapper, pg)
    return wrapper_partial


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
    if config['proxy_list']:  # we have present a proxy list
        config['next_proxy_pair_func'] = make_next_proxy_pair_func(config['proxy_list'], config['proxy_list_usage'])
    else:
        config['next_proxy_pair_func'] = None
    # Other unimplemented checks and defaults and etc. Well, I was too lazy to make them all :D
    # This a POC anyway (I am trying to coin a decent excuse :D)


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


def make_chrome_options(config):
    # Add Chrome arguments
    chrome_options = webdriver.ChromeOptions()
    chrome_options.headless = config['headless_chrome']
    chrome_options.add_argument("--mute-audio")
    if os.name == "posix":
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
    if config['next_proxy_pair_func'] is not None:  # There are proxys/ports lists present
        next_proxy_pair = config['next_proxy_pair_func']()
        if next_proxy_pair != [None, None]:
            chrome_options.add_argument("--proxy-server={}:{}".format(*next_proxy_pair))
        else:
            global_stop()
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
        play_btn.click()  # start playback if not started
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
    log("Will stay Idle for {0}h {1}m {2}s ({3} second(s))".format(duration // (60 * 60), (duration // 60) % 60,
                                                                   duration % 60, duration))
    with cond:
        cond.wait(duration)


def browser_start(config):
    log("Trying to start Chrome")
    # Make Chrome options
    options = make_chrome_options(config)
    if stop:
        return None, False
    try:
        # Start Chrome etc.
        browser = webdriver.Chrome(options=options)
        log("Chrome started")
        log("Trying to open URL: {}".format(config['mix_url']))
        browser.get(config['mix_url'])
        log("Loaded successfully {}".format(config['mix_url']))
        wait_for(config['wait_time_before_try_play'], wait_cond)
        start_play_if_stopped(browser, config)
    except WebDriverException as e:
        msg = str(e)
        log(msg)
        if msg.find("net::ERR_PROXY_CONNECTION_FAILED"):
            return browser, False
    return browser, True


def browser_stop(browser, config):
    try:
        log("Trying to close Chrome")
        browser.close()
        log("Killed Chrome{} Whew :) It wasn't so hard, was it :)".format(' - The Head-Less :)' if config['headless_chrome'] else "."))
    except WebDriverException as e:
        log(e)


def browser_refresh(browser, config, refresh_count):
    if stop:
        return
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


def init():
    log("Initializing")
    refresh_count = itertools.count(1)
    # Load config and then check it for errors
    config = load_config()
    check_config(config)
    install_signal_handlers()
    return refresh_count, config


def main():
    log("[    *** *** *** Starting *** *** ***    ]")
    refresh_count, config = init()
    browser, success = browser_start(config)
    # Reload the page after random time (config['speed']=='slow') or fixed time (config['speed']=='fast')
    # If proxy list is present -> Close the browser and start new instance
    # (with new options i.e. proxy) instead of reloading
    while not stop or not config['proxy_list'] and not success:
        if config['speed'] == 'random' and success:
            wait_for(abs(math.ceil(random.gauss(config['random_wait_mu'], config['random_wait_sigma']))), wait_cond)
        if config['speed'] == 'fast' and success:
            wait_for(config['fast_wait_time'], wait_cond)
        if stop:
            break
        if not config['proxy_list']:
            browser_refresh(browser, config, refresh_count)
        else:
            browser_stop(browser, config)
            browser, success = browser_start(config)

    browser is None or browser_stop(browser, config)
    log("[    *** *** *** Stopped *** *** ***    ]")


if __name__ == "__main__":
    main()

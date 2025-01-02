#!/usr/bin/env python3

import argparse
import os
import time
from modules import selenium_module
from modules.helpers import resolve_host
from multiprocessing import Manager, Process, current_process
from signal import signal, SIGINT
try:
    from pyvirtualdisplay import Display
except ImportError:
    print('[*] pyvirtualdisplay not found.')
    print('[*] Please run the script in the setup directory!')
    sys.exit()

def create_cli_parser():
    parser = argparse.ArgumentParser(
        add_help=False, description="EyeWitness is a tool used to capture screenshots from a list of URLs")
    parser.add_argument('-h', '-?', '--h', '-help',
                        '--help', action="store_true", help=argparse.SUPPRESS)
    input_options = parser.add_argument_group('Input Options')
    input_options.add_argument('-f', metavar='Filename', default=None,
                               help='Line-separated file containing URLs to capture')
    input_options.add_argument('--single', metavar='Single URL', default=None,
                               help='Single URL/Host to capture')
    input_options.add_argument('--no-dns', default=False, action='store_true',
                               help='Skip DNS resolution when connecting to websites')
    timing_options = parser.add_argument_group('Timing Options')
    timing_options.add_argument('--timeout', metavar='Timeout', default=7, type=int,
                                help='Maximum number of seconds to wait while requesting a web page (Default: 7)')
    timing_options.add_argument('--threads', metavar='# of Threads', default=10,
                                type=int, help='Number of threads to use while using file based input')
    timing_options.add_argument('--max-retries', default=1, metavar='Max retries on a timeout'.replace('    ', ''), type=int,
                                help='Max retries on timeouts')
    http_options = parser.add_argument_group('Web Options')
    http_options.add_argument('--user-agent', metavar='User Agent',
                              default=None, help='User Agent to use for all requests')
    http_options.add_argument('--proxy-ip', metavar='127.0.0.1', default=None,
                              help='IP of web proxy to go through')
    http_options.add_argument('--proxy-port', metavar='8080', default=None,
                              type=int, help='Port of web proxy to go through')
    http_options.add_argument('--proxy-type', metavar='socks5', default="http",
                              help='Proxy type (socks5/http)')
    http_options.add_argument('--show-selenium', default=False,
                              action='store_true', help='Show display for selenium')
    http_options.add_argument('--resolve', default=False,
                              action='store_true', help=("Resolve IP/Hostname for targets"))
    http_options.add_argument('--width', metavar="1366", default=1366, type=int,
                              help='Screenshot window image width size. 600-7680 (eg. 1920)')
    http_options.add_argument('--height', metavar="768", default=768, type=int,
                              help='Screenshot window image height size. 400-4320 (eg. 1080)')
    output_options = parser.add_argument_group('Output Options')
    output_options.add_argument('-d', metavar='Directory Name',
                                default=None,
                                help='Directory name for storing screenshots')
    resume_options = parser.add_argument_group('Resume Options')
    resume_options.add_argument('--resume', metavar='ew.db',
                                default=None, help='Path to db file if you want to resume')
    args = parser.parse_args()
    args.date = time.strftime('%Y/%m/%d')
    args.time = time.strftime('%H:%M:%S')

    if args.h:
        parser.print_help()
        sys.exit()

    if args.f is None and args.single is None and args.resume is None:
        print("[*] Error: You didn't specify a file! I need a file containing URLs!")
        parser.print_help()
        sys.exit()

    if ((args.f is not None) and not os.path.isfile(args.f)):
        print("[*] Error: You didn't specify the correct path to a file. Try again!\n")
        parser.print_help()
        sys.exit()

    if args.width < 600 or args.width >7680:
        print("\n[*] Error: Specify a width >= 600 and <= 7680, for example 1920.\n")
        parser.print_help()
        sys.exit()

    if args.height < 400 or args.height >4320:
        print("\n[*] Error: Specify a height >= 400 and <= 4320, for example, 1080.\n")
        parser.print_help()
        sys.exit()

    if args.proxy_ip is not None and args.proxy_port is None:
        print("[*] Error: Please provide a port for the proxy!")
        parser.print_help()
        sys.exit()

    if args.proxy_port is not None and args.proxy_ip is None:
        print("[*] Error: Please provide an IP for the proxy!")
        parser.print_help()
        sys.exit()
        
    if args.d is not None:
        if not os.path.exists(args.d):
            os.makedirs(args.d)
    else:
        output_folder = args.date.replace('/', '-') + '_' + args.time.replace(':', '')
        args.d = os.path.join(os.getcwd(), output_folder)
        os.makedirs(args.d)

    args.log_file_path = os.path.join(args.d, 'logfile.log')
    return args

def capture_screenshots(cli_parsed, targets, lock, counter, user_agent=None):
    if cli_parsed.web:
        create_driver = selenium_module.create_driver
        capture_host = selenium_module.capture_host

    with lock:
        driver = create_driver(cli_parsed, user_agent)
    try:
        while True:
            http_object = targets.get()
            if http_object is None:
                break

            print('Attempting to screenshot {0}'.format(http_object.remote_system))
            http_object.resolved = resolve_host(http_object.remote_system)
            if user_agent is None:
                http_object, driver = capture_host(
                    cli_parsed, http_object, driver)
            counter[0].value += 1
            if counter[0].value % 15 == 0:
                print('\x1b[32m[*] Completed {0} out of {1} services\x1b[0m'.format(counter[0].value, counter[1]))
    except KeyboardInterrupt:
        pass
    driver.quit()

def multi_mode(cli_parsed):
    m = Manager()
    targets = m.Queue()
    lock = m.Lock()
    multi_counter = m.Value('i', 0)
    display = None

    def exitsig(*args):
        if current_process().name == 'MainProcess':
            print('')
            print('Quitting...')
        os._exit(1)

    signal(SIGINT, exitsig)

    url_list = []
    if cli_parsed.f:
        with open(cli_parsed.f, 'r') as f:
            url_list = f.read().splitlines()
    if cli_parsed.single:
        url_list.append(cli_parsed.single)

    for url in url_list:
        targets.put(url)

    if cli_parsed.web:
        if not cli_parsed.show_selenium:
            display = Display(visible=0, size=(1920, 1080))
            display.start()

        num_threads = min(cli_parsed.threads, len(url_list))
        for i in range(num_threads):
            targets.put(None)
        try:
            workers = [Process(target=capture_screenshots, args=(
                cli_parsed, targets, lock, (multi_counter, len(url_list)))) for _ in range(num_threads)]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
        except Exception as e:
            print(str(e))

    if display is not None:
        display.stop()

if __name__ == "__main__":
    cli_parsed = create_cli_parser()
    if cli_parsed.single or cli_parsed.f:
        multi_mode(cli_parsed)
    print('Finished in {0} seconds'.format(time.time() - start_time))

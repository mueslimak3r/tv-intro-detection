import os
import sys
import getopt
from pathlib import Path
from datetime import datetime

config_path = os.environ['CONFIG_DIR'] if 'CONFIG_DIR' in os.environ else './config'
data_path = os.environ['DATA_DIR'] if 'DATA_DIR' in os.environ else os.path.join(config_path, 'data')

session_timestamp = datetime.now().strftime("%Y_%m_%d-%I_%M_%S_%p")


def print_debug(a=[], log=True, log_file=False):
    # Here a is the array holding the objects
    # passed as the argument of the function
    output = ' '.join([str(elem) for elem in a])
    if log:
        print(output, file=sys.stderr)
    if log_file:
        log_path = os.path.join(config_path, 'logs')
        Path(log_path).mkdir(parents=True, exist_ok=True)
        with open(os.path.join(log_path, 'log_%s.txt' % session_timestamp), "a") as logger:
            logger.write(output + '\n')


def get_video(name='', log_level=0, log_file=False, cleanup=True, log_timestamp=None):
    print(name)


def main(argv):

    name = ''
    log_level = 0
    cleanup = False
    log = False
    try:
        opts, args = getopt.getopt(argv, "hi:dvcl")
    except getopt.GetoptError:
        print_debug(['ytube_scrape.py -i <show season> -v (verbose - some logging) -d (debug - most logging) -l (log to file)\n'])
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print_debug(['decode.py -i <path> -v (verbose - some logging) -d (debug - most logging) -l (log to file)\n'])
            sys.exit()
        elif opt == '-i':
            name = arg
        elif opt == '-l':
            log = True
        elif opt == '-d':
            log_level = 2
        elif opt == '-v':
            log_level = 1

    result = get_video(name=name, log_level=log_level, log_file=log, cleanup=cleanup)
    print(result)


if __name__ == "__main__":
    main(sys.argv[1:])

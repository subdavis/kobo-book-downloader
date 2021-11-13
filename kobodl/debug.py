from datetime import datetime

from kobodl.globals import Globals


def debug_data(*args):
    if Globals.Debug:
        with open('./debug.log', 'a') as debuglog:
            debuglog.write(str(datetime.now()))
            debuglog.write('\n')
            for stringable in args:
                debuglog.write(str(stringable))
                debuglog.write('\n')

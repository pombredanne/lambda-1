from __future__ import print_function
import sys
import imp
import os
import json
import string
import logging.config
import time
import uuid


debugging = False

debugging and print ('loading...')


class Context(object):
#FIXME attributes should be set on start
    function_name = None
    function_version = None
    invoked_function_arn = None
    memory_limit_in_mb = None
    aws_request_id = None
    log_group_name = None
    log_stream_name = None
    identity = None
    client_context = None

    def __init__(self):
        self.function_name = getAWS_LAMBDA_FUNCTION_NAME()
        self.function_version = getAWS_LAMBDA_FUNCTION_VERSION()
        self.aws_request_id = getREQUEST_ID()
        self.memory_limit_in_mb = int(getTASK_MAXMEM() / 1024 / 1024)

    def get_remaining_time_in_millis(self):
        remaining = plannedEnd - time.time()
        if remaining < 0:
            remaining = 0
        return remaining * 1000

    def log(self, msg):
        print (msg, end='')
        return


class Payload(object):

    def __init__(self, js):
        self.__dict__ = json.loads(js)

    def __repr__(self):
        return json.dumps(self.__dict__, sort_keys=True)

    def __str__(self):
        return str(self.__dict__)


class DynaCaller(object):

    def __init__(self, module, name):
        self.moduleName = module
        self.funcName = name

    def locateFunc(self):
        self.module = (self.locateModuleInMountFolder()
            or self.locateModuleDefault())
        if self.module is None:
            print ("Failed to locate a module", file=sys.stderr)
            return False
        self.func = getattr(self.module, self.funcName)
        if self.func is None:
            print ("Failed to locate a function inside module", file=sys.stderr)
            return False
        return True

    def locateModuleDefault(self):
        try:
            return __import__(self.moduleName)
        except Exception:
            return None

    def locateModuleInMountFolder(self):
        mountModuleLocation = '/mnt/' + self.moduleName + '.py'
        if not os.path.isfile(mountModuleLocation):
            return None
        try:
            return imp.load_source(self.moduleName, mountModuleLocation)
        except Exception:
            return None

    def call(self, payload, context):
        return self.func(payload, context)


class UTCFormatter(logging.Formatter):
    converter = time.gmtime

    def __init__(self, fmt=None, datefmt=None):
        super(UTCFormatter, self).__init__(fmt, datefmt)

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
            s = "%s.%03dZ" % (t, record.msecs)
        return s


def stopWithError(msg):
    print ("ERROR:", msg, file=sys.stderr)
    raise SystemExit(1)


def getPAYLOAD_FILE():
    return os.environ.get('PAYLOAD_FILE')


def getTASK_TIMEOUT():
    return os.environ.get('TASK_TIMEOUT') or 3600


def getTASK_MAXMEM():
    maxmemFlag = os.environ.get('TASK_MAXMEM') or '300m'
    suffix = maxmemFlag[-1:]
    theNumber = int(maxmemFlag[:-1])
    factor = 1024
    valueInBytes = {
        'b': theNumber,
        'k': theNumber * factor,
        'm': theNumber * factor * factor,
        'g': theNumber * factor * factor * factor,
        }.get(suffix, theNumber)
    return valueInBytes


def getAWS_LAMBDA_FUNCTION_NAME():
    return os.environ.get('AWS_LAMBDA_FUNCTION_NAME')


def getAWS_LAMBDA_FUNCTION_VERSION():
    return os.environ.get('AWS_LAMBDA_FUNCTION_VERSION')


def getREQUEST_ID():
    return os.environ.get('TASK_ID') or uuid.uuid4()


def getHANDLER():
    # return os.environ.get('HANDLER')
    if len(sys.argv) > 1:
        return sys.argv[1]
    return None


def configLogging(context):
    class RequestIdFilter(logging.Filter):
        def filter(self, record):
            record.request_id = context.aws_request_id
            return True

    loggingConfig = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'standard': {
                '()': UTCFormatter,
                'format': '[%(levelname)s]\t%(asctime)s\t%(request_id)s\t%(message)s'
            },
        },
        'handlers': {
            'default': {
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
                'stream': 'ext://sys.stdout'
            },
        },
        'filters':{
            'request_id' :{
                '()' : RequestIdFilter
            }
        },
        'loggers': {
            '': {
                'handlers': ['default'],
                'filters': ['request_id'],
                'propagate': True
            },
        }
    }
    logging.config.dictConfig(loggingConfig)

plannedEnd = time.time() + getTASK_TIMEOUT()

debugging and print ('os.environ      = ', os.environ)
debugging and print ('/mnt content    = ', os.listdir("/mnt"))
debugging and print ('pwd dir content = ',
    os.listdir(os.path.dirname(os.path.realpath(__file__))))

context = Context()
debugging and print ('context created')

configLogging(context)
debugging and print ('config loaded')

payloadFileName = getPAYLOAD_FILE()
debugging and print ('PAYLOAD_FILE = ', payloadFileName)

handlerName = getHANDLER()
debugging and print ('HANDLER = ', handlerName)

if handlerName is None:
    stopWithError("HANDLER variable is not specified")
if payloadFileName is None:
    stopWithError("PAYLOAD_FILE variable is not specified")

if not os.path.isfile(payloadFileName):
    stopWithError("No payload present")

handlerParts = string.rsplit(handlerName, ".", 2)

if len(handlerParts) < 2:
    stopWithError("HANDLER variable should be specified " +
        "in format 'moduleName.functionName'")

moduleName = handlerParts[0]
funcName = handlerParts[1]

if moduleName is None:
    stopWithError("Module name is not defined")
if funcName is None:
    stopWithError("Function name is not defined")

try:
    with file(payloadFileName) as f:
        s = f.read()
except:
    stopWithError("Failed to read {payload}".format(payload=payloadFileName))

debugging and print ('payload loaded')

try:
    payload = Payload(s)
except:
    stopWithError('Payload is not JSON')

debugging and print ('payload parsed as JSON')

caller = DynaCaller(moduleName, funcName)

try:
    if not caller.locateFunc():
        stopWithError("Failed to locate {module}.{func}"
            .format(module=moduleName, func=funcName))
except Exception as e:
    print (e, file=sys.stderr)
    stopWithError("Failed to locate {module}.{func}"
        .format(module=moduleName, func=funcName))

debugging and print ('handler found')

try:
    result = caller.call(payload, context)
    #FIXME where to put result in async mode?
except Exception as e:
    stopWithError(e)

debugging and print ('done')

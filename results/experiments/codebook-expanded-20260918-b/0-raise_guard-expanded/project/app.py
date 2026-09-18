def connect(timeout):
    if timeout < 1:
        raise ValueError('too small')
    return timeout * 2
SOURCE_VERSION = 2

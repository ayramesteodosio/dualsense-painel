from .. import plataforma


def default_backend():
    if plataforma.LINUX:
        from .linux import LinuxBackend
        return LinuxBackend()
    from .hidapi_backend import HidapiBackend
    return HidapiBackend()

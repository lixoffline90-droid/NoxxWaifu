import logging
import sys
import time

StartTime = time.time()

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.FileHandler("log.txt"), logging.StreamHandler()],
    level=logging.INFO,
)

logging.getLogger("apscheduler").setLevel(logging.ERROR)
logging.getLogger("pyrate_limiter").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
LOGGER = logging.getLogger(__name__)

if sys.version_info[0] < 3 or sys.version_info[1] < 8:
    LOGGER.error("You MUST have a Python version of at least 3.8!")
    sys.exit(1)

LOAD = []
NO_LOAD = []


def __list_all_modules():
    import glob
    from os.path import basename, dirname, isfile

    mod_paths = glob.glob(dirname(__file__) + "/*.py")
    all_modules = [
        basename(f)[:-3]
        for f in mod_paths
        if isfile(f) and f.endswith(".py") and not f.endswith("__init__.py")
    ]

    if LOAD or NO_LOAD:
        to_load = LOAD
        if to_load:
            if not all(any(mod == m for m in all_modules) for mod in to_load):
                LOGGER.error("Invalid loadorder names, Quitting...")
                sys.exit(1)
            all_modules = sorted(set(all_modules) - set(to_load))
            to_load = list(all_modules) + to_load
        else:
            to_load = all_modules
        if NO_LOAD:
            LOGGER.info("Not loading: {}".format(NO_LOAD))
            return [item for item in to_load if item not in NO_LOAD]
        return to_load
    return all_modules


ALL_MODULES = __list_all_modules()
LOGGER.info("Modules to load: %s", str(ALL_MODULES))
__all__ = ALL_MODULES + ["ALL_MODULES"]

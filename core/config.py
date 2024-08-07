
import configparser


def get_key(name:str, section:str="Default", default:str=None):
    config = configparser.ConfigParser()
    try:
        config.read('setting.ini')
        return config.get(section, name, fallback=default)
    except:
        return default
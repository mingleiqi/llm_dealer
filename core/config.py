
import configparser


def get_key(name:string, section:string="Default", default:string=None):
    config = configparser.ConfigParser()
    try:
        config.read('setting.ini')
        return config.get('GitHub', 'token', fallback=default)
    except:
        return default
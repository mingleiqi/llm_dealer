
import configparser


def get_key(name:str, section:str="Default", default:str=None):
    config = configparser.ConfigParser()
    try:
        config.read('.\\setting.ini',encoding="utf8")
        if not config.has_section(section):
            config.add_section(section)
        return config[section].get(name,fallback=default)
    except Exception  as e:
        print(e)
        return default
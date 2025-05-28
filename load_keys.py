from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from bot import Base, VPNKey

def load_keys_from_file(filename='vpn_keys.txt'):
    """Загрузка ключей из файла в базу данных"""
    engine = create_engine('sqlite:///vpn_keys.db')
    Session = sessionmaker(bind=engine)
    session = Session()

    # Очистка существующих ключей
    session.query(VPNKey).delete()
    
    # Загрузка новых ключей
    with open(filename, 'r') as file:
        for line in file:
            key = line.strip()
            if key:  # Проверка на пустую строку
                identifier = key.split('#')[-1] if '#' in key else None
                if identifier and identifier.startswith('AmegaVPN-'):
                    identifier = identifier[len('AmegaVPN-'):]
                # Извлекаем xui_id (между '://' и '@')
                xui_id = None
                try:
                    xui_id = key.split('://')[1].split('@')[0]
                except Exception:
                    pass
                new_key = VPNKey(key=key, xui_email=identifier, xui_id=xui_id)
                session.add(new_key)

    session.commit()
    session.close()
    print("Ключи успешно загружены в базу данных")

if __name__ == '__main__':
    load_keys_from_file() 
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from bot import VPNKey, Base

DB_PATH = 'vpn_keys.db'

def add_column_if_not_exists():
    # Добавляем столбец xui_email, если его нет
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(vpn_keys)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'xui_email' not in columns:
        cursor.execute("ALTER TABLE vpn_keys ADD COLUMN xui_email TEXT")
        print('Столбец xui_email добавлен.')
    else:
        print('Столбец xui_email уже существует.')
    conn.commit()
    conn.close()

def fill_xui_email():
    engine = create_engine(f'sqlite:///{DB_PATH}')
    Session = sessionmaker(bind=engine)
    session = Session()
    keys = session.query(VPNKey).all()
    updated = 0
    for key_obj in keys:
        key = key_obj.key
        identifier = key.split('#')[-1] if '#' in key else None
        if identifier and identifier.startswith('AmegaVPN-'):
            identifier = identifier[len('AmegaVPN-'):]
        if identifier and key_obj.xui_email != identifier:
            key_obj.xui_email = identifier
            updated += 1
    session.commit()
    session.close()
    print(f'Обновлено {updated} ключей.')

if __name__ == '__main__':
    add_column_if_not_exists()
    fill_xui_email()
    print('Миграция завершена.') 
import sqlite3
conn = sqlite3.connect('vpn_keys.db')
conn.execute("ALTER TABLE vpn_keys ADD COLUMN xui_id TEXT;")
conn.commit()
conn.close()
print("Столбец xui_id добавлен.")
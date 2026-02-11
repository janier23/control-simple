import sqlite3

def conectar():
    return sqlite3.connect("database.db")

def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    # Negocios
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS negocios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL
    )
    """)

    # Productos
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        precio REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0
    )
    """)

    # Ventas
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER,
        cantidad INTEGER NOT NULL,
        total REAL NOT NULL,
        fecha TEXT NOT NULL,
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )
    """)

    conn.commit()
    conn.close()

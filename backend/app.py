from flask import Flask, render_template, request, redirect, session, send_file
import sqlite3
import os
from datetime import datetime, timedelta
from reports.pdf_report import generate_pdf
from reports.excel_report import generate_excel


# =========================
# CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

app = Flask(
    __name__,
    template_folder="../frontend/templates",
    static_folder="../frontend/static"
)
app.secret_key = "control_simple_secreto"

# =========================
# DATABASE
# =========================
def conectar():
    return sqlite3.connect(DB_PATH)

def buscar_historial(desde=None, hasta=None, producto=None, usuario=None):
    conn = conectar()
    cursor = conn.cursor()

    query = """
        SELECT v.fecha, p.nombre, v.cantidad, v.total, u.nombre
        FROM ventas v
        JOIN productos p ON p.id = v.producto_id
        JOIN usuarios u ON u.id = v.usuario_id
        WHERE 1=1
    """
    params = []

    if desde and hasta:
        query += " AND date(v.fecha) BETWEEN ? AND ?"
        params.extend([desde, hasta])

    if producto:
        query += " AND p.nombre LIKE ?"
        params.append(f"%{producto}%")

    if usuario:
        query += " AND u.nombre LIKE ?"
        params.append(f"%{usuario}%")

    query += " ORDER BY v.fecha DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "fecha": r[0],
            "producto": r[1],
            "cantidad": r[2],
            "total": r[3],
            "usuario": r[4]
        }
        for r in rows
    ]


def get_report_data(desde, hasta):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM ventas
        WHERE date(fecha) BETWEEN ? AND ?
    """, (desde, hasta))
    ventas_total = float(cursor.fetchone()[0])

    cursor.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE date(fecha) BETWEEN ? AND ?
    """, (desde, hasta))
    gastos_total = float(cursor.fetchone()[0])

    cursor.execute("""
        SELECT p.nombre, v.cantidad, v.total, v.fecha, u.nombre
        FROM ventas v
        JOIN productos p ON p.id = v.producto_id
        JOIN usuarios u ON u.id = v.usuario_id
        WHERE date(v.fecha) BETWEEN ? AND ?
        ORDER BY v.fecha DESC
    """, (desde, hasta))
    ventas_rows = cursor.fetchall()

    cursor.execute("""
        SELECT g.descripcion, g.monto, g.fecha, u.nombre
        FROM gastos g
        JOIN usuarios u ON u.id = g.usuario_id
        WHERE date(g.fecha) BETWEEN ? AND ?
        ORDER BY g.fecha DESC
    """, (desde, hasta))
    gastos_rows = cursor.fetchall()

    conn.close()

    return {
    "desde": desde,
    "hasta": hasta,
    "ventas": ventas_total,
    "gastos": gastos_total,
    "ganancia": ventas_total - gastos_total,
    "ventas_detalle": [
        {
            "producto": r[0],
            "cantidad": r[1],
            "total": r[2],
            "fecha": r[3],
            "usuario": r[4],
        }
        for r in ventas_rows
    ],
    "gastos_detalle": [
        {
            "descripcion": r[0],
            "monto": r[1],
            "fecha": r[2],
            "usuario": r[3],
        }
        for r in gastos_rows
    ]
}

def requiere_login():
    return "usuario_id" in session

def requiere_dueno():
    if session.get("rol") != "dueno":
        return False
    return True

from functools import wraps

def solo_dueno(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        if session.get("rol") != "dueno":
            return redirect("/")
        return f(*args, **kwargs)
    return decorador


def requiere_operadora():
    if session.get("rol") not in ("operadora", "dueno"):
        return False
    return True

def esta_en_semana_cerrada(fecha_str):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM cierres_semanales
        WHERE date(?) BETWEEN fecha_inicio AND fecha_fin
    """, (fecha_str,))

    cerrado = cursor.fetchone()[0] > 0
    conn.close()

    return cerrado


def crear_tablas():
    conn = conectar()
    cursor = conn.cursor()

    # PRODUCTOS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        precio REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0
    )
    """)

    # VENTAS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        producto_id INTEGER,
        cantidad INTEGER NOT NULL,
        total REAL NOT NULL,
        fecha TEXT NOT NULL,
        usuario_id INTEGER NOT NULL DEFAULT 1
    )
    """)

    # GASTOS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        descripcion TEXT NOT NULL,
        monto REAL NOT NULL,
        fecha TEXT NOT NULL,
        usuario_id INTEGER NOT NULL DEFAULT 1
    )
    """)

    # USUARIOS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        rol TEXT NOT NULL CHECK (rol IN ('dueno','operadora')),
        activo INTEGER NOT NULL DEFAULT 1
    )
    """)

    conn.commit()
    conn.close()


def crear_dueno_si_no_existe():
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total = cursor.fetchone()[0]

    if total == 0:
        cursor.execute(
            "INSERT INTO usuarios (nombre, rol) VALUES (?, ?)",
            ("Dueño", "dueno")
        )
        conn.commit()

    conn.close()

crear_tablas()
crear_dueno_si_no_existe()

# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = conectar()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, rol FROM usuarios WHERE nombre = ?",
            (request.form.get("usuario"),)
        )

        user = cursor.fetchone()
        conn.close()

        if user:
            session["usuario_id"] = user[0]
            session["rol"] = user[1]
            session["negocio"] = request.form.get("negocio", "Mi negocio")

            return redirect("/")

    return render_template("login.html")

# ======================
# LOGOUT  👈 AQUÍ VA
# ======================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# =========================
# HOME
# =========================
@app.route("/")
def home():
    if "negocio" not in session:
        return redirect("/login")

    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT IFNULL(SUM(total),0) FROM ventas")
    total_ventas = cursor.fetchone()[0]

    cursor.execute("SELECT IFNULL(SUM(monto),0) FROM gastos")
    total_gastos = cursor.fetchone()[0]

    # HOY
    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM ventas
        WHERE date(fecha) = date('now')
    """)
    ventas_hoy = cursor.fetchone()[0]

    cursor.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE date(fecha) = date('now')
    """)
    gastos_hoy = cursor.fetchone()[0]

    # SEMANA (últimos 7 días)
    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM ventas
        WHERE date(fecha) >= date('now', '-7 day')
    """)
    ventas_semana = cursor.fetchone()[0]

    cursor.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE date(fecha) >= date('now', '-7 day')
    """)
    gastos_semana = cursor.fetchone()[0]

    # MES (últimos 30 días)
    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM ventas
        WHERE date(fecha) >= date('now', '-30 day')
    """)
    ventas_mes = cursor.fetchone()[0]

    cursor.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE date(fecha) >= date('now', '-30 day')
    """)
    gastos_mes = cursor.fetchone()[0]

    conn.close()
    ganancia = total_ventas - total_gastos


    return render_template(
    "index.html",
    total_ventas=total_ventas,
    total_gastos=total_gastos,
    ganancia=ganancia,
    ventas_hoy=ventas_hoy,
    gastos_hoy=gastos_hoy,
    ventas_semana=ventas_semana,
    gastos_semana=gastos_semana,
    ventas_mes=ventas_mes,
    gastos_mes=gastos_mes
)

# =========================
# PRODUCTOS
# =========================
@app.route("/productos", methods=["GET", "POST"])
@solo_dueno
def productos():
    if request.method == "POST" and not requiere_operadora():
        return redirect("/login")
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute(
            "INSERT INTO productos (nombre, precio, stock) VALUES (?, ?, ?)",
            (
                request.form["nombre"],
                float(request.form["precio"]),
                int(request.form.get("stock", 0))
            )
        )
        conn.commit()

    cursor.execute("SELECT id, nombre, precio, stock FROM productos")
    productos = cursor.fetchall()
    conn.close()

    return render_template("productos.html", productos=productos)

@app.route("/productos/eliminar/<int:id>")
@solo_dueno
def eliminar_producto(id):
    if not requiere_dueno():
        return redirect("/")
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM productos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/productos")

@app.route("/productos/editar/<int:id>", methods=["GET", "POST"])
@solo_dueno
def editar_producto(id):
    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        cursor.execute("""
            UPDATE productos
            SET nombre = ?, precio = ?, stock = ?
            WHERE id = ?
        """, (
            request.form["nombre"],
            float(request.form["precio"]),
            int(request.form["stock"]),
            id
        ))
        conn.commit()
        conn.close()
        return redirect("/productos")

    cursor.execute("SELECT * FROM productos WHERE id = ?", (id,))
    producto = cursor.fetchone()
    conn.close()
    return render_template("editar_producto.html", producto=producto)

# =========================
# VENTAS
# =========================
from datetime import datetime

@app.route("/ventas/nueva", methods=["GET", "POST"])
def nueva_venta():
    if not requiere_operadora():
        return redirect("/login")


    conn = conectar()
    cursor = conn.cursor()

    if request.method == "POST":
        producto_id = int(request.form["producto_id"])
        cantidad = int(request.form["cantidad"])

        # Obtener precio del producto
        cursor.execute(
            "SELECT precio FROM productos WHERE id = ?",
            (producto_id,)
        )
        precio = cursor.fetchone()[0]

        total = precio * cantidad
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")

        cursor.execute(
            """
            INSERT INTO ventas (producto_id, cantidad, total, fecha, usuario_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                producto_id,
                cantidad,
                total,
                fecha,
                session.get("usuario_id")
            )
        )


        conn.commit()
        conn.close()

        return redirect("/ventas")

    # GET → mostrar formulario
    cursor.execute("SELECT id, nombre FROM productos")
    productos = cursor.fetchall()
    conn.close()

    return render_template("venta.html", productos=productos)


@app.route("/ventas")
def ventas():
    if not requiere_operadora():
        return redirect("/login")
    conn = conectar()
    cursor = conn.cursor()
    if session.get("rol") == "dueno":
        cursor.execute("""
            SELECT v.id, p.nombre, v.cantidad, v.total, v.fecha, u.nombre
            FROM ventas v
            JOIN productos p ON p.id = v.producto_id
            JOIN usuarios u ON u.id = v.usuario_id
            ORDER BY v.id DESC
        """)
    else:
        cursor.execute("""
            SELECT v.id, p.nombre, v.cantidad, v.total, v.fecha, u.nombre
            FROM ventas v
            JOIN productos p ON p.id = v.producto_id
            JOIN usuarios u ON u.id = v.usuario_id
            WHERE v.usuario_id = ?
            ORDER BY v.id DESC
        """, (session.get("usuario_id"),))

    ventas = cursor.fetchall()
    conn.close()

    return render_template("ventas.html", ventas=ventas)

# =========================
# GASTOS
# =========================
@app.route("/gastos/nuevo", methods=["GET", "POST"])
def nuevo_gasto():
    if not requiere_operadora():
        return redirect("/login")
    if request.method == "POST":
        conn = conectar()
        cursor = conn.cursor()
        descripcion = request.form.get("descripcion")
        monto = float(request.form.get("monto"))
        fecha = datetime.now().strftime("%Y-%m-%d")

        cursor.execute(
            """
            INSERT INTO gastos (descripcion, monto, fecha, usuario_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                descripcion,
                monto,
                fecha,
                session.get("usuario_id")
            )
        )

        conn.commit()
        conn.close()
        return redirect("/gastos")

    return render_template("gasto.html")

@app.route("/gastos")
def gastos():
    if not requiere_operadora():
        return redirect("/login")
    conn = conectar()
    cursor = conn.cursor()
    if session.get("rol") == "dueno":
        cursor.execute("""
            SELECT g.id, g.descripcion, g.monto, g.fecha, u.nombre
            FROM gastos g
            JOIN usuarios u ON u.id = g.usuario_id
            ORDER BY g.id DESC
        """)
    else:
        cursor.execute("""
            SELECT g.id, g.descripcion, g.monto, g.fecha, u.nombre
            FROM gastos g
            JOIN usuarios u ON u.id = g.usuario_id
            WHERE g.usuario_id = ?
            ORDER BY g.id DESC
        """, (session.get("usuario_id"),))

    gastos = cursor.fetchall()
    conn.close()

    return render_template("gastos.html", gastos=gastos)

# =========================
# ELIMINAR VENTA (SOLO DUEÑO)
# =========================
@app.route("/ventas/eliminar/<int:id>")
@solo_dueno
def eliminar_venta(id):
    conn = conectar()
    cursor = conn.cursor()

    # obtener fecha de la venta
    cursor.execute("SELECT fecha FROM ventas WHERE id = ?", (id,))
    venta = cursor.fetchone()

    if not venta:
        conn.close()
        return redirect("/ventas")

    fecha_venta = venta[0]  # YYYY-MM-DD HH:MM

    # obtener último cierre semanal
    cursor.execute("""
        SELECT fecha_cierre
        FROM cierres_semanales
        ORDER BY fecha_cierre DESC
        LIMIT 1
    """)
    ultimo_cierre = cursor.fetchone()

    # 🔒 si existe un cierre y la venta es anterior o igual → NO borrar
    if ultimo_cierre:
        fecha_ultimo_cierre = ultimo_cierre[0]
        if fecha_venta <= fecha_ultimo_cierre:
            conn.close()
            return redirect("/ventas")

    # 🧹 borrar venta
    cursor.execute("DELETE FROM ventas WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    return redirect("/ventas")

# =========================
# ELIMINAR GASTO (SOLO DUEÑO)
# =========================
@app.route("/gastos/eliminar/<int:id>")
@solo_dueno
def eliminar_gasto(id):
    conn = conectar()
    cursor = conn.cursor()

    cursor.execute("SELECT fecha FROM gastos WHERE id = ?", (id,))
    fila = cursor.fetchone()

    if fila and esta_en_semana_cerrada(fila[0]):
        conn.close()
        return redirect("/gastos")

    cursor.execute("DELETE FROM gastos WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect("/gastos")

# =========================
# CIERRE SEMANAL (SOLO DUEÑO)
# =========================
@app.route("/cierres/semana", methods=["POST"])
@solo_dueno
def cerrar_semana():
    hoy = datetime.now()

    # lunes de la semana actual
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    fin_semana = inicio_semana + timedelta(days=6)

    inicio = inicio_semana.strftime("%Y-%m-%d")
    fin = fin_semana.strftime("%Y-%m-%d")

    conn = conectar()
    cursor = conn.cursor()

    # total ventas de la semana
    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM ventas
        WHERE date(fecha) BETWEEN ? AND ?
    """, (inicio, fin))
    total_ventas = cursor.fetchone()[0]

    # total gastos de la semana
    cursor.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE date(fecha) BETWEEN ? AND ?
    """, (inicio, fin))
    total_gastos = cursor.fetchone()[0]

    ganancia = total_ventas - total_gastos

    cursor.execute("""
        INSERT INTO cierres_semanales
        (fecha_inicio, fecha_fin, total_ventas, total_gastos, ganancia, cerrado_por, fecha_cierre)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        inicio,
        fin,
        total_ventas,
        total_gastos,
        ganancia,
        session.get("usuario_id"),
        datetime.now().strftime("%Y-%m-%d %H:%M")
    ))

    conn.commit()
    conn.close()

    return redirect("/")

# =========================
# REPORTES (SOLO DUEÑO)
# =========================
from datetime import date, timedelta
from flask import request

@app.route("/reportes", methods=["GET", "POST"])
@solo_dueno
def reportes():
    conn = conectar()
    cursor = conn.cursor()
    # 🔑 valores por defecto (SIEMPRE definidos)
    from datetime import date
    hoy = date.today().strftime("%Y-%m-%d")

    desde = hoy
    hasta = hoy


    hoy = date.today()
    accion = request.form.get("accion")

    # 🔑 soportar GET (historial)
    if request.method == "GET":
        desde = request.args.get("desde", desde)
        hasta = request.args.get("hasta", hasta)


    # 1️⃣ Determinar fechas
    if accion == "hoy":
        desde = hasta = hoy

    elif accion == "semana":
        desde = hoy - timedelta(days=hoy.weekday())
        hasta = hoy

    elif accion == "mes":
        desde = hoy.replace(day=1)
        hasta = hoy

    else:
        # filtro manual
        desde = request.form.get("desde")
        hasta = request.form.get("hasta")

        if not desde or not hasta:
            desde = hasta = hoy

    # 2️⃣ Convertir SIEMPRE a string YYYY-MM-DD
    if isinstance(desde, date):
        desde = desde.strftime("%Y-%m-%d")
    if isinstance(hasta, date):
        hasta = hasta.strftime("%Y-%m-%d")

    # 3️⃣ Totales de ventas
    cursor.execute("""
        SELECT IFNULL(SUM(total), 0)
        FROM ventas
        WHERE date(fecha) BETWEEN ? AND ?
    """, (desde, hasta))
    ventas_total = float(cursor.fetchone()[0])

    # 4️⃣ Totales de gastos
    cursor.execute("""
        SELECT IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE date(fecha) BETWEEN ? AND ?
    """, (desde, hasta))
    gastos_total = float(cursor.fetchone()[0])

    ganancia = ventas_total - gastos_total

    cursor.execute("""
        SELECT p.nombre, v.cantidad, v.total, v.fecha, u.nombre
        FROM ventas v
        JOIN productos p ON p.id = v.producto_id
        JOIN usuarios u ON u.id = v.usuario_id
        WHERE date(v.fecha) BETWEEN ? AND ?
        ORDER BY v.fecha DESC
    """, (desde, hasta))

    ventas = cursor.fetchall()

    ventas = [
        {
            "producto": r[0],
            "cantidad": r[1],
            "total": r[2],
            "fecha": r[3],
            "usuario": r[4]
        }
        for r in cursor.fetchall()
    ]

    cursor.execute("""
        SELECT g.descripcion, g.monto, g.fecha, u.nombre
        FROM gastos g
        JOIN usuarios u ON u.id = g.usuario_id
        WHERE date(g.fecha) BETWEEN ? AND ?
        ORDER BY g.fecha DESC
    """, (desde, hasta))

    gastos = cursor.fetchall()


    gastos = [
        {
            "descripcion": r[0],
            "monto": r[1],
            "fecha": r[2],
            "usuario": r[3]
        }
        for r in cursor.fetchall()
    ]

    producto = request.args.get("producto")
    usuario = request.args.get("usuario")

    historial = None
    if request.method == "GET":
        historial = buscar_historial(
            desde=desde,
            hasta=hasta,
            producto=producto,
            usuario=usuario
        )


    conn.close()

    return render_template(
    "reportes.html",
    total_ventas=ventas_total,
    total_gastos=gastos_total,
    ganancia=ventas_total - gastos_total,
    ventas=ventas,
    gastos=gastos,
    desde=desde,
    hasta=hasta,
    historial=historial
)

@app.route("/export/pdf")
@solo_dueno
def export_pdf():
    desde = request.args.get("from")
    hasta = request.args.get("to")

    if not desde or not hasta:
        return redirect("/reportes")

    data = get_report_data(desde, hasta)
    file_path = generate_pdf(data)

    return send_file(file_path, as_attachment=True)



@app.route("/export/excel")
def export_excel():
    desde = request.args.get("from")
    hasta = request.args.get("to")

    if not desde or not hasta:
        return redirect("/reportes")

    data = get_report_data(desde, hasta)
    file_path = generate_excel(data)

    return send_file(file_path, as_attachment=True)

@app.route("/calendar/data")
@solo_dueno
def calendar_data():
    month = request.args.get("month")  # YYYY-MM
    if not month:
        return {}

    conn = conectar()
    cursor = conn.cursor()

    # Ventas por día
    cursor.execute("""
        SELECT date(fecha) as dia, IFNULL(SUM(total), 0)
        FROM ventas
        WHERE strftime('%Y-%m', fecha) = ?
        GROUP BY dia
    """, (month,))
    ventas = dict(cursor.fetchall())

    # Gastos por día
    cursor.execute("""
        SELECT date(fecha) as dia, IFNULL(SUM(monto), 0)
        FROM gastos
        WHERE strftime('%Y-%m', fecha) = ?
        GROUP BY dia
    """, (month,))
    gastos = dict(cursor.fetchall())

    conn.close()

    # Unificar
    data = {}
    for dia in set(ventas) | set(gastos):
        data[dia] = {
            "ventas": ventas.get(dia, 0),
            "gastos": gastos.get(dia, 0)
        }

    return data




# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import os
from datetime import datetime
from flask import send_file
import io

def generate_pdf(data):
    buffer = io.BytesIO()
    buffer.write(b"Reporte PDF")  # ejemplo
    buffer.seek(0)
    os.makedirs("tmp", exist_ok=True)
    filename = f"reporte_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = os.path.join("tmp", filename)

    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    y = height - 2 * cm

    # TÍTULO
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, "Reporte de Negocio")
    y -= 1 * cm

    # PERÍODO
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Período: {data['desde']} a {data['hasta']}")
    y -= 1 * cm

    # RESUMEN
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Resumen")
    y -= 0.6 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Ventas:   ${data['ventas']}")
    y -= 0.4 * cm
    c.drawString(2 * cm, y, f"Gastos:   ${data['gastos']}")
    y -= 0.4 * cm
    c.drawString(2 * cm, y, f"Ganancia: ${data['ganancia']}")
    y -= 1 * cm

    # VENTAS
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Detalle de Ventas")
    y -= 0.6 * cm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(2 * cm, y, "Fecha")
    c.drawString(6 * cm, y, "Producto")
    c.drawString(11 * cm, y, "Cant.")
    c.drawString(13 * cm, y, "Total")
    y -= 0.4 * cm

    c.setFont("Helvetica", 9)
    for v in data["ventas_detalle"]:
        c.drawString(2 * cm, y, v["fecha"])
        c.drawString(6 * cm, y, v["producto"])
        c.drawRightString(12.5 * cm, y, str(v["cantidad"]))
        c.drawRightString(17 * cm, y, f"${v['total']}")
        y -= 0.35 * cm

        if y < 2 * cm:
            c.showPage()
            y = height - 2 * cm

    c.showPage()
    c.save()
    return path

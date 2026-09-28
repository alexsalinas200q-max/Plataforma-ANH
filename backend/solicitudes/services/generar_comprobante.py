# apps/solicitudes/services/generar_comprobante.py

import io
from django.utils import timezone

from core.fechas import ahora_local, formatear_fecha_hora


def generar_comprobante(solicitud) -> bytes:
    """
    Genera un PDF comprobante de solicitud APROBADA.
    El consumidor lo descarga y presenta en la estación.

    Incluye:
    - Datos del consumidor
    - Datos de la solicitud aprobada
    - Estación asignada con dirección
    - Fecha límite de retiro
    - Código QR con el id_publico para verificación
    - Instrucciones para el consumidor
    """
    from reportlab.lib.pagesizes import A5
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        rightMargin=1.5*cm,
        leftMargin=1.5*cm,
        topMargin=1.2*cm,
        bottomMargin=1.5*cm,
    )

    # ------------------------------------------------
    # COLORES Y ESTILOS
    # ------------------------------------------------

    azul       = colors.HexColor("#1a3a5c")
    azul_claro = colors.HexColor("#2d6a9f")
    verde      = colors.HexColor("#27ae60")
    gris       = colors.HexColor("#f5f5f5")
    blanco     = colors.white
    naranja    = colors.HexColor("#e67e22")

    titulo_style = ParagraphStyle(
        "titulo", fontSize=11, textColor=blanco,
        fontName="Helvetica-Bold", alignment=TA_CENTER, leading=16
    )
    subtitulo_style = ParagraphStyle(
        "subtitulo", fontSize=9, textColor=azul,
        fontName="Helvetica-Bold", alignment=TA_CENTER,
        spaceBefore=6, spaceAfter=4
    )
    label_style = ParagraphStyle(
        "label", fontSize=8, textColor=azul_claro,
        fontName="Helvetica-Bold"
    )
    valor_style = ParagraphStyle(
        "valor", fontSize=8, textColor=colors.black,
        fontName="Helvetica"
    )
    normal_style = ParagraphStyle(
        "normal", fontSize=7.5, fontName="Helvetica",
        textColor=colors.black, alignment=TA_CENTER
    )
    alerta_style = ParagraphStyle(
        "alerta", fontSize=8, fontName="Helvetica-Bold",
        textColor=naranja, alignment=TA_CENTER
    )

    consumidor = solicitud.consumidor
    user       = consumidor.user
    doc_id     = consumidor.documentos.first()
    elementos  = []

    # ------------------------------------------------
    # ENCABEZADO
    # ------------------------------------------------

    encabezado = Table(
        [[Paragraph(
            "AGENCIA NACIONAL DE HIDROCARBUROS<br/>"
            "<font size='9'>COMPROBANTE DE SOLICITUD APROBADA</font>",
            titulo_style
        )]],
        colWidths=["100%"]
    )
    encabezado.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), azul),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    elementos.append(encabezado)
    elementos.append(Spacer(1, 0.3*cm))

    # ------------------------------------------------
    # NÚMERO DE SOLICITUD DESTACADO
    # ------------------------------------------------

    num_solicitud = Table(
        [[Paragraph(
            f"N° {str(solicitud.id_publico)[:8].upper()}",
            ParagraphStyle("num", fontSize=16, fontName="Helvetica-Bold",
                          textColor=azul, alignment=TA_CENTER)
        )]],
        colWidths=["100%"]
    )
    num_solicitud.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), gris),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 1.5, azul_claro),
    ]))
    elementos.append(num_solicitud)
    elementos.append(Spacer(1, 0.3*cm))

    # ------------------------------------------------
    # HELPER FILA
    # ------------------------------------------------

    def fila(label, valor):
        return [
            Paragraph(label, label_style),
            Paragraph(str(valor) if valor else "—", valor_style)
        ]

    def tabla_seccion(titulo, filas_datos):
        elementos.append(Paragraph(titulo, subtitulo_style))
        t = Table(filas_datos, colWidths=["38%", "62%"])
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), gris),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#dddddd")),
            ("BOX",           (0, 0), (-1, -1), 0.8, azul_claro),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(t)
        elementos.append(Spacer(1, 0.25*cm))

    # ------------------------------------------------
    # DATOS DEL SOLICITANTE
    # ------------------------------------------------

    tabla_seccion("DATOS DEL SOLICITANTE", [
        fila("Nombre",     user.nombre_completo()),
        fila("Documento",  f"{doc_id.get_tipo_documento_display()}: {doc_id.numero_documento}" if doc_id else "—"),
        fila("Municipio",  consumidor.municipio.nombre if consumidor.municipio else "—"),
    ])

    # ------------------------------------------------
    # COMBUSTIBLE APROBADO
    # ------------------------------------------------

    tabla_seccion("COMBUSTIBLE APROBADO", [
        fila("Tipo",    solicitud.get_tipo_combustible_aprobado_display()),
        fila("Litros",  f"{solicitud.litros_aprobados} L"),
        fila("Uso",     solicitud.uso_combustible or "—"),
    ])

    # ------------------------------------------------
    # ESTACIÓN ASIGNADA
    # ------------------------------------------------

    if solicitud.estacion_servicio:
        tabla_seccion("ESTACIÓN DE RETIRO", [
            fila("Estación",   solicitud.estacion_servicio.nombre),
            fila("Dirección",  solicitud.estacion_servicio.direccion),
            fila("Municipio",  solicitud.estacion_servicio.municipio),
        ])

    # ------------------------------------------------
    # FECHA LÍMITE — DESTACADA
    # ------------------------------------------------

    if solicitud.fecha_expiracion:
        fecha_limite = formatear_fecha_hora(solicitud.fecha_expiracion)
        dias_restantes = (solicitud.fecha_expiracion - timezone.now()).days

        fecha_tabla = Table(
            [[
                Paragraph("⏰ VÁLIDO HASTA:", label_style),
                Paragraph(
                    f"<b>{fecha_limite}</b>",
                    ParagraphStyle("fecha", fontSize=9, fontName="Helvetica-Bold",
                                  textColor=verde if dias_restantes > 1 else naranja)
                )
            ]],
            colWidths=["40%", "60%"]
        )
        fecha_tabla.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#eafaf1") if dias_restantes > 1 else colors.HexColor("#fef9e7")),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("BOX",           (0, 0), (-1, -1), 1.5, verde if dias_restantes > 1 else naranja),
        ]))
        elementos.append(fecha_tabla)
        elementos.append(Spacer(1, 0.3*cm))

    # ------------------------------------------------
    # INSTRUCCIONES
    # ------------------------------------------------

    elementos.append(HRFlowable(width="100%", thickness=0.5, color=azul_claro))
    elementos.append(Spacer(1, 0.2*cm))
    elementos.append(Paragraph(
        "INSTRUCCIONES PARA EL RETIRO", subtitulo_style
    ))
    elementos.append(Paragraph(
        "1. Presentar este comprobante en la estación asignada.<br/>"
        "2. Portar documento de identidad original.<br/>"
        "3. El bidón/envase debe estar limpio y ser apto para combustible.<br/>"
        "4. Retirar antes de la fecha límite indicada.<br/>"
        "5. Solo el titular puede retirar el combustible.",
        ParagraphStyle("inst", fontSize=7.5, fontName="Helvetica",
                      textColor=colors.black, leading=12)
    ))
    elementos.append(Spacer(1, 0.3*cm))

    # ------------------------------------------------
    # PIE DE PÁGINA
    # ------------------------------------------------

    pie = Table(
        [[Paragraph(
            f"Generado: {formatear_fecha_hora(ahora_local())} | "
            f"Sistema ANH Bolivia | ID: {str(solicitud.id_publico)[:8].upper()}",
            ParagraphStyle("pie", fontSize=6.5, textColor=colors.grey,
                          alignment=TA_CENTER, fontName="Helvetica")
        )]],
        colWidths=["100%"]
    )
    pie.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("LINEABOVE",     (0, 0), (-1, 0),  0.5, colors.grey),
    ]))
    elementos.append(pie)

    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()
# apps/solicitudes/services/generar_declaracion_jurada.py

import io

from core.fechas import (
    ahora_local, formatear_fecha, formatear_fecha_hora, formatear_fecha_larga,
)


def generar_declaracion_jurada(solicitud) -> bytes:
    """
    Genera un PDF de declaración jurada con los datos
    de la solicitud y del perfil del consumidor.

    El documento incluye:
    - Encabezado institucional ANH
    - Datos personales del solicitante
    - Datos de ubicación
    - Datos del producto solicitado
    - Actividad económica y uso del combustible
    - Texto legal de declaración jurada
    - Espacio para firma y huella digital
    - Fecha y lugar
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle,
        Paragraph, Spacer, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=1.5*cm,
        bottomMargin=2*cm,
    )

    # ------------------------------------------------
    # COLORES Y ESTILOS
    # ------------------------------------------------

    azul       = colors.HexColor("#1a3a5c")
    azul_claro = colors.HexColor("#2d6a9f")
    gris       = colors.HexColor("#f5f5f5")
    blanco     = colors.white

    titulo_style = ParagraphStyle(
        "titulo", fontSize=13, textColor=blanco,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
        leading=18
    )
    subtitulo_style = ParagraphStyle(
        "subtitulo", fontSize=11, textColor=azul,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
        spaceAfter=8, spaceBefore=8
    )
    label_style = ParagraphStyle(
        "label", fontSize=9, textColor=azul_claro,
        fontName="Helvetica-Bold"
    )
    valor_style = ParagraphStyle(
        "valor", fontSize=9, textColor=colors.black,
        fontName="Helvetica"
    )
    legal_style = ParagraphStyle(
        "legal", fontSize=8.5, textColor=colors.black,
        fontName="Helvetica", alignment=TA_JUSTIFY,
        leading=13, spaceBefore=6, spaceAfter=6
    )
    normal_style = ParagraphStyle(
        "normal", fontSize=9, fontName="Helvetica",
        textColor=colors.black
    )

    consumidor = solicitud.consumidor
    user       = consumidor.user
    doc_id     = consumidor.documentos.first()
    elementos  = []

    # ------------------------------------------------
    # ENCABEZADO INSTITUCIONAL
    # ------------------------------------------------

    encabezado = Table(
        [[Paragraph(
            "AGENCIA NACIONAL DE HIDROCARBUROS — BOLIVIA<br/>"
            "<font size='11'>DECLARACIÓN JURADA DE SOLICITUD DE COMBUSTIBLE</font><br/>"
            f"<font size='9'>N° {str(solicitud.id_publico)[:8].upper()} | "
            f"Fecha: {formatear_fecha(ahora_local())}</font>",
            titulo_style
        )]],
        colWidths=["100%"]
    )
    encabezado.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), azul),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
    ]))
    elementos.append(encabezado)
    elementos.append(Spacer(1, 0.5*cm))

    # ------------------------------------------------
    # HELPER PARA FILAS DE DATOS
    # ------------------------------------------------

    def fila(label, valor):
        return [
            Paragraph(label, label_style),
            Paragraph(str(valor) if valor else "—", valor_style)
        ]

    def seccion(titulo, filas_datos):
        """Genera una tabla de sección con título y filas de datos."""
        elementos.append(Paragraph(titulo, subtitulo_style))

        tabla = Table(
            filas_datos,
            colWidths=["35%", "65%"]
        )
        tabla.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), gris),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("BOX",           (0, 0), (-1, -1), 1,   azul_claro),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 0.3*cm))

    # ------------------------------------------------
    # SECCIÓN 1 — DATOS PERSONALES
    # ------------------------------------------------

    seccion("I. DATOS PERSONALES DEL SOLICITANTE", [
        fila("Nombres",           user.nombres),
        fila("Primer apellido",   user.apellido_paterno),
        fila("Segundo apellido",  user.apellido_materno or "—"),
        fila("Tipo de documento", doc_id.get_tipo_documento_display() if doc_id else "—"),
        fila("N° de documento",   f"{doc_id.numero_documento} {doc_id.complemento_documento}".strip() if doc_id else "—"),
        fila("Fecha de nacimiento", formatear_fecha(consumidor.fecha_nacimiento)),
    ])

    # ------------------------------------------------
    # SECCIÓN 2 — DATOS GENERALES
    # ------------------------------------------------

    seccion("II. DATOS GENERALES", [
        fila("Correo electrónico", user.email),
        fila("Celular",            consumidor.celular or "—"),
        fila("Departamento",       consumidor.departamento.nombre if consumidor.departamento else "—"),
        fila("Provincia",          consumidor.provincia.nombre    if consumidor.provincia    else "—"),
        fila("Municipio",          consumidor.municipio.nombre    if consumidor.municipio    else "—"),
        fila("Dirección",          consumidor.direccion or "—"),
        fila("Actividad económica", consumidor.get_actividad_display() if consumidor.actividad else "—"),
    ])

    # ------------------------------------------------
    # SECCIÓN 3 — DATOS DEL PRODUCTO
    # ------------------------------------------------

    seccion("III. DATOS DEL PRODUCTO SOLICITADO", [
        fila("Tipo de combustible", solicitud.get_tipo_combustible_display()),
        fila("Volumen solicitado",  f"{solicitud.litros_solicitados} litros"),
        fila("Uso / destino",       solicitud.uso_combustible or "—"),
    ])

    # ------------------------------------------------
    # TEXTO DE DECLARACIÓN JURADA
    # ------------------------------------------------

    elementos.append(HRFlowable(
        width="100%", thickness=1.5, color=azul
    ))
    elementos.append(Spacer(1, 0.3*cm))
    elementos.append(Paragraph(
        "IV. DECLARACIÓN JURADA", subtitulo_style
    ))

    texto_legal = (
        f"Yo, <b>{user.nombre_completo()}</b>, con "
        f"{doc_id.get_tipo_documento_display() if doc_id else 'documento'} "
        f"N° <b>{doc_id.numero_documento if doc_id else '—'}</b>, "
        f"domiciliado en <b>{consumidor.municipio.nombre if consumidor.municipio else '—'}</b>, "
        f"Departamento de <b>{consumidor.departamento.nombre if consumidor.departamento else '—'}</b>, "
        f"Bolivia; DECLARO BAJO JURAMENTO que:<br/><br/>"
        f"1. Los datos consignados en el presente formulario son verídicos y exactos, "
        f"haciéndome responsable de cualquier falsedad en los mismos.<br/><br/>"
        f"2. El combustible solicitado (<b>{solicitud.litros_solicitados} litros de "
        f"{solicitud.get_tipo_combustible_display()}</b>) será utilizado exclusivamente "
        f"para el siguiente destino: <b>{solicitud.uso_combustible or 'no especificado'}</b>, "
        f"en el marco de la actividad económica declarada.<br/><br/>"
        f"3. No estoy incurso en ninguna causal de inhabilitación establecida por la "
        f"Agencia Nacional de Hidrocarburos (ANH).<br/><br/>"
        f"4. Reconozco que la falsedad de los datos declarados o el uso indebido del "
        f"combustible otorgado constituye infracción sujeta a las sanciones previstas "
        f"en la normativa vigente de hidrocarburos en el Estado Plurinacional de Bolivia.<br/><br/>"
        f"5. Autorizo a la ANH a verificar la información proporcionada con las "
        f"instituciones correspondientes."
    )

    elementos.append(Paragraph(texto_legal, legal_style))
    elementos.append(Spacer(1, 0.5*cm))

    # ------------------------------------------------
    # FIRMA Y DATOS FINALES
    # ------------------------------------------------

    lugar_fecha = (
        f"{consumidor.municipio.nombre if consumidor.municipio else '___________'}, "
        f"{formatear_fecha_larga(ahora_local())}"
    )

    elementos.append(Paragraph(
        f"Lugar y fecha: {lugar_fecha}", normal_style
    ))
    elementos.append(Spacer(1, 1.5*cm))

    firma_tabla = Table(
        [[
            Paragraph("_____________________________", normal_style),
            Paragraph("", normal_style),
            Paragraph("_____________________________", normal_style),
        ],[
            Paragraph(f"<b>Firma del solicitante</b><br/>{user.nombre_completo()}<br/>{doc_id.numero_documento if doc_id else ''}", label_style),
            Paragraph("", normal_style),
            Paragraph("<b>Huella digital</b>", label_style),
        ]],
        colWidths=["45%", "10%", "45%"]
    )
    firma_tabla.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(firma_tabla)
    elementos.append(Spacer(1, 0.5*cm))

    # ------------------------------------------------
    # PIE DE PÁGINA
    # ------------------------------------------------

    pie = Table(
        [[Paragraph(
            "Documento generado por el Sistema de Gestión de Solicitudes de Combustible — ANH Bolivia | "
            f"ID: {str(solicitud.id_publico)[:8].upper()} | {formatear_fecha_hora(ahora_local())}",
            ParagraphStyle("pie", fontSize=7, textColor=colors.grey,
                           alignment=TA_CENTER, fontName="Helvetica")
        )]],
        colWidths=["100%"]
    )
    pie.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEABOVE",     (0, 0), (-1, -1), 0.5, colors.grey),
    ]))
    elementos.append(pie)

    doc.build(elementos)
    buffer.seek(0)
    return buffer.getvalue()
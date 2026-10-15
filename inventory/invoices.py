import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT

COMPANY_NAME = "Your Business Name"
COMPANY_ADDRESS = "Benin City, Nigeria"


def generate_invoice_pdf(sale) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm, leftMargin=20 * mm, rightMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=styles["Heading1"], fontSize=22, spaceAfter=2)
    small_muted = ParagraphStyle("muted", parent=styles["Normal"], textColor=colors.grey, fontSize=9)

    elements = []
    elements.append(Paragraph("INVOICE", title_style))
    elements.append(Paragraph(COMPANY_NAME, styles["Normal"]))
    elements.append(Paragraph(COMPANY_ADDRESS, small_muted))
    elements.append(Spacer(1, 10 * mm))

    meta_table = Table([
        ["Invoice #:", f"S-{sale.id:04d}", "Date:", sale.sale_date.strftime("%d %b %Y")],
        ["Bill to:", sale.customer.name, "Due date:", sale.due_date.strftime("%d %b %Y") if sale.due_date else "On receipt"],
        ["", sale.customer.address or "", "Status:", sale.get_status_display()],
    ], colWidths=[22 * mm, 68 * mm, 22 * mm, 58 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.grey),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 10 * mm))

    data = [["Product", "Qty", "Unit Price", "Total"]]
    for item in sale.items.select_related("product"):
        data.append([
            item.product.name, str(item.quantity),
            f"NGN {item.unit_price:,.2f}", f"NGN {item.total_price:,.2f}",
        ])
    items_table = Table(data, colWidths=[80 * mm, 20 * mm, 35 * mm, 35 * mm])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b2b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 6 * mm))

    totals_data = [
        ["", "Subtotal:", f"NGN {sale.total_amount:,.2f}"],
        ["", "Amount Paid:", f"NGN {sale.amount_paid:,.2f}"],
        ["", "Balance Due:", f"NGN {sale.balance_due:,.2f}"],
    ]
    totals_table = Table(totals_data, colWidths=[100 * mm, 35 * mm, 35 * mm])
    totals_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("RIGHTPADDING", (1, 0), (1, -1), 10),
        ("FONTNAME", (1, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (1, 2), (-1, 2), 12),
        ("LINEABOVE", (1, 2), (-1, 2), 1, colors.black),
        ("TOPPADDING", (1, 2), (-1, 2), 6),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 15 * mm))

    if sale.notes:
        elements.append(Paragraph(f"Notes: {sale.notes}", small_muted))
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph("Thank you for your business.", small_muted))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

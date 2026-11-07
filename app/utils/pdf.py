"""Professional PDF documents built with ReportLab.

ReportLab is used instead of an HTML-to-PDF engine because it has no system
dependencies (WeasyPrint needs GTK on Windows) and produces deterministic
layouts for report cards and receipts.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .money import format_money

INK = colors.HexColor("#0B1B2B")
MUTED = colors.HexColor("#4A5F73")
LINE = colors.HexColor("#D9E0E7")
SOFT = colors.HexColor("#F4F6F8")


def _tmp_path(name: str) -> Path:
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4().hex}-{name}"


def _styles(accent_hex: str):
    base = getSampleStyleSheet()
    accent = colors.HexColor(accent_hex)
    return {
        "school": ParagraphStyle(
            "school", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=19, leading=22, textColor=INK, spaceAfter=2, alignment=TA_LEFT,
        ),
        "address": ParagraphStyle(
            "address", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.5, leading=11, textColor=MUTED,
        ),
        "doctitle": ParagraphStyle(
            "doctitle", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=accent, alignment=TA_CENTER,
            spaceBefore=6, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=12, textColor=MUTED, alignment=TA_CENTER,
        ),
        "label": ParagraphStyle(
            "label", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=10, textColor=MUTED,
        ),
        "value": ParagraphStyle(
            "value", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=INK,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=11,
        ),
        "cellbold": ParagraphStyle(
            "cellbold", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=9,
            leading=11,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10,
            textColor=MUTED,
        ),
        "remark": ParagraphStyle(
            "remark", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5, leading=11,
        ),
        "accent": accent,
    }


def _header(story, school: dict, styles, logo_path: str | None = None):
    if logo_path and Path(logo_path).exists():
        try:
            logo = Image(logo_path, width=18 * mm, height=18 * mm, kind="proportional")
            logo.hAlign = "LEFT"
            text = [
                Paragraph(escape(school.get("name") or "School"), styles["school"]),
                Paragraph(escape(school.get("address") or ""), styles["address"]),
                Paragraph(
                    escape(" · ".join(filter(None, [school.get("phone"), school.get("email")]))),
                    styles["address"],
                ),
            ]
            table = Table([[logo, text]], colWidths=[22 * mm, 150 * mm])
            table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(table)
        except Exception:
            story.append(Paragraph(escape(school.get("name") or "School"), styles["school"]))
    else:
        story.append(Paragraph(escape(school.get("name") or "School"), styles["school"]))
        story.append(Paragraph(escape(school.get("address") or ""), styles["address"]))
        story.append(
            Paragraph(
                escape(" · ".join(filter(None, [school.get("phone"), school.get("email")]))),
                styles["address"],
            )
        )
    story.append(Spacer(1, 4))
    rule = Table([[""]], colWidths=[172 * mm], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), styles["accent"])]))
    story.append(rule)


def build_report_card_pdf(snapshot: dict, filename: str) -> str:
    school = snapshot["school"]
    styles = _styles(school.get("accent") or "#B7791F")
    path = _tmp_path(filename)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Report Card — {snapshot['student']['name']}",
        author=school.get("name") or "School OS",
    )
    story = []

    logo_path = None
    try:
        from .settings import get_school

        current = get_school()
        if current and current.logo_file_id:
            from ..extensions import db
            from ..models import StoredFile

            record = db.session.get(StoredFile, current.logo_file_id)
            if record:
                logo_path = record.stored_path
    except Exception:
        logo_path = None

    _header(story, school, styles, logo_path)
    story.append(Paragraph("REPORT CARD", styles["doctitle"]))
    story.append(
        Paragraph(
            escape(
                f"{snapshot['exam']['type']} · {snapshot['exam']['name']} · "
                f"Academic Year {snapshot['exam']['session']}"
            ),
            styles["subtitle"],
        )
    )
    story.append(Spacer(1, 8))

    student = snapshot["student"]
    info_rows = [
        [
            Paragraph("STUDENT", styles["label"]),
            Paragraph(escape(student["name"]), styles["value"]),
            Paragraph("ADMISSION NO.", styles["label"]),
            Paragraph(escape(student["admission_no"]), styles["value"]),
        ],
        [
            Paragraph("CLASS & SECTION", styles["label"]),
            Paragraph(escape(student["class_section"]), styles["value"]),
            Paragraph("ROLL NO.", styles["label"]),
            Paragraph(str(student["roll_no"] or "—"), styles["value"]),
        ],
    ]
    info = Table(info_rows, colWidths=[32 * mm, 54 * mm, 30 * mm, 46 * mm])
    info.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(info)
    story.append(Spacer(1, 12))

    table_data = [
        [
            Paragraph("Subject", styles["cellbold"]),
            Paragraph("Max", styles["cellbold"]),
            Paragraph("Pass", styles["cellbold"]),
            Paragraph("Obtained", styles["cellbold"]),
            Paragraph("Grade", styles["cellbold"]),
            Paragraph("Remarks", styles["cellbold"]),
        ]
    ]
    for subject in snapshot["subjects"]:
        obtained = subject["obtained"]
        if subject["status"] == "ABSENT":
            display = "AB"
        elif subject["status"] == "EXEMPT":
            display = "EX"
        else:
            display = str(obtained if obtained is not None else "—")
        table_data.append(
            [
                Paragraph(escape(subject["name"]), styles["cell"]),
                Paragraph(str(subject["max_marks"]), styles["cell"]),
                Paragraph(str(subject["pass_marks"]), styles["cell"]),
                Paragraph(display, styles["cell"]),
                Paragraph(escape(subject["grade"] or "—"), styles["cell"]),
                Paragraph(escape(subject["remarks"] or ""), styles["cell"]),
            ]
        )

    totals = snapshot["totals"]
    table_data.append(
        [
            Paragraph("Total", styles["cellbold"]),
            Paragraph(str(totals["max"]), styles["cellbold"]),
            Paragraph("", styles["cellbold"]),
            Paragraph(str(totals["obtained"]), styles["cellbold"]),
            Paragraph(escape(totals["grade"] or "—"), styles["cellbold"]),
            Paragraph("", styles["cellbold"]),
        ]
    )
    table = Table(table_data, colWidths=[58 * mm, 16 * mm, 16 * mm, 24 * mm, 18 * mm, 40 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINE),
                ("BACKGROUND", (0, -1), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))

    summary_rows = [
        [
            Paragraph(
                f"Total: <b>{totals['obtained']} / {totals['max']}</b>", styles["cell"]
            ),
            Paragraph(f"Percentage: <b>{totals['percentage']:.2f}%</b>", styles["cell"]),
            Paragraph(f"Grade: <b>{escape(totals['grade'] or '—')}</b>", styles["cell"]),
            Paragraph(
                f"Result: <b>{totals['result']}</b>", styles["cell"]
            ),
        ]
    ]
    summary = Table(summary_rows, colWidths=[43 * mm, 43 * mm, 43 * mm, 43 * mm])
    summary.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(summary)
    story.append(Spacer(1, 8))

    attendance = snapshot["attendance"]
    story.append(
        Paragraph(
            f"Attendance: <b>{attendance['present']}</b> present of <b>{attendance['total']}</b> "
            f"marked days"
            + (f" ({attendance['percentage']:.1f}%)" if attendance["percentage"] is not None else ""),
            styles["cell"],
        )
    )
    story.append(Spacer(1, 10))

    remarks = snapshot["remarks"]
    remark_rows = [
        [
            Paragraph("Class Teacher's Remarks", styles["label"]),
            Paragraph("Principal's Remarks", styles["label"]),
        ],
        [
            Paragraph(escape(remarks.get("teacher") or "—"), styles["remark"]),
            Paragraph(escape(remarks.get("principal") or "—"), styles["remark"]),
        ],
    ]
    remark_table = Table(remark_rows, colWidths=[86 * mm, 86 * mm])
    remark_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 22),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(remark_table)
    story.append(Spacer(1, 22))

    signatures = Table(
        [
            [
                Paragraph("____________________________", styles["cell"]),
                Paragraph("____________________________", styles["cell"]),
            ],
            [
                Paragraph("Class Teacher", styles["small"]),
                Paragraph("Principal", styles["small"]),
            ],
        ],
        colWidths=[86 * mm, 86 * mm],
    )
    signatures.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(signatures)

    story.append(Spacer(1, 14))
    policy = snapshot.get("policy", {})
    note = (
        "Absent subjects are counted as zero."
        if policy.get("absent_policy") == "ZERO"
        else "Absent subjects are excluded from totals."
    )
    story.append(
        Paragraph(
            escape(
                f"{note} Exempted subjects are excluded from totals. "
                "This is a computer-generated document issued by the school."
            ),
            styles["small"],
        )
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return str(path)


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(18 * mm, 8 * mm, "Generated by School OS")
    canvas.drawRightString(A4[0] - 18 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


# --------------------------------------------------------------------------
# Receipts
# --------------------------------------------------------------------------
def build_receipt_pdf(payment: dict, filename: str) -> str:
    school = payment["school"]
    styles = _styles(school.get("accent") or "#B7791F")
    path = _tmp_path(filename)
    doc = SimpleDocTemplate(
        str(path), pagesize=A5,
        leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"Receipt {payment['receipt_no']}",
    )
    story = []
    story.append(Paragraph(escape(school.get("name") or "School"), styles["school"]))
    story.append(Paragraph(escape(school.get("address") or ""), styles["address"]))
    story.append(Spacer(1, 4))
    rule = Table([[""]], colWidths=[120 * mm], rowHeights=[2])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), styles["accent"])]))
    story.append(rule)
    story.append(Paragraph("FEE RECEIPT", styles["doctitle"]))
    story.append(Spacer(1, 6))

    meta = Table(
        [
            [
                Paragraph("Receipt No.", styles["label"]),
                Paragraph(escape(payment["receipt_no"]), styles["value"]),
                Paragraph("Date", styles["label"]),
                Paragraph(escape(payment["paid_at"]), styles["value"]),
            ],
            [
                Paragraph("Student", styles["label"]),
                Paragraph(escape(payment["student"]), styles["value"]),
                Paragraph("Class", styles["label"]),
                Paragraph(escape(payment["class_section"]), styles["value"]),
            ],
        ],
        colWidths=[24 * mm, 40 * mm, 16 * mm, 40 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 8))

    rows = [[Paragraph("Particulars", styles["cellbold"]), Paragraph("Amount", styles["cellbold"])]]
    for item in payment["items"]:
        rows.append([Paragraph(escape(item["label"]), styles["cell"]),
                     Paragraph(format_money(item["amount_paise"]), styles["cell"])])
    rows.append(
        [
            Paragraph("Total received", styles["cellbold"]),
            Paragraph(format_money(payment["amount_paise"]), styles["cellbold"]),
        ]
    )
    table = Table(rows, colWidths=[85 * mm, 35 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, -1), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            escape(
                f"Amount in words: {payment['amount_words']}. "
                f"Payment mode: {payment['method']}."
            ),
            styles["small"],
        )
    )
    story.append(Spacer(1, 18))
    story.append(Paragraph("____________________________", styles["cell"]))
    story.append(Paragraph("Authorised Signatory", styles["small"]))

    doc.build(story)
    return str(path)


def amount_in_words(paise: int) -> str:
    """Indian numbering: crore / lakh / thousand."""
    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
        "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
        "Eighteen", "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two(n: int) -> str:
        if n < 20:
            return ones[n]
        return (tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")).strip()

    def three(n: int) -> str:
        if n < 100:
            return two(n)
        return (ones[n // 100] + " Hundred" + (" " + two(n % 100) if n % 100 else "")).strip()

    rupees = paise // 100
    paise_part = paise % 100
    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore, rest = divmod(rupees, 10_000_000)
        lakh, rest = divmod(rest, 100_000)
        thousand, rest = divmod(rest, 1000)
        if crore:
            parts.append(three(crore) + " Crore")
        if lakh:
            parts.append(three(lakh) + " Lakh")
        if thousand:
            parts.append(three(thousand) + " Thousand")
        if rest:
            parts.append(three(rest))
        words = " ".join(parts)
    text = f"Rupees {words}"
    if paise_part:
        text += f" and {two(paise_part)} Paise"
    return text + " only"

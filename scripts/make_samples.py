"""Create rights-safe examples authored for this repository, not training samples."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"
GOOD = """Northwind Supplies
INVOICE USD
Invoice No: NW-2026-0481
Invoice Date: 12 Aug 2026
Filter cartridges 10 in 24 408.00
Sealing rings box of 50 6 171.00
Delivery 1 45.00
Subtotal 624.00
Tax 8.5% 53.04
Total Due 677.04"""
BAD = """Ridgeway Trading
INVOICE USD
Invoice No: RT-9912
Invoice Date: 03 Aug 2026
Pallet wrap 12 216.00
Strapping tape 4 88.00
Subtotal 304.00
Tax 8.5% 25.84
Total Due 349.84"""
MANUAL = """Silver Birch Studio
SERVICE AGREEMENT
Contract No: SB-014
Date: 2026-08-12
Currency USD
The parties agree to prepare an illustrated handbook.
The engagement begins upon signature and ends on delivery.
Neither party may assign this agreement without written consent.
Authorized signatures: __________________"""

def main():
    OUT.mkdir(exist_ok=True)
    for name, text in (("valid-invoice.txt", GOOD), ("incorrect-total.txt", BAD), ("manual-contract.txt", MANUAL)):
        (OUT / name).write_text(text + "\n", encoding="utf-8")
    pdf = canvas.Canvas(str(OUT / "two-page-invoice.pdf"), pagesize=(612, 792), invariant=1)
    for text in (GOOD, "Supporting delivery note\nTwo boxes delivered in good condition.\nAuthorized by receiving desk."):
        page = pdf.beginText(45, 740)
        page.setFont("Helvetica", 12)
        for line in text.splitlines():
            page.textLine(line)
        pdf.drawText(page)
        pdf.showPage()
    pdf.save()
    image = Image.new("RGB", (1600, 1200), "white")
    fonts = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    font = next((ImageFont.truetype(p, 30) for p in fonts if Path(p).exists()), ImageFont.load_default(size=30))
    ImageDraw.Draw(image).multiline_text((70, 65), GOOD, fill="black", font=font, spacing=20)
    image.save(OUT / "scanned-invoice.png")
    pdf = canvas.Canvas(str(OUT / "scanned-invoice.pdf"), pagesize=(800, 600), invariant=1)
    pdf.drawImage(ImageReader(image), 0, 0, width=800, height=600)
    pdf.save()

if __name__ == "__main__":
    main()

from django.shortcuts import render
from django.http import HttpResponse, FileResponse
import io
import zipfile
import pikepdf
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.colors import HexColor
from pdf2docx import Converter
from docx import Document
import tempfile
from io import BytesIO

# Landing page
def index(request):
    return render(request, "index.html")


# ---------------- PDF ROTATE ----------------
def rotate(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        rotation_angle = int(request.POST.get("rotation", 0))
        pages_input = request.POST.get("pages", "").strip()

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf:
            def parse_pages(pages_str, total_pages):
                pages_to_rotate = set()
                if not pages_str:
                    return set(range(total_pages))
                for part in pages_str.split(","):
                    if "-" in part:
                        start, end = part.split("-")
                        pages_to_rotate.update(range(int(start)-1, int(end)))
                    else:
                        pages_to_rotate.add(int(part)-1)
                return pages_to_rotate

            pages_to_rotate = parse_pages(pages_input, len(pdf.pages))

            for i, page in enumerate(pdf.pages):
                if i in pages_to_rotate:
                    page.Rotate = (page.obj.get("/Rotate", 0) + rotation_angle) % 360

            output = io.BytesIO()
            pdf.save(output)
            output.seek(0)

        response = HttpResponse(output, content_type="application/pdf")
        response["Content-Disposition"] = "inline; filename=rotated.pdf"
        return response

    return render(request, "rotate.html")


# ---------------- PDF PROTECT ----------------
def protect_pdf(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        password = request.POST.get("user_password", "123")

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf:
            enc = pikepdf.Encryption(
                user=password,
                allow=pikepdf.Permissions(extract=False, print_lowres=True),
                R=4
            )
            output = io.BytesIO()
            pdf.save(output, encryption=enc)
            output.seek(0)

        response = HttpResponse(output, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="protected_{uploaded_file.name}"'
        return response

    return render(request, "protect.html")


# ---------------- PDF SPLIT ----------------
def split_pdf(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pages_input = request.POST.get("pages", "").strip()

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf:

            def parse_pages(pages_str, total_pages):
                pages_to_extract = set()
                if not pages_str:
                    return set(range(total_pages))
                for part in pages_str.split(","):
                    if "-" in part:
                        start, end = part.split("-")
                        pages_to_extract.update(range(int(start)-1, int(end)))
                    else:
                        pages_to_extract.add(int(part)-1)
                return pages_to_extract

            selected_pages = parse_pages(pages_input, len(pdf.pages))
            pdf_files = []

            for i, page in enumerate(pdf.pages):
                if i in selected_pages:
                    new_pdf = pikepdf.Pdf.new()
                    new_pdf.pages.append(page)
                    buf = io.BytesIO()
                    new_pdf.save(buf)
                    buf.seek(0)
                    pdf_files.append((f"page_{i+1}.pdf", buf.read()))

        if len(pdf_files) == 1:
            filename, content = pdf_files[0]
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            return response
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zipf:
                for filename, content in pdf_files:
                    zipf.writestr(filename, content)
            zip_buffer.seek(0)
            response = HttpResponse(zip_buffer, content_type="application/zip")
            response["Content-Disposition"] = 'attachment; filename="split_pdfs.zip"'
            return response

    return render(request, "split.html")


# ---------------- PDF MERGE ----------------
def merge_pdf(request):
    if request.method == "POST" and request.FILES.getlist("pdf_files"):
        uploaded_files = request.FILES.getlist("pdf_files")
        merged_pdf = pikepdf.Pdf.new()

        for uploaded_file in uploaded_files:
            pdf_data = uploaded_file.read()
            with pikepdf.open(io.BytesIO(pdf_data)) as pdf:
                merged_pdf.pages.extend(pdf.pages)

        output = io.BytesIO()
        merged_pdf.save(output)
        output.seek(0)

        response = HttpResponse(output, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="merged.pdf"'
        return response

    return render(request, "merge.html")


# ---------------- DELETE PAGES ----------------
def delete_pages(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pages_input = request.POST.get("pages", "").strip()

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf:

            pages_to_delete = set()
            for part in pages_input.split(","):
                if "-" in part:
                    start, end = map(int, part.split("-"))
                    pages_to_delete.update(range(start-1, end))
                elif part.isdigit():
                    pages_to_delete.add(int(part)-1)

            for p in sorted(pages_to_delete, reverse=True):
                if 0 <= p < len(pdf.pages):
                    del pdf.pages[p]

            output = io.BytesIO()
            pdf.save(output)
            output.seek(0)

        response = HttpResponse(output, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="modified.pdf"'
        return response

    return render(request, "delete.html")


# ---------------- COPY PAGES ----------------
def copy_pages(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pages_input = request.POST.get("pages", "").strip()
        insert_at = request.POST.get("insert_at", "").strip()

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf:
            total_pages = len(pdf.pages)

            pages_to_copy = [int(p)-1 for p in pages_input.split(",") if p.isdigit()]
            insert_index = int(insert_at)-1 if insert_at.isdigit() else total_pages

            for idx in pages_to_copy:
                pdf.pages.insert(insert_index, pikepdf.Page(pdf.pages[idx]))
                insert_index += 1

            # delete originals
            for idx in sorted(pages_to_copy, reverse=True):
                del pdf.pages[idx]

            output = io.BytesIO()
            pdf.save(output)
            output.seek(0)

        response = HttpResponse(output, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="copied_deleted.pdf"'
        return response

    return render(request, "copy.html")


# ---------------- EXTRACT IMAGES ----------------
def extract_images(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pdf_data = uploaded_file.read()
        image_files = []

        with pikepdf.open(io.BytesIO(pdf_data)) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                for img_name, raw_img in page.images.items():
                    pdf_img = pikepdf.PdfImage(raw_img)
                    buf = io.BytesIO()
                    pdf_img.extract_to(stream=buf)
                    buf.seek(0)
                    image_files.append((f"page{page_num}_{img_name}.jpg", buf.read()))

        if not image_files:
            return HttpResponse("No images found in this PDF.")

        if len(image_files) == 1:
            filename, content = image_files[0]
            response = HttpResponse(content, content_type="image/jpeg")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zipf:
                for filename, content in image_files:
                    zipf.writestr(filename, content)
            zip_buffer.seek(0)
            response = HttpResponse(zip_buffer, content_type="application/zip")
            response["Content-Disposition"] = 'attachment; filename="images.zip"'
            return response

    return render(request, "extract_images.html")


# ---------------- ADD TEXT WATERMARK ----------------
def add_text_watermark(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]

        watermark_text = request.POST.get("watermark_text", "CONFIDENTIAL")
        font_size = int(request.POST.get("font_size", 40))
        color = request.POST.get("color", "#000000")
        opacity = float(request.POST.get("opacity", 0.3))
        position = request.POST.get("position", "center")

        # create watermark PDF in memory
        wm_buffer = io.BytesIO()
        c = canvas.Canvas(wm_buffer, pagesize=letter)
        c.setFont("Helvetica-Bold", font_size)
        c.setFillColor(HexColor(color))
        c.setFillAlpha(opacity)

        if position == "center":
            c.translate(300, 400)
            c.rotate(45)
            c.drawCentredString(0, 0, watermark_text)
        elif position == "topleft":
            c.drawString(50, 750, watermark_text)
        elif position == "bottomright":
            c.drawRightString(550, 50, watermark_text)
        else:
            c.translate(300, 400)
            c.rotate(45)
            c.drawCentredString(0, 0, watermark_text)

        c.save()
        wm_buffer.seek(0)

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf, pikepdf.open(wm_buffer) as wm_pdf:
            wm_page = wm_pdf.pages[0]
            for page in pdf.pages:
                page.add_overlay(wm_page)

            output = io.BytesIO()
            pdf.save(output)
            output.seek(0)

        response = HttpResponse(output, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="watermarked.pdf"'
        return response

    return render(request, "watermark.html")


# ---------------- PDF → WORD ----------------
def pdf_to_word(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]

        # read PDF into memory
        pdf_data = uploaded_file.read()
        pdf_buffer = io.BytesIO(pdf_data)

        # create in-memory output for Word
        output_buffer = io.BytesIO()

        # use pdf2docx converter
        cv = Converter(pdf_buffer)
        cv.convert(output_buffer, start=0, end=None)
        cv.close()

        # make sure pointer is at start
        output_buffer.seek(0)

        response = HttpResponse(
            output_buffer,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        response["Content-Disposition"] = f'attachment; filename="{uploaded_file.name.replace(".pdf", ".docx")}"'
        return response

    return render(request, "pdf_to_word.html")



# ---------------- WORD → PDF ----------------
def word_to_pdf(request):
    if request.method == "POST" and request.FILES.get("word_file"):
        word_file = request.FILES["word_file"]

        # Load Word file into memory
        word_data = word_file.read()
        doc = Document(BytesIO(word_data))

        # Prepare PDF in memory
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=A4)
        width, height = A4

        y = height - 50  # starting y-position

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                c.drawString(50, y, text)
                y -= 20  # line spacing
                if y < 50:  # new page
                    c.showPage()
                    y = height - 50

        c.save()
        pdf_buffer.seek(0)

        response = HttpResponse(pdf_buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{word_file.name.replace(".docx", ".pdf")}"'
        return response

    return render(request, "word_to_pdf.html")
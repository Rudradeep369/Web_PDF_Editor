# my_app/views.py
from django.shortcuts import render
from django.http import HttpResponse
import pikepdf
import tempfile
import zipfile
import os
import io
# from django.core.files.storage import FileSystemStorage
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from pdf2docx import Converter
import pytesseract
from docx2pdf import convert

def index(request):
    return render(request, "index.html")

def rotate(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        rotation_angle = int(request.POST.get("rotation", 0))
        pages_input = request.POST.get("pages", "").strip()

        # open PDF from memory
        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf_my:

            # helper: parse page input
            def parse_pages(pages_str, total_pages):
                pages_to_rotate = set()
                if not pages_str:
                    return set(range(total_pages))  # rotate all
                for part in pages_str.split(","):
                    if "-" in part:
                        start, end = part.split("-")
                        pages_to_rotate.update(range(int(start)-1, int(end)))
                    else:
                        pages_to_rotate.add(int(part)-1)
                return pages_to_rotate

            pages_to_rotate = parse_pages(pages_input, len(pdf_my.pages))

            # rotate selected pages
            for i, page in enumerate(pdf_my.pages):
                if i in pages_to_rotate:
                    page.Rotate = (page.obj.get("/Rotate", 0) + rotation_angle) % 360

            # save to memory
            output_buffer = io.BytesIO()
            pdf_my.save(output_buffer)
            output_buffer.seek(0)

        # ✅ return rotated file directly from memory
        response = HttpResponse(output_buffer, content_type="application/pdf")
        response["Content-Disposition"] = "inline; filename=preview.pdf"
        return response

    return render(request, "rotate.html")



def protect_pdf(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        user_password = request.POST.get("user_password", "123")

        # open PDF from memory
        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf_my:
            # apply encryption
            no_extract = pikepdf.Encryption(
                user=user_password,
                allow=pikepdf.Permissions(extract=False, print_lowres=True),
                R=4
            )

            # save to memory
            output_buffer = io.BytesIO()
            pdf_my.save(output_buffer, encryption=no_extract)
            output_buffer.seek(0)

        # return as download
        response = HttpResponse(output_buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="protected_{uploaded_file.name}"'
        return response

    return render(request, "protect.html")


def split_pdf(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pages_input = request.POST.get("pages", "").strip()

        # helper to parse page input
        def parse_pages(pages_str, total_pages):
            pages_to_extract = set()
            if not pages_str:
                return set(range(total_pages))  # default: all pages
            for part in pages_str.split(","):
                if "-" in part:
                    start, end = part.split("-")
                    pages_to_extract.update(range(int(start)-1, int(end)))  # convert to 0-based
                else:
                    pages_to_extract.add(int(part)-1)
            return pages_to_extract

        with tempfile.TemporaryDirectory() as tmpdirname:
            # save uploaded file into temp
            input_path = os.path.join(tmpdirname, uploaded_file.name)
            with open(input_path, "wb") as f:
                for chunk in uploaded_file.chunks():
                    f.write(chunk)

            # open PDF inside with → closes properly
            with pikepdf.open(input_path) as pdf_my:
                selected_pages = parse_pages(pages_input, len(pdf_my.pages))

                pdf_files = []
                for i, page in enumerate(pdf_my.pages):
                    if i in selected_pages:
                        new_pdf = pikepdf.Pdf.new()
                        new_pdf.pages.append(page)
                        name = f"page_{i+1}.pdf"
                        filepath = os.path.join(tmpdirname, name)
                        new_pdf.save(filepath)
                        pdf_files.append(filepath)

            # ✅ if only one page → return that PDF
            if len(pdf_files) == 1:
                file_path = pdf_files[0]
                with open(file_path, "rb") as f:
                    response = HttpResponse(f.read(), content_type="application/pdf")
                    response["Content-Disposition"] = 'inline; filename="split_page.pdf"'
                    return response

            # ✅ if multiple pages → return as ZIP
            zip_path = os.path.join(tmpdirname, "split_pdfs.zip")
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for file in pdf_files:
                    zipf.write(file, os.path.basename(file))

            with open(zip_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="application/zip")
                response["Content-Disposition"] = 'attachment; filename="split_pdfs.zip"'
                return response

    return render(request, "split.html")

def merge_pdf(request):
    if request.method == "POST" and request.FILES.getlist("pdf_files"):
        uploaded_files = request.FILES.getlist("pdf_files")
        new_pdf = pikepdf.Pdf.new()

        # everything stays in a temp directory
        with tempfile.TemporaryDirectory() as tmpdirname:
            for uploaded_file in uploaded_files:
                # save file temporarily
                input_path = os.path.join(tmpdirname, uploaded_file.name)
                with open(input_path, "wb") as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)

                # open and append pages
                with pikepdf.open(input_path) as old_pdf:
                    new_pdf.pages.extend(old_pdf.pages)

            # save merged file in temp
            merged_path = os.path.join(tmpdirname, "merged.pdf")
            new_pdf.save(merged_path)

            # return as download
            with open(merged_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response["Content-Disposition"] = 'inline; filename="merged.pdf"'
                return response

    return render(request, "merge.html")


def delete_pages(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        pdf_file = request.FILES["pdf_file"]
        pages_to_delete = request.POST.get("pages")  # e.g. "1,2,5-7"

        with tempfile.TemporaryDirectory() as tmpdirname:
            # save uploaded file into temp only
            input_path = os.path.join(tmpdirname, pdf_file.name)
            with open(input_path, "wb") as f:
                for chunk in pdf_file.chunks():
                    f.write(chunk)

            # open and process
            with pikepdf.open(input_path) as pdf:
                pages = []
                if pages_to_delete:
                    for part in pages_to_delete.split(","):
                        if "-" in part:
                            start, end = map(int, part.split("-"))
                            pages.extend(range(start-1, end))  # inclusive
                        else:
                            pages.append(int(part)-1)

                for p in sorted(set(pages), reverse=True):
                    if 0 <= p < len(pdf.pages):
                        del pdf.pages[p]

                output_path = os.path.join(tmpdirname, "modified.pdf")
                pdf.save(output_path)

            # send response
            with open(output_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response["Content-Disposition"] = "inline; filename=preview.pdf"
                return response

    return render(request, "delete.html")


def copy_pages(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pages_input = request.POST.get("pages", "").strip()   # e.g. "1,3"
        insert_at = request.POST.get("insert_at", "").strip() # e.g. "5"

        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf_my:
            total_pages = len(pdf_my.pages)

            # parse pages to copy
            pages_to_copy = []
            for part in pages_input.split(","):
                if part.isdigit():
                    page_index = int(part) - 1  # 1-based → 0-based
                    if 0 <= page_index < total_pages:
                        pages_to_copy.append(page_index)

            # parse insert position
            if insert_at.isdigit():
                insert_index = min(int(insert_at) - 1, total_pages)
            else:
                insert_index = total_pages  # append if not provided

            # STEP 1: insert copies
            for idx in pages_to_copy:
                copied_page = pikepdf.Page(pdf_my.pages[idx])
                pdf_my.pages.insert(insert_index, copied_page)
                insert_index += 1

            # STEP 2: delete originals (important → reverse order to avoid shifting indexes)
            for idx in sorted(pages_to_copy, reverse=True):
                del pdf_my.pages[idx]

            # save updated PDF
            output_buffer = io.BytesIO()
            pdf_my.save(output_buffer)
            output_buffer.seek(0)

        response = HttpResponse(output_buffer, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="copied_and_deleted.pdf"'
        return response

    return render(request, "copy.html")


def extract_images(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pdf_data = uploaded_file.read()

        image_files = []

        with pikepdf.open(io.BytesIO(pdf_data)) as pdf_my:
            for page_num, page in enumerate(pdf_my.pages, start=1):
                for image_name, raw_image in page.images.items():
                    pdf_img = pikepdf.PdfImage(raw_image)
                    img_buffer = io.BytesIO()
                    pdf_img.extract_to(stream=img_buffer)  # ✅ no format
                    img_buffer.seek(0)

                    # fallback extension (most are JPEG)
                    filename = f"page{page_num}_{image_name}.jpg"
                    image_files.append((filename, img_buffer.read()))

        if not image_files:
            return HttpResponse("No images found in this PDF.")

        if len(image_files) > 1:
            # return ZIP
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                for filename, content in image_files:
                    zip_file.writestr(filename, content)
            zip_buffer.seek(0)
            response = HttpResponse(zip_buffer, content_type="application/zip")
            response["Content-Disposition"] = 'attachment; filename="extracted_images.zip"'
            return response
        else:
            # return single image
            filename, content = image_files[0]
            response = HttpResponse(content, content_type="image/jpeg")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

    return render(request, "extract_images.html")


def add_text_watermark(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]

        # Get user inputs
        watermark_text = request.POST.get("watermark_text", "CONFIDENTIAL")
        font_size = int(request.POST.get("font_size", 40))
        color = request.POST.get("color", "#000000")   # hex color
        opacity = float(request.POST.get("opacity", 0.3))  # 0 → transparent, 1 → solid
        position = request.POST.get("position", "center")  # center, topleft, bottomright

        # Step 1: Generate watermark PDF in memory
        wm_buffer = io.BytesIO()
        c = canvas.Canvas(wm_buffer, pagesize=letter)
        c.setFont("Helvetica-Bold", font_size)
        c.setFillColor(HexColor(color))
        c.setFillAlpha(opacity)

        c.saveState()

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

        c.restoreState()
        c.save()
        wm_buffer.seek(0)

        # Step 2: Read PDFs into memory
        pdf_data = uploaded_file.read()
        with pikepdf.open(io.BytesIO(pdf_data)) as pdf_my, pikepdf.open(wm_buffer) as pdf_wm:
            wm_page = pdf_wm.pages[0]

            # Step 3: Apply watermark to every page
            for page in pdf_my.pages:
                page.add_overlay(wm_page)

            # Step 4: Save output
            output_buffer = io.BytesIO()
            pdf_my.save(output_buffer)
            output_buffer.seek(0)

        # Step 5: Return watermarked PDF
        response = HttpResponse(output_buffer, content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="copied_and_deleted.pdf"'
        return response

    return render(request, "watermark.html")


def pdf_to_word(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]

        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
            for chunk in uploaded_file.chunks():
                temp_pdf.write(chunk)
            temp_pdf_path = temp_pdf.name

        # Create temporary output Word file
        temp_docx_path = temp_pdf_path.replace(".pdf", ".docx")

        # Convert PDF → Word
        cv = Converter(temp_pdf_path)
        cv.convert(temp_docx_path, start=0, end=None)
        cv.close()

        # Read output and send as response
        with open(temp_docx_path, "rb") as f:
            word_data = f.read()

        # Cleanup
        os.remove(temp_pdf_path)
        os.remove(temp_docx_path)

        response = HttpResponse(word_data, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        response["Content-Disposition"] = f'attachment; filename="{uploaded_file.name.replace(".pdf", ".docx")}"'
        return response

    return render(request, "pdf_to_word.html")

def word_to_pdf(request):
    if request.method == "POST" and request.FILES.get("word_file"):
        uploaded_file = request.FILES["word_file"]

        # Save temp Word file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_word:
            for chunk in uploaded_file.chunks():
                tmp_word.write(chunk)
            tmp_word_path = tmp_word.name

        # Output PDF path
        tmp_pdf_path = tmp_word_path.replace(".docx", ".pdf")

        # Convert Word → PDF
        convert(tmp_word_path, tmp_pdf_path)

        # Return PDF to user
        with open(tmp_pdf_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="application/pdf")
            response["Content-Disposition"] = "inline; filename=preview.pdf"
            return response

    return render(request, "word_to_pdf.html")

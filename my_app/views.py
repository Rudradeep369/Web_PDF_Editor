# my_app/views.py
from django.shortcuts import render
from django.http import HttpResponse
import pikepdf
import tempfile
import zipfile
import os
import io
from django.core.files.storage import FileSystemStorage

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

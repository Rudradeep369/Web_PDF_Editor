# my_app/views.py
from django.shortcuts import render
from django.http import HttpResponse
import pikepdf
import tempfile
import zipfile
import os
from django.core.files.storage import FileSystemStorage

def index(request):
    return render(request, "index.html")

def rotate(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        rotation_angle = int(request.POST.get("rotation", 0))
        pages_input = request.POST.get("pages", "").strip()  # e.g., "1,3,5" or "2-4"

        fs = FileSystemStorage()
        input_file = fs.save(uploaded_file.name, uploaded_file)
        input_path = fs.path(input_file)

        output_path = fs.path("rotated_" + uploaded_file.name)

        pdf_my = pikepdf.open(input_path)

        # function to parse page input
        def parse_pages(pages_str, total_pages):
            pages_to_rotate = set()
            if not pages_str:
                return set(range(total_pages))  # rotate all pages
            for part in pages_str.split(","):
                if "-" in part:
                    start, end = part.split("-")
                    pages_to_rotate.update(range(int(start)-1, int(end)))  # convert to 0-based
                else:
                    pages_to_rotate.add(int(part)-1)  # convert to 0-based
            return pages_to_rotate

        pages_to_rotate = parse_pages(pages_input, len(pdf_my.pages))

        # rotate selected pages
        for i, page in enumerate(pdf_my.pages):
            if i in pages_to_rotate:
                page.Rotate = (page.obj.get("/Rotate", 0) + rotation_angle) % 360

        pdf_my.save(output_path)

        # return rotated file as download
        with open(output_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="application/pdf")
            response["Content-Disposition"] = "inline; filename=preview.pdf"
            return response


    return render(request, "rotate.html")


def protect_pdf(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        user_password = request.POST.get("user_password", "123")
        # owner_password = request.POST.get("owner_password", "owner")

        fs = FileSystemStorage()
        input_file = fs.save(uploaded_file.name, uploaded_file)
        input_path = fs.path(input_file)

        output_path = fs.path("protected_" + uploaded_file.name)

        # open and apply encryption
        pdf_my = pikepdf.open(input_path)

        no_extract = pikepdf.Encryption(
            user=user_password, 
            # owner=owner_password,
            allow=pikepdf.Permissions(extract=False, print_lowres=True),
            R=4
        )

        pdf_my.save(output_path, encryption=no_extract)

        # return protected PDF
        with open(output_path, "rb") as f:
            response = HttpResponse(f.read(), content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="protected_{uploaded_file.name}"'
            return response

    return render(request, "protect.html")


def split_pdf(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        uploaded_file = request.FILES["pdf_file"]
        pages_input = request.POST.get("pages", "").strip()

        # Save uploaded file temporarily
        fs = FileSystemStorage()
        input_file = fs.save(uploaded_file.name, uploaded_file)
        input_path = fs.path(input_file)

        pdf_my = pikepdf.open(input_path)

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

        selected_pages = parse_pages(pages_input, len(pdf_my.pages))

        # create temporary directory for split files
        with tempfile.TemporaryDirectory() as tmpdirname:
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
                    response["Content-Disposition"] = "inline; filename=preview.pdf"
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

        fs = FileSystemStorage()
        new_pdf = pikepdf.Pdf.new()

        # save each uploaded file temporarily
        with tempfile.TemporaryDirectory() as tmpdirname:
            for uploaded_file in uploaded_files:
                input_file = fs.save(uploaded_file.name, uploaded_file)
                input_path = fs.path(input_file)

                old_pdf = pikepdf.open(input_path)
                new_pdf.pages.extend(old_pdf.pages)

            # save merged file
            merged_path = os.path.join(tmpdirname, "merged.pdf")
            new_pdf.save(merged_path)

            # return as download
            with open(merged_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response["Content-Disposition"] = "inline; filename=preview.pdf"
                return response

    return render(request, "merge.html")


def delete_pages(request):
    if request.method == "POST" and request.FILES.get("pdf_file"):
        pdf_file = request.FILES["pdf_file"]
        pages_to_delete = request.POST.get("pages")  # e.g. "1,2,5-7"

        # Save uploaded PDF to temp
        with tempfile.TemporaryDirectory() as tmpdirname:
            input_path = os.path.join(tmpdirname, pdf_file.name)
            with open(input_path, "wb") as f:
                for chunk in pdf_file.chunks():
                    f.write(chunk)

            # Open inside "with" so file closes after editing
            with pikepdf.open(input_path) as pdf:
                # Parse user input (pages are 1-based, Python uses 0-based)
                pages = []
                if pages_to_delete:
                    for part in pages_to_delete.split(","):
                        if "-" in part:
                            start, end = map(int, part.split("-"))
                            pages.extend(range(start-1, end))  # inclusive
                        else:
                            pages.append(int(part)-1)

                # Delete pages safely (descending order)
                for p in sorted(set(pages), reverse=True):
                    if 0 <= p < len(pdf.pages):
                        del pdf.pages[p]

                # Save modified PDF to a NEW file
                output_path = os.path.join(tmpdirname, "modified.pdf")
                pdf.save(output_path)

            # Now file is closed, safe to read and send
            with open(output_path, "rb") as f:
                response = HttpResponse(f.read(), content_type="application/pdf")
                response["Content-Disposition"] = "inline; filename=preview.pdf"
                return response

    return render(request, "delete.html")
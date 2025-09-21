# my_app/views.py
from django.shortcuts import render
from django.http import HttpResponse
import pikepdf
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
            response["Content-Disposition"] = f'attachment; filename="rotated_{uploaded_file.name}"'
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

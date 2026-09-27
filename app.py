import os
import uuid

from flask import (
    Flask,
    render_template,
    request,
    redirect
)

from werkzeug.utils import secure_filename

from modules.pdf_processor.extractor import (
    extract_form16_data
)

from modules.tax_engine.old_regime import (
    calculate_old_regime
)

from modules.tax_engine.new_regime import (
    calculate_new_regime
)

from modules.tax_engine.tax_compare import (
    compare_tax_regimes
)


app = Flask(__name__)

app.secret_key = os.environ.get(
    "TAXNOVA_SECRET_KEY",
    "taxnova_dev_secret"
)


# ============================================================
# UPLOAD CONFIGURATION
# ============================================================

UPLOAD_FOLDER = os.path.join(
    os.getcwd(),
    "uploads"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"pdf"}

MAX_FILE_SIZE = 10 * 1024 * 1024

app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def allowed_file(filename):

    return (
        filename
        and "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def create_safe_filename(filename):

    safe_name = secure_filename(filename)

    if not safe_name:

        safe_name = "form16.pdf"

    extension = os.path.splitext(
        safe_name
    )[1].lower()

    return (
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )


def parse_integer(value):

    if value is None:

        raise ValueError(
            "Value is missing."
        )

    value = (
        str(value)
        .replace(",", "")
        .replace("₹", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .strip()
    )

    return int(float(value))


# ============================================================
# BASIC ROUTES
# ============================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form.get(
            "name",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        print("Name:", name)
        print("Email:", email)

        # Never print passwords.

        return redirect("/login")

    return render_template(
        "register.html"
    )


@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        print(
            "Login Email:",
            email
        )

        # Never print passwords.

        return redirect(
            "/dashboard"
        )

    return render_template(
        "login.html"
    )


@app.route("/logout")
def logout():

    return render_template(
        "logout.html"
    )


@app.route("/dashboard")
def dashboard():

    return render_template(
        "dashboard.html"
    )


# ============================================================
# UPLOAD + PROCESS
# ============================================================

@app.route(
    "/upload",
    methods=["GET", "POST"]
)
def upload():

    if request.method == "GET":

        return render_template(
            "upload.html"
        )


    # --------------------------------------------------------
    # 1. File exists?
    # --------------------------------------------------------

    if "pdf_file" not in request.files:

        return render_template(
            "error.html",
            message=(
                "Please select a Form 16 PDF "
                "before uploading."
            )
        )


    pdf = request.files["pdf_file"]


    # --------------------------------------------------------
    # 2. Empty file?
    # --------------------------------------------------------

    if not pdf or not pdf.filename:

        return render_template(
            "error.html",
            message=(
                "No file was selected. "
                "Please choose a Form 16 PDF."
            )
        )


    # --------------------------------------------------------
    # 3. Extension validation
    # --------------------------------------------------------

    if not allowed_file(pdf.filename):

        return render_template(
            "error.html",
            message=(
                "Only PDF files are supported. "
                "Please upload your Form 16 PDF."
            )
        )


    # --------------------------------------------------------
    # 4. Safe filename
    # --------------------------------------------------------

    filename = create_safe_filename(
        pdf.filename
    )

    pdf_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        filename
    )


    # --------------------------------------------------------
    # 5. Save
    # --------------------------------------------------------

    try:

        pdf.save(pdf_path)

    except Exception as e:

        print(
            "Upload save error:",
            e
        )

        return render_template(
            "error.html",
            message=(
                "We couldn't save your document. "
                "Please try again."
            )
        )


    try:

        # ----------------------------------------------------
        # 6. Complete extraction pipeline
        # ----------------------------------------------------

        extracted_data = extract_form16_data(
            pdf_path
        )


        # ----------------------------------------------------
        # 7. Extraction error
        # ----------------------------------------------------

        if (
            not extracted_data
            or "error" in extracted_data
        ):

            return render_template(
                "error.html",
                message=(
                    extracted_data.get(
                        "error",
                        "We couldn't read this document."
                    )
                )
            )


        # ----------------------------------------------------
        # 8. Salary validation
        # ----------------------------------------------------

        salary_value = extracted_data.get(
            "salary"
        )

        if salary_value is None:

            return render_template(
                "error.html",
                message=(
                    "We found a Form 16, but couldn't "
                    "find the gross salary. Please "
                    "verify your document or enter "
                    "the amount manually."
                )
            )


        try:

            salary = parse_integer(
                salary_value
            )

        except ValueError:

            return render_template(
                "error.html",
                message=(
                    "The extracted salary value "
                    "couldn't be understood. "
                    "Please verify it manually."
                )
            )


        # ----------------------------------------------------
        # 9. Salary sanity check
        # ----------------------------------------------------

        if salary < 0:

            return render_template(
                "error.html",
                message=(
                    "The extracted salary is invalid."
                )
            )


        # ----------------------------------------------------
        # 10. Tax calculation
        # ----------------------------------------------------

        try:

            old_tax = calculate_old_regime(
                salary
            )

            new_tax = calculate_new_regime(
                salary
            )

            comparison = compare_tax_regimes(
                old_tax,
                new_tax
            )

        except Exception as e:

            print(
                "Tax calculation error:",
                e
            )

            return render_template(
                "error.html",
                message=(
                    "We couldn't calculate your tax "
                    "from the extracted information."
                )
            )


        # ----------------------------------------------------
        # 11. Add tax results
        # ----------------------------------------------------

        extracted_data["old_tax"] = old_tax

        extracted_data["new_tax"] = new_tax

        extracted_data["best_regime"] = (
            comparison["best_regime"]
        )

        extracted_data["savings"] = (
            comparison["savings"]
        )


        # ----------------------------------------------------
        # 12. Send everything to review
        # ----------------------------------------------------

        return render_template(
            "review.html",
            data=extracted_data
        )


    finally:

        # ----------------------------------------------------
        # 13. Always delete temporary PDF
        # ----------------------------------------------------

        try:

            if os.path.exists(pdf_path):

                os.remove(pdf_path)

        except Exception as e:

            print(
                "Temporary file cleanup error:",
                e
            )


# ============================================================
# SUCCESS
# ============================================================

@app.route(
    "/success",
    methods=["POST"]
)
def success():

    data = {

        "salary": request.form.get(
            "salary",
            ""
        ),

        "tds": request.form.get(
            "tds",
            ""
        ),

        "employer": request.form.get(
            "employer",
            ""
        ),

        "old_tax": request.form.get(
            "old_tax",
            ""
        ),

        "new_tax": request.form.get(
            "new_tax",
            ""
        ),

        "best_regime": request.form.get(
            "best_regime",
            ""
        ),

        "savings": request.form.get(
            "savings",
            ""
        ),

    }

    return render_template(
        "success.html",
        data=data
    )


# ============================================================
# FILE TOO LARGE
# ============================================================

@app.errorhandler(413)
def file_too_large(error):

    return render_template(
        "error.html",
        message=(
            "This PDF is too large. "
            "Please upload a file smaller than 10 MB."
        )
    ), 413


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
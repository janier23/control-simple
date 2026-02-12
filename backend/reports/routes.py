from flask import Blueprint, render_template, session, redirect, url_for

reports_bp = Blueprint(
    "reports",
    __name__,
    url_prefix="/reports"
)

@reports_bp.route("/")
def reports():
    if "usuario_id" not in session:
        return redirect(url_for("auth.login"))

    return render_template("reports/reports.html")

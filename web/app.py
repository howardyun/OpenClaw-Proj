from __future__ import annotations

from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

from .services.result_loader import ResultLoadError, load_case_result
from .services.scan_runner import ScanRunError, run_single_skill_scan

REPO_ROOT = Path(__file__).resolve().parents[1]


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        SECRET_KEY="dev",
        SCAN_PYTHON_BIN=None,
        SCAN_SCRIPT_PATH=str(REPO_ROOT / "scripts" / "run_single_skill_from_skills_sh.py"),
        SCAN_DB_PATH=str(REPO_ROOT / "crawling" / "skills" / "skills_sh" / "skills.db"),
        SCAN_REPOS_ROOT=str(REPO_ROOT / "skills" / "skill_sh_test"),
        SCAN_OUTPUT_ROOT=str(REPO_ROOT / "outputs" / "web_runs"),
        SCAN_MATRIX_PATH=str(REPO_ROOT / "analyzer" / "security matrix.md"),
        SCAN_LLM_REVIEW_MODE="off",
    )
    if test_config:
        app.config.update(test_config)

    @app.get("/")
    def index():
        return render_template("index.html", error=None, skill_id="")

    @app.post("/scan")
    def scan():
        skill_id = request.form.get("skill_id", "").strip()
        try:
            result = run_single_skill_scan(
                skill_id,
                python_bin=app.config["SCAN_PYTHON_BIN"],
                script_path=app.config["SCAN_SCRIPT_PATH"],
                db_path=app.config["SCAN_DB_PATH"],
                repos_root=app.config["SCAN_REPOS_ROOT"],
                output_root=app.config["SCAN_OUTPUT_ROOT"],
                matrix_path=app.config["SCAN_MATRIX_PATH"],
                llm_review_mode=app.config["SCAN_LLM_REVIEW_MODE"],
            )
        except ScanRunError as exc:
            return render_template("index.html", error=str(exc), skill_id=skill_id), 200

        return redirect(
            url_for("result_detail", run_id=result.run_id, skill_key=result.skill_key)
        )

    @app.get("/results/<run_id>/<skill_key>")
    def result_detail(run_id: str, skill_key: str):
        try:
            view_model = load_case_result(
                run_id,
                skill_key,
                output_root=app.config["SCAN_OUTPUT_ROOT"],
            )
        except ResultLoadError as exc:
            abort(404, description=str(exc))
        return render_template("result.html", result=view_model)

    @app.errorhandler(404)
    def handle_not_found(error):
        return render_template("index.html", error=error.description, skill_id=""), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

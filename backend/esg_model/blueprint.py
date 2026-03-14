"""
Flask Blueprint - 기존 MVP 앱에 한 줄로 등록 가능

등록 방법:
    from esg_module import esg_bp
    app.register_blueprint(esg_bp, url_prefix="/api")

엔드포인트:
    GET  /api/esg/<stock_code>              → 분석 결과 반환
    GET  /api/esg/<stock_code>?force=1      → 캐시 무시 재분석
"""
from flask import Blueprint, jsonify, request
from .analyzer import analyze_by_stock_code

esg_bp = Blueprint("esg", __name__)


@esg_bp.route("/esg/<stock_code>")
def get_esg(stock_code: str):
    """
    성공 (보고서 있음):  200  {"stock_code":..., "risks":..., "opportunities":..., ...}
    보고서 없음:         204  {}
    서버 오류:           500  {"error": "..."}
    """
    force = request.args.get("force", "0") == "1"
    try:
        result = analyze_by_stock_code(stock_code, force_refresh=force)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if result is None:
        return jsonify({}), 204

    if "error" in result:
        return jsonify(result), 500

    return jsonify(result), 200

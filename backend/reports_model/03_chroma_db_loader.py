import os
import json
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
try:
    from langchain_chroma import Chroma
except ImportError:
    from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

# 환경변수 로드
load_dotenv()

def flatten_metadata(metadata_dict):
    flat_meta = {}
    for key, value in metadata_dict.items():
        if value is None:
            flat_meta[key] = "None"
        elif isinstance(value, list):
            flat_meta[key] = ", ".join(str(v) for v in value)
        else:
            flat_meta[key] = str(value)
    return flat_meta

def create_document_from_json(json_path):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    common_meta = data.get("common_metadata", {})
    specific_data = data.get("specific_data", {})
    
    raw_metadata = {**common_meta}
    if "company_name" in specific_data: raw_metadata["company_name"] = specific_data["company_name"]
    if "ticker" in specific_data: raw_metadata["ticker"] = specific_data["ticker"]
    if "sector_name" in specific_data: raw_metadata["sector_name"] = specific_data["sector_name"]
        
    clean_metadata = flatten_metadata(raw_metadata)
    clean_metadata["source"] = os.path.basename(json_path)

    # 원문 URL 사이드카 파일 읽기 (크롤러가 저장한 .url 파일)
    # parsed_data/.../file.json → reports/.../file.url 경로 추정
    json_basename = os.path.basename(json_path).replace(".json", "")
    category = os.path.basename(os.path.dirname(json_path))
    _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(json_path)))
    url_path = os.path.join(_backend_dir, "reports", category, json_basename + ".url")
    if os.path.exists(url_path):
        with open(url_path, "r", encoding="utf-8") as _f:
            clean_metadata["naver_pdf_url"] = _f.read().strip()

    content_lines = []
    content_lines.append(f"리포트 제목: {common_meta.get('report_title', '제목없음')}")
    
    for key, value in specific_data.items():
        if not value: continue
        key_ko = key.replace("_", " ").title()
        if isinstance(value, list):
            val_str = "\n".join([f"  - {item}" for item in value])
            content_lines.append(f"[{key_ko}]\n{val_str}")
        else:
            content_lines.append(f"[{key_ko}]: {value}")
            
    page_content = "\n\n".join(content_lines)
    return Document(page_content=page_content, metadata=clean_metadata)

def run_embedding():
    from pathlib import Path
    _backend_dir = Path(__file__).resolve().parent.parent
    base_dir = str(_backend_dir / "parsed_data")
    reports_db_path = str(_backend_dir / "reports_chroma_db")

    if not os.path.exists(base_dir):
        print("❌ parsed_data 폴더가 없습니다. 2단계 추출을 먼저 진행해주세요.")
        return

    documents = []
    
    for category in os.listdir(base_dir):
        category_path = os.path.join(base_dir, category)
        if not os.path.isdir(category_path):
            continue
            
        for file in os.listdir(category_path):
            if file.endswith('.json'):
                json_path = os.path.join(category_path, file)
                doc = create_document_from_json(json_path)
                documents.append(doc)

    if not documents:
        print("❌ 변환할 JSON 문서가 없습니다.")
        return

    print(f"\n총 {len(documents)}개의 리포트를 Chroma DB에 임베딩합니다...")

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    
    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=reports_db_path,
        collection_name="financial_reports"
    )
    
    print(f"✅ Chroma DB 저장 완료! (저장 위치: {reports_db_path})")

if __name__ == "__main__":
    run_embedding()
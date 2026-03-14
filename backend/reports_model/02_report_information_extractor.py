import os
import json
import pdfplumber
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()

def extract_text_and_tables(pdf_path):
    full_content = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text: full_content.append(text)
                
                for table in page.extract_tables():
                    raw_table = "\n".join([" | ".join([str(cell).strip().replace('\n', ' ') if cell else "" for cell in row]) for row in table])
                    full_content.append(raw_table)
        return "\n\n".join(full_content)
    except Exception as e:
        print(f"❌ PDF 읽기 에러: {e}")
        return None

def get_category_schema_prompt(category):
    common_schema = """
    "common_metadata": {
        "report_type": "종목분석, 산업분석, 시황정보, 투자정보 중 하나",
        "report_date": "발간일 (YYYY-MM-DD)",
        "brokerage": "증권사명",
        "analyst_name": "작성자명 (여러 명일 경우 콤마로 구분)"
    }"""
    # (스키마 내용은 이전과 동일하여 생략 없이 축약 형태로 삽입했습니다. 실제 복사 시 이전 스키마를 그대로 유지해도 무방합니다)
    specific_schema = '"specific_data": {}'
    if category == "종목분석":
        specific_schema = '"specific_data": { "company_name": "종목명", "ticker": "종목코드 (숫자 6자리)", "investment_rating": "투자의견", "investment_points": ["추천 사유 및 핵심 이유 배열"], "risk_factors": ["고객 고지 리스크 배열"], "shareholder_structure": "주요 주주 지분율 텍스트 요약" }'
    elif category == "산업분석":
        specific_schema = '"specific_data": { "sector_name": "산업/섹터", "industry_rating": "산업 투자의견", "top_picks": ["최선호주 리스트 배열"], "industry_trends": ["산업 동향 배열"], "risk_factors": ["산업 리스크 배열"] }'
    elif category == "시황정보":
        specific_schema = '"specific_data": { "market_summary": "시황 요약", "macro_indicators": "거시 지표 추이", "fund_flows": "수급 동향", "key_news": ["핵심 이슈 배열"] }'
    elif category == "투자정보":
        specific_schema = '"specific_data": { "strategy_theme": "투자 전략 테마", "recommended_portfolio": ["편입 종목 리스트"], "strategy_logic": ["전략 논리 배열"], "quant_factors": ["핵심 팩터 배열"] }'

    return f"{{\n{common_schema},\n{specific_schema}\n}}"

def extract_title_from_filename(filename):
    try:
        parts = filename.replace(".pdf", "").split("_", 3)
        if len(parts) >= 4: return parts[3]
        return filename.replace(".pdf", "")
    except:
        return filename.replace(".pdf", "")

def run_parser():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    parser = JsonOutputParser()
    
    prompt = PromptTemplate(
        template="""당신은 증권사 리포트 인사이트 추출 AI입니다. 요구하는 JSON 형식에 맞춰 비정형 데이터를 추출하세요. 없는 정보는 null 처리하세요.
        [요구 스키마 형식]
        {schema_format}
        [리포트 내용]
        {report_content}
        """,
        input_variables=["schema_format", "report_content"]
    )
    chain = prompt | llm | parser

    base_dir, output_dir = "reports", "parsed_data"
    os.makedirs(output_dir, exist_ok=True)
    categories = ["종목분석", "산업분석", "시황정보", "투자정보"]

    for category in categories:
        category_path = os.path.join(base_dir, category)
        if not os.path.exists(category_path): continue
            
        print(f"\n[{category}] 비정형 JSON 데이터 추출 시작...")
        pdf_files = [f for f in os.listdir(category_path) if f.endswith('.pdf')]
        
        # 💡 전체 파일 파싱 진행 ([:1] 제한 제거)
        for pdf_file in pdf_files: 
            pdf_path = os.path.join(category_path, pdf_file)
            exact_title = extract_title_from_filename(pdf_file)
            
            # 파싱된 JSON이 이미 있으면 중복 비용 방지
            out_category_dir = os.path.join(output_dir, category)
            os.makedirs(out_category_dir, exist_ok=True)
            save_path = os.path.join(out_category_dir, pdf_file.replace('.pdf', '.json'))
            if os.path.exists(save_path): continue

            report_content = extract_text_and_tables(pdf_path)
            if not report_content: continue
                
            report_content = report_content[:100000] 
            schema_format = get_category_schema_prompt(category)
            
            try:
                extracted_json = chain.invoke({"schema_format": schema_format, "report_content": report_content})
                
                if "common_metadata" not in extracted_json: extracted_json["common_metadata"] = {}
                extracted_json["common_metadata"]["report_title"] = exact_title
                
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(extracted_json, f, ensure_ascii=False, indent=4)
                print(f"    ✅ 파싱 완료: {pdf_file}")
            except Exception as e:
                print(f"    ❌ 파싱 에러 ({pdf_file}): {e}")

if __name__ == "__main__":
    run_parser()
import os
import time
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

def sanitize_filename(filename):
    """윈도우/맥 파일명으로 사용할 수 없는 특수문자 제거"""
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

def download_all_naver_reports(base_dir="reports", days_to_fetch=30):
    target_categories = {
        "종목분석": "https://finance.naver.com/research/company_list.naver",
        "산업분석": "https://finance.naver.com/research/industry_list.naver",
        "시황정보": "https://finance.naver.com/research/market_info_list.naver",
        "투자정보": "https://finance.naver.com/research/invest_list.naver"
    }
    
    headers = {"User-Agent": "Mozilla/5.0"}
    cutoff_date = datetime.now().date() - timedelta(days=days_to_fetch)
    
    for category, base_url in target_categories.items():
        category_dir = os.path.join(base_dir, category)
        os.makedirs(category_dir, exist_ok=True)
            
        print(f"\n========================================")
        print(f"[{category}] 최근 {days_to_fetch}일치 전체 리포트 수집 시작... ")
        print(f"========================================")
        
        page = 1
        stop_pagination = False
        downloaded = 0
        
        while not stop_pagination:
            url = f"{base_url}?page={page}"
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.content, "html.parser")
            
            file_tds = soup.select("td.file")
            
            if not file_tds:
                break
            
            for td in file_tds: 
                tr = td.find_parent("tr")
                
                # 💡 버그 수정 1: 배열 마지막이 아니라 class="date"로 정확히 날짜 추출
                date_td = tr.select_one("td.date")
                if not date_td:
                    continue
                    
                date_str = date_td.text.strip()
                try:
                    report_date = datetime.strptime(date_str, "%y.%m.%d").date()
                except ValueError:
                    continue
                
                if report_date < cutoff_date:
                    stop_pagination = True
                    break
                
                pdf_link = td.find("a")
                if not pdf_link: continue
                
                pdf_url = pdf_link.get("href")
                if not pdf_url.startswith("http"): continue
                
                original_filename = pdf_url.split("/")[-1]
                file_id_part = original_filename.replace(".pdf", "")
                
                title_tag = tr.select_one("a[href*='_read.naver']")
                raw_title = title_tag.text.strip() if title_tag else "제목없음"
                
                # 💡 버그 수정 2: '첨부파일' td 바로 앞 칸에 있는 증권사명 추출
                broker_td = td.find_previous_sibling("td")
                broker_name = broker_td.text.strip() if broker_td else "알수없음"
                
                safe_title = sanitize_filename(raw_title)
                new_filename = f"{file_id_part}_{safe_title}.pdf"
                save_path = os.path.join(category_dir, new_filename)
                
                if os.path.exists(save_path):
                    continue
                
                try:
                    pdf_response = requests.get(pdf_url, headers=headers)
                    with open(save_path, "wb") as f:
                        f.write(pdf_response.content)
                    # 원문 URL 저장 (백엔드에서 직접 링크 제공용)
                    url_path = save_path.replace(".pdf", ".url")
                    with open(url_path, "w", encoding="utf-8") as f:
                        f.write(pdf_url)
                    print(f" -> 다운로드 완료: [{broker_name}] {new_filename} ({date_str})")
                    downloaded += 1
                except Exception as e:
                    print(f" -> 다운로드 실패 ({new_filename}): {e}")
                
                time.sleep(1) 
            
            page += 1

        print(f"[{category}] 총 {downloaded}건 수집 완료.")

if __name__ == "__main__":
    download_all_naver_reports(days_to_fetch=30)
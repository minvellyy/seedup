import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# 환경변수 로드
load_dotenv()

def format_docs(docs):
    """검색된 문서들을 LLM이 읽기 좋게 출처와 함께 포맷팅"""
    formatted_docs = []
    for i, doc in enumerate(docs):
        # 3단계에서 저장해둔 메타데이터를 꺼내옵니다.
        source = doc.metadata.get('source', '알 수 없는 파일')
        title = doc.metadata.get('report_title', '제목 없음')
        date = doc.metadata.get('report_date', '날짜 미상')
        brokerage = doc.metadata.get('brokerage', '증권사 미상')
        
        # 문서 내용과 출처를 결합
        doc_str = f"[참고 문서 {i+1}]\n- 출처: {brokerage} 리포트 '{title}' (발간일: {date}, 파일명: {source})\n- 내용:\n{doc.page_content}"
        formatted_docs.append(doc_str)
        
    return "\n\n====================\n\n".join(formatted_docs)

def main():
    reports_db_path = "./reports_chroma_db"
    if not os.path.exists(reports_db_path):
        print("❌ Chroma DB 폴더가 없습니다. 03번 코드를 먼저 실행해주세요.")
        return

    print("🧠 벡터 DB를 불러오는 중...")
    # 1. DB 및 임베딩 모델 로드 (3단계와 동일한 모델 사용 필수!)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(persist_directory=reports_db_path, embedding_function=embeddings, collection_name="financial_reports")
    
    # 2. Retriever (검색기) 설정
    # k=3 : 질문과 가장 유사한 상위 3개의 리포트 내용을 찾아오라는 뜻
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    # 3. LLM 설정 (매니저 에이전트의 뇌)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # 4. 프롬프트 엔지니어링 (할루시네이션 방지 핵심)
    prompt = PromptTemplate.from_template(
        """당신은 투자 포트폴리오를 관리하고 고객에게 브리핑하는 '매니저 에이전트'입니다.
        아래 제공된 [참고 문서]만을 근거로 사용자의 질문에 답변하세요.
        
        [지시사항]
        1. 참고 문서에 없는 내용은 절대 지어내지 말고, "제공된 리포트 내용에서는 해당 정보를 찾을 수 없습니다."라고 답변하세요.
        2. 답변 시 반드시 어떤 리포트(증권사명, 리포트 제목)를 참고했는지 자연스럽게 출처를 언급하세요.
        3. 전문가답지만 이해하기 쉬운 자연스러운 문투로 작성하세요.
        
        [참고 문서]
        {context}
        
        [사용자 질문]
        {question}
        
        답변:"""
    )

    # 5. LCEL (LangChain Expression Language) 체인 구성
    # 질문이 들어오면 -> retriever가 문서를 찾고 -> format_docs로 정리한 뒤 -> prompt에 넣고 -> LLM이 답변 생성
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    # 6. 실전 테스트 루프
    print("\n✅ 매니저 에이전트 준비 완료! 질문을 입력하세요. (종료하려면 'q' 또는 'quit' 입력)")
    print("-" * 50)
    
    while True:
        user_query = input("🧑‍💻 질문: ")
        if user_query.lower() in ['q', 'quit', 'exit']:
            print("👋 테스트를 종료합니다.")
            break
            
        if not user_query.strip():
            continue
            
        print("\n🤖 매니저 에이전트 답변 중 (리포트 검색 중...)...\n")
        
        try:
            # 💡 RAG 체인 실행!
            response = rag_chain.invoke(user_query)
            print(response)
        except Exception as e:
            print(f"❌ 에러 발생: {e}")
            
        print("\n" + "-" * 50)

if __name__ == "__main__":
    main()
# modules/data_exporter.py

import pandas as pd
from io import BytesIO
from datetime import datetime
import xlsxwriter # xlsxwriter 임포트 (Pandas의 to_excel 엔진으로 사용)
import re # 정규 표현식을 위해 추가

def export_articles_to_txt(articles_list: list[dict], file_prefix: str = "news_articles") -> str:
    """
    기사 목록을 텍스트 형식으로 변환합니다.
    Args:
        articles_list (list[dict]): 기사 데이터 목록.
        file_prefix (str): 파일 이름 접두사.
    Returns:
        str: 텍스트 파일 내용.
    """
    txt_data_lines = []
    for article in articles_list:
        txt_data_lines.append(f"제목: {article.get('제목', 'N/A')}")
        txt_data_lines.append(f"링크: {article.get('링크', 'N/A')}")
        txt_data_lines.append(f"날짜: {article.get('날짜', 'N/A')}")
        txt_data_lines.append(f"내용: {article.get('내용', 'N/A')}")
        if '수집_시간' in article: # 모든 수집 뉴스에만 있는 필드
            txt_data_lines.append(f"수집 시간: {article.get('수집_시간', 'N/A')}")
        txt_data_lines.append("-" * 50) # 구분선
    return "\n".join(txt_data_lines)

def export_articles_to_csv(articles_df: pd.DataFrame) -> BytesIO:
    """
    기사 DataFrame을 CSV 형식의 BytesIO 객체로 변환합니다.
    Args:
        articles_df (pd.DataFrame): 기사 데이터프레임.
    Returns:
        BytesIO: CSV 파일 내용이 담긴 BytesIO 객체.
    """
    output = BytesIO()
    # utf-8-sig는 엑셀에서 한글 깨짐 방지를 위해 BOM(Byte Order Mark)을 포함합니다.
    output.write(articles_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig'))
    output.seek(0)
    return output

def export_articles_to_excel(articles_df: pd.DataFrame, sheet_name: str = "Sheet1") -> BytesIO:
    """
    기사 DataFrame을 XLSX(Excel) 형식의 BytesIO 객체로 변환하고 스타일링을 적용합니다.
    Args:
        articles_df (pd.DataFrame): 기사 데이터프레임.
        sheet_name (str): 엑셀 시트 이름.
    Returns:
        BytesIO: XLSX 파일 내용이 담긴 BytesIO 객체.
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        articles_df.to_excel(writer, index=False, sheet_name=sheet_name)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # 헤더 포맷 정의
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'vcenter',
            'fg_color': '#D7E4BC', # 연한 녹색 배경
            'border': 1
        })

        # 데이터 행 포맷 (선택적: 홀수/짝수 행 배경색)
        even_row_format = workbook.add_format({'fg_color': '#F2F2F2', 'border': 1}) # 연한 회색
        odd_row_format = workbook.add_format({'border': 1}) # 기본 배경

        # 헤더 적용
        for col_num, value in enumerate(articles_df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # 열 너비 자동 조정 및 데이터 행 포맷 적용
        for col_num, col_name in enumerate(articles_df.columns):
            max_len = 0
            # 헤더 길이와 데이터 길이 중 최대값 계산
            max_len = max(max_len, len(str(col_name)))
            if not articles_df.empty:
                max_len = max(max_len, articles_df[col_name].astype(str).map(len).max())
            
            # 특정 열은 너비를 제한하거나 더 넓게 설정
            if col_name == '제목':
                worksheet.set_column(col_num, col_num, 50) # 제목 열은 고정 너비
            elif col_name == '내용':
                worksheet.set_column(col_num, col_num, 80) # 내용 열은 고정 너비
            elif col_name == '링크' or col_name == 'url': # 링크 열도 적절히
                worksheet.set_column(col_num, col_num, 40)
            else:
                worksheet.set_column(col_num, col_num, min(max_len + 2, 50)) # 최대 50으로 제한

            # 데이터 행 포맷 적용
            for row_num in range(len(articles_df)):
                cell_format = even_row_format if (row_num + 1) % 2 == 0 else odd_row_format
                for col_idx in range(len(articles_df.columns)):
                    worksheet.write(row_num + 1, col_idx, articles_df.iloc[row_num, col_idx], cell_format)


    output.seek(0)
    return output

def export_ai_report_to_excel(report_text: str, sheet_name: str = "AI Report") -> BytesIO:
    """
    AI가 생성한 마크다운 보고서 텍스트를 파싱하여 Excel 파일로 내보냅니다.
    각 섹션을 별도의 행으로 구성하고, 셀 크기를 조정합니다.
    """
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        # 수정된 부분: writer.sheets.add 대신 workbook.add_worksheet 사용
        worksheet = workbook.add_worksheet(sheet_name) # 새로운 시트 추가

        # 포맷 정의
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'text_wrap': True,
            'valign': 'vcenter',
            'align': 'center',
            'fg_color': '#FFC000', # 주황색 배경
            'border': 1
        })
        header_format = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'text_wrap': True,
            'valign': 'vcenter',
            'fg_color': '#D7E4BC', # 연한 녹색 배경
            'border': 1
        })
        content_format = workbook.add_format({
            'text_wrap': True,
            'valign': 'top',
            'border': 1
        })
        sub_header_format = workbook.add_format({
            'bold': True,
            'font_size': 11,
            'text_wrap': True,
            'valign': 'vcenter',
            'fg_color': '#EBF1DE', # 더 연한 녹색
            'border': 1
        })
        
        # 열 너비 설정
        worksheet.set_column('A:A', 30) # 섹션 제목 열
        worksheet.set_column('B:B', 100) # 내용 열

        row_idx = 0

        # 전체 보고서 제목 추출 및 작성
        overall_report_title_match = re.match(r'#\s*([^\n]+)', report_text)
        overall_report_title = ""
        if overall_report_title_match:
            overall_report_title = overall_report_title_match.group(1).strip()
            # 보고서 텍스트에서 전체 제목 줄 제거
            report_text = report_text[len(overall_report_title_match.group(0)):].strip()
        
        if overall_report_title:
            worksheet.merge_range(row_idx, 0, row_idx, 1, overall_report_title, title_format)
            row_idx += 2 # 제목 후 두 줄 공백

        # 주요 섹션(##)으로 보고서 텍스트 분할
        # 이 정규식은 분할하면서 "## 헤더"도 결과에 포함시킵니다.
        # 결과는 [첫 번째 헤더 이전 내용, ## 헤더1, 내용1, ## 헤더2, 내용2, ...] 형태가 됩니다.
        parts = re.split(r'(##\s*[^\n]+)', report_text)

        # 첫 번째 부분은 비어있거나 서론(예: "개요" 내용)을 포함할 수 있습니다.
        current_content = parts[0].strip()
        if current_content:
            # 보고서 구조상, 메인 제목 다음의 첫 번째 내용 블록은 "개요"입니다.
            worksheet.write(row_idx, 0, "개요", header_format)
            worksheet.write(row_idx, 1, current_content, content_format)
            row_idx += 2 # 섹션 후 한 줄 공백 추가

        # 나머지 부분(헤더와 해당 내용) 처리
        for i in range(1, len(parts), 2): # 헤더(홀수 인덱스부터 시작하여 두 칸씩 건너뛰기) 반복
            header_line = parts[i].strip()
            content_block = parts[i+1].strip() if (i+1) < len(parts) else ""

            main_section_title = header_line.replace("##", "").strip()
            
            # 주요 섹션 제목과 해당 내용(하위 헤더 이전) 작성
            worksheet.write(row_idx, 0, main_section_title, header_format)
            
            # 내용 블록을 하위 섹션(###)으로 분할
            sub_parts = re.split(r'(###\s*[^\n]+)', content_block)
            
            # sub_parts의 첫 번째 요소는 첫 번째 하위 헤더 이전의 내용입니다.
            initial_content_of_main_section = sub_parts[0].strip()
            if initial_content_of_main_section:
                worksheet.write(row_idx, 1, initial_content_of_main_section, content_format)
            else:
                worksheet.write(row_idx, 1, "", content_format) # 내용이 없어도 셀은 작성
            row_idx += 1 # 하위 섹션이 있거나 다음 주요 섹션으로 이동

            # 하위 섹션 처리
            for j in range(1, len(sub_parts), 2): # 하위 헤더 반복
                sub_header_line = sub_parts[j].strip()
                sub_content_block = sub_parts[j+1].strip() if (j+1) < len(sub_parts) else ""

                sub_section_title = sub_header_line.replace("###", "").strip()
                
                worksheet.write(row_idx, 0, f"  - {sub_section_title}", sub_header_format) # 하위 헤더 들여쓰기
                worksheet.write(row_idx, 1, sub_content_block, content_format)
                row_idx += 1
            
            row_idx += 1 # 각 주요 섹션(또는 마지막 하위 섹션) 후 한 줄 공백 추가하여 가독성 향상

    output.seek(0)
    return output

def generate_filename(prefix: str, extension: str) -> str:
    """
    현재 시간을 기반으로 파일 이름을 생성합니다.
    Args:
        prefix (str): 파일 이름 접두사.
        extension (str): 파일 확장자 (예: 'txt', 'csv', 'xlsx').
    Returns:
        str: 생성된 파일 이름.
    """
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"

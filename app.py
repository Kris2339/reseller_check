import streamlit as st
import pandas as pd
import io

# --- Helper Functions ---

def load_dataframe(file):
    """업로드된 파일을 읽어 Pandas DataFrame으로 변환합니다."""
    try:
        if file.name.endswith('.csv'):
            try:
                return pd.read_csv(file, encoding='cp949')
            except UnicodeDecodeError:
                file.seek(0)
                return pd.read_csv(file, encoding='utf-8')
        elif file.name.endswith(('.xls', '.xlsx')):
            return pd.read_excel(file)
    except Exception as e:
        st.error(f"'{file.name}' 파일 처리 중 오류 발생: {e}")
        return None
    return None

@st.cache_data
def convert_df_to_excel(df):
    """DataFrame을 엑셀 파일 형식의 Bytes로 변환합니다."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# --- Streamlit App Main Interface ---

st.set_page_config(page_title="리셀러 의심 주문 분석기", layout="wide")

# (수정) 앱 제목과 설명을 '주소' 기준 로직으로 변경
st.title("🕵️ 리셀러 의심 주문 분석기 (주소 비교 로직)")
st.markdown("""
이 앱은 **동일한 주문자**가 **다른 날짜**에 **다른 주소**로 보낸 주문 내역을 찾아냅니다.
- **주문자, 주문일, 주소** 컬럼명이 실제 파일과 다른 경우, 사이드바에서 직접 수정해주세요.
- **주문자** 정보가 비어있는 주문은 분석에서 자동으로 제외됩니다.
""")
st.markdown("---")

# --- Session State 초기화 ---
if 'merge_success' not in st.session_state:
    st.session_state.merge_success = False
if 'combined_df' not in st.session_state:
    st.session_state.combined_df = None

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ 분석 설정")
    st.info("파일의 실제 컬럼(열) 이름을 확인하고 필요시 수정해주세요.")
    
    # (수정) 컬럼 설정을 '주소'로 변경
    buyer_col = st.text_input("1. 주문자 이름 컬럼", value="주문자")
    date_col = st.text_input("2. 주문 날짜 컬럼", value="주문일")
    address_col = st.text_input("3. 주소 컬럼", value="주소") # '주소' 컬럼으로 변경

# --- 1. File Upload & Merge Section ---
st.subheader("단계 1: 파일 업로드 및 병합")
uploaded_files = st.file_uploader(
    "여기에 주문 파일을 드래그하거나 선택하세요.",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("✅ 병합 및 분석 준비하기", type="primary"):
        with st.spinner('파일을 검증하고 병합하는 중입니다...'):
            dataframes = []
            first_file_columns = None
            is_format_consistent = True

            for file in uploaded_files:
                df = load_dataframe(file)
                if df is not None:
                    if first_file_columns is None:
                        first_file_columns = df.columns.tolist()
                    if df.columns.tolist() != first_file_columns:
                        st.error(f"'{file.name}' 파일의 컬럼(열) 형식이 다른 파일과 다릅니다.")
                        is_format_consistent = False
                        break
                    dataframes.append(df)
            
            if is_format_consistent and dataframes:
                st.session_state.combined_df = pd.concat(dataframes, ignore_index=True)
                st.session_state.merge_success = True
                st.success(f"총 {len(uploaded_files)}개의 파일이 성공적으로 병합되었습니다.")
            else:
                st.session_state.merge_success = False

# --- 2. Analysis Section ---
if st.session_state.merge_success:
    st.markdown("---")
    st.subheader("단계 2: 리셀러 분석 실행")
    
    df_to_analyze = st.session_state.combined_df.copy()

    # (수정) 필수 컬럼 존재 여부 확인에 '주소' 컬럼 추가
    required_cols = [buyer_col, date_col, address_col]
    if not all(col in df_to_analyze.columns for col in required_cols):
        st.error(f"오류: 파일에서 필수 컬럼({', '.join(required_cols)})을 찾지 못했습니다. 사이드바에서 컬럼 이름을 확인해주세요.")
    else:
        if st.button("🚀 리셀러 분석 시작하기"):
            with st.spinner("데이터를 분석 중입니다..."):
                
                # 1. 주문자 정보가 비어있는 행(row)을 제거
                initial_rows = len(df_to_analyze)
                df_to_analyze.dropna(subset=[buyer_col], inplace=True)
                cleaned_rows = len(df_to_analyze)
                
                if initial_rows > cleaned_rows:
                    st.info(f"주문자 정보가 비어있는 **{initial_rows - cleaned_rows}개**의 주문을 분석에서 제외했습니다.")

                # 2. ⭐ '주소' 기준 핵심 분석 로직 ⭐
                # 주문자별로 그룹화하여, 각 주문자의 고유한 '주문일'과 '주소' 개수를 셉니다.
                grouped = df_to_analyze.groupby(buyer_col).agg(
                    unique_dates=(date_col, 'nunique'),
                    unique_addresses=(address_col, 'nunique') # '주소'의 고유값 개수를 셈
                )
                
                # '주문일'과 '주소'가 모두 1개를 초과하는 (즉, 2개 이상인) 주문자만 필터링합니다.
                suspicious_buyers = grouped[(grouped['unique_dates'] > 1) & (grouped['unique_addresses'] > 1)].index.tolist()

                if not suspicious_buyers:
                    # (수정) 결과 없음 메시지 변경
                    st.info("분석 결과: 동일한 주문자가 다른 날짜에 다른 주소로 보낸 내역을 찾지 못했습니다.")
                else:
                    st.success(f"총 {len(suspicious_buyers)}명의 의심 주문자를 찾았습니다!")
                    
                    # 원본 데이터에서 해당 주문자들의 모든 내역을 추출
                    result_df = df_to_analyze[df_to_analyze[buyer_col].isin(suspicious_buyers)].copy()
                    result_df.sort_values(by=[buyer_col, date_col], inplace=True)

                    st.markdown("##### 📊 분석 결과")
                    st.dataframe(result_df)

                    excel_data = convert_df_to_excel(result_df)
                    st.download_button(
                        label="📥 결과를 엑셀 파일로 다운로드",
                        data=excel_data,
                        # (수정) 다운로드 파일 이름 변경
                        file_name="suspicious_orders_by_address.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
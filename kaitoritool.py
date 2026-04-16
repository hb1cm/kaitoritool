import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime
import requests  # 新增：用于发送网络请求
from bs4 import BeautifulSoup  # 新增：用于解析网页内容

# --- 初始化 Supabase 连接 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="買取データ分析アシスタント", layout="wide")

def get_shouten_data(jan):
    """
    買取商店のサイトから直接データを取得する関数
    """
    search_url = "https://www.kaitorishouten-co.jp/products/list"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.kaitorishouten-co.jp/"
    }
    # 这里的 mode=search 是破解 404 的关键
    params = {"mode": "search", "name": jan}

    try:
        response = requests.get(search_url, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            products = soup.select(".product-item") # 查找商品块
            
            res_list = []
            for p in products:
                name = p.select_one(".name").get_text(strip=True) if p.select_one(".name") else "不明"
                # 尝试抓取价格标签
                price_tag = p.select_one(".price_val") or p.select_one(".price")
                price = price_tag.get_text(strip=True) if price_tag else "要相談"
                res_list.append({"ショップ": "買取商店", "商品名": name, "買取価格": price})
            return res_list
        return None
    except:
        return None

# --- 顶部导航栏设置 ---
# 修复点：左侧增加了 tab_compare，确保变量数量与右侧列表一致
tab_search, tab_compare, tab_upload = st.tabs([
    "🔍 販売詳細検索", 
    "💰 競合価格比較", 
    "📦 データアップロード"
])

# 1. 销售分析搜索 (默认页面)
with tab_search:
    st.header("🔍 販売詳細検索")
    
    # 1. 定义固定的店铺列表
    store_options = [
        "全ての店舗",
        "販売一丁目（楽天）",
        "販売一丁目【本店】",
        "販売一丁目 Amazon店",
        "販売一丁目 Yahoo！ショッピング店",
        "販売一丁目 Qoo10店",
        "ニューライフ",
        "販売一丁目 Wowma店"
    ]
    
    # --- 搜索过滤器布局 ---
    with st.expander("検索条件", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # --- 1. 这里是日语的快捷选项 ---
            date_presets = {
                "指定なし": None,
                "過去1週間": 7,
                "過去1ヶ月": 30,
                "過去3ヶ月": 90,
                "過去1年": 365
            }
            
            # 快捷下拉框
            selected_preset = st.selectbox("期間（プリセット）", options=list(date_presets.keys()))

            # 根据选择计算默认日期
            default_date = []
            if selected_preset != "指定なし":
                end_date = datetime.date.today()
                start_date = end_date - datetime.timedelta(days=date_presets[selected_preset])
                default_date = [start_date, end_date]

            # --- 2. 原本的日期选择器 ---
            date_range = st.date_input(
                "注文日時期間（手動）",
                value=default_date,
                help="開始日と終了日を選択してください"
            )
            
        with col2:
            # JAN / 商品码 搜索
            search_code = st.text_input("JANコード または 商品コード で検索")
            
        with col3:
            # 店铺筛选下拉框
            selected_store = st.selectbox("店舗フィルタ", store_options)

    if st.button("検索開始"):
        try:
            query = supabase.table("order").select("*")
            
            if search_code:
                query = query.or_(f'"JANコード".eq.{search_code},"商品コード".eq.{search_code}')
            
            if selected_store != "全ての店舗":
                query = query.eq("店舗名", selected_store)
                
            if len(date_range) == 2:
                start_date = date_range[0].strftime('%Y-%m-%d 00:00:00')
                end_date = date_range[1].strftime('%Y-%m-%d 23:59:59')
                query = query.gte("注文日時", start_date).lte("注文日時", end_date)
            
            res = query.execute()
            data = pd.DataFrame(res.data)

            if not data.empty:
                st.success(f"🎊 {len(data)} 件の注文データが見つかりました！")
                
                data['注文日時'] = pd.to_datetime(data['注文日時'])
                latest_item = data.sort_values(by='注文日時', ascending=False).iloc[0]
                
                st.info(f"**商品名：** {latest_item['商品名']}  \n**JANコード：** {latest_item['JANコード']}")
                
                # --- 📊 销售周期分析 ---
                st.write("### 📊 販売サイクル分析")
                tab_day, tab_month, tab_year = st.tabs(["📅 日次集計", "📅 月次集計", "📅 年次集計"])
                
                data_indexed = data.set_index('注文日時')
                
                # --- 1. 日次集計 ---
                with tab_day:
                    st.subheader("🗓️ 日次販売詳細")
                    day_res = data_indexed.resample('D').agg({'数量': 'sum', '単価': 'mean'}).reset_index()
                    day_res = day_res[day_res['数量'] > 0]
                    
                    col_table, _ = st.columns([2, 1])
                    with col_table:
                        day_table = day_res.rename(columns={'注文日時': '日付', '数量': '販売総数', '単価': '平均単価'})
                        day_table['日付'] = day_table['日付'].dt.strftime('%Y-%m-%d')
                        day_table['平均単価'] = day_table['平均単価'].map('¥{:,.0f}'.format)
                        day_table = day_table[['販売総数', '日付', '平均単価']]
                        st.dataframe(day_table, hide_index=True, use_container_width=True)
                    
                    st.write("📉 **日次トレンド**")
                    chart_day = day_res.copy()
                    chart_day['日付ラベル'] = chart_day['注文日時'].dt.strftime('%m-%d')
                    st.bar_chart(chart_day.set_index('日付ラベル')['数量'])

                # --- 2. 月次集計 ---
                with tab_month:
                    st.subheader("🗓️ 月次販売詳細")
                    month_res = data_indexed.resample('ME').agg({'数量': 'sum', '単価': 'mean'}).reset_index()
                    
                    col_table, _ = st.columns([2, 1])
                    with col_table:
                        month_table = month_res.rename(columns={'注文日時': '年月', '数量': '販売総数', '単価': '平均単価'})
                        month_table['年月'] = month_table['年月'].dt.strftime('%Y-%m')
                        month_table['平均単価'] = month_table['平均単価'].map('¥{:,.0f}'.format)
                        month_table = month_table[['販売総数', '年月', '平均単価']]
                        st.dataframe(month_table, hide_index=True, use_container_width=True)
                    
                    st.write("📉 **月次トレンド**")
                    chart_month = month_res.copy()
                    chart_month['年月ラベル'] = chart_month['注文日時'].dt.strftime('%Y-%m')
                    st.bar_chart(chart_month.set_index('年月ラベル')['数量'])

                # --- 3. 年次集計 ---
                with tab_year:
                    st.subheader("🗓️ 年次販売詳細")
                    year_res = data_indexed.resample('YE').agg({'数量': 'sum', '単価': 'mean'}).reset_index()
                    
                    col_table, _ = st.columns([2, 1])
                    with col_table:
                        year_table = year_res.rename(columns={'注文日時': '年度', '数量': '販売総数', '単価': '平均単価'})
                        year_table['年度'] = year_table['年度'].dt.strftime('%Y')
                        year_table['平均単価'] = year_table['平均単価'].map('¥{:,.0f}'.format)
                        year_table = year_table[['販売総数', '年度', '平均単価']]
                        st.dataframe(year_table, hide_index=True, use_container_width=True)
                    
                    st.write("📉 **年度トレンド**")
                    chart_year = year_res.copy()
                    chart_year['年度ラベル'] = chart_year['注文日時'].dt.strftime('%Y')
                    st.bar_chart(chart_year.set_index('年度ラベル')['数量'])
            
            else:
                st.warning("⚠️ 該当するデータが見つかりませんでした。検索条件を確認してください。")
                
        except Exception as e:
            st.error("🚨 検索中にエラーが発生しました。")
            st.code(str(e))

# --- 2. 💰 競合価格比較 (新分页) ---
with tab_compare:
    st.header("💰 競合価格リアルタイム比較")
    st.info("💡 JANコードを入力すると、自動で価格を取得し、他サイトへのリンクも生成します。")
    
    compare_jan = st.text_input("検索する JANコード を入力してください", placeholder="例: 4549995663167")
    
    if compare_jan:
        st.write(f"### 🎯 検索対象: `{compare_jan}`")
        
        # --- 🏮 買取商店の自動取得セクション ---
        with st.spinner('🏮 買取商店からデータを取得中...'):
            shouten_results = get_shouten_data(compare_jan)
            
        if shouten_results:
            st.subheader("🏮 買取商店 の最新買取価格")
            # 用 dataframe 展示抓取到的实时数据
            st.dataframe(pd.DataFrame(shouten_results), hide_index=True, use_container_width=True)
        else:
            st.warning("🏮 買取商店 の自動取得に失敗しました。以下のボタンで直接確認してください。")
            st.link_button("🏮 買取商店 で直接検索", f"https://www.kaitorishouten-co.jp/products/list?mode=search&name={compare_jan}")

        st.divider()
        
        # --- 🌐 他サイトへのクイックリンク ---
        st.write("### 🔗 他サイトの検索リンク")
        links = {
            "🌐 買取Wiki": f"https://gamekaitori.jp/search?type=&q={compare_jan}#searchtop",
            "📦 森森買取": f"https://www.mori-mori.jp/search/?keyword={compare_jan}",
            "📱 じゃんぱら": f"https://www.janpara.co.jp/buy/search/result/?KEYWORD={compare_jan}&ORDER=1",
            "💻 イオシス": f"https://k-tai-iosys.com/buy/search/result/?KEYWORD={compare_jan}",
            "📉 価格.com": f"https://kakaku.com/search_results/{compare_jan}/"
        }
        
        col_l, col_r = st.columns(2)
        for i, (site, url) in enumerate(links.items()):
            if i % 2 == 0:
                col_l.link_button(f"{site} で確認", url, use_container_width=True)
            else:
                col_r.link_button(f"{site} で確認", url, use_container_width=True)
                
        st.success("✅ 全てのリンクの生成が完了しました。")
    else:
        st.write("👆 上記のボックスに JANコード を入力してください。")

# --- 3. 📦 数据上传 ---
with tab_upload:
    st.header("📦 データアップロード")
    uploaded_file = st.file_uploader("CSVファイルを選択してください", type="csv")
    
    if uploaded_file is not None:
        column_types = {'管理番号': str, 'JANコード': str, '商品コード': str}
        
        df = None
        for enc in ['utf-8-sig', 'cp932', 'shift_jis', 'utf-8']:
            try:
                uploaded_file.seek(0) 
                df = pd.read_csv(uploaded_file, encoding=enc, dtype=column_types)
                break
            except:
                continue
        
        if df is None:
            st.error("🚨 CSVファイルの読み込みに失敗しました。文字コードを確認してください。")
            st.stop()
        
        df = df.fillna('')
        st.write("アップロードデータのプレビュー：", df.head())

        if st.button("🚀 データベースへ同期"):
            rows = df.to_dict('records')
            total_rows = len(rows)
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            batch_size = 50
            success = True
            
            for i in range(0, total_rows, batch_size):
                batch = rows[i : i + batch_size]
                try:
                    supabase.table("order").insert(batch).execute()
                    current_progress = min((i + batch_size) / total_rows, 1.0)
                    progress_bar.progress(current_progress)
                    status_text.text(f"同期中：{min(i + batch_size, total_rows)} / {total_rows} 件...")
                except Exception as e:
                    st.error(f"エラーが発生しました：{e}")
                    success = False
                    break
            
            if success:
                progress_bar.empty()
                status_text.text("✅ データの同期が完了しました！")
                st.balloons()
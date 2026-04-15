import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime

# --- 初始化 Supabase 连接 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="買取数据分析助手", layout="wide")

# --- 顶部导航栏设置 ---
# 把“销售分析搜索”放在第一个，它就会成为默认打开的页面
tab_search, tab_upload = st.tabs(["🔍 销售详情搜索", "📦 数据上传"])

# 1. 销售分析搜索 (默认页面)
with tab_search:
    st.header("🔍 销售详情搜索")
    
    # 1. 定义固定的店铺列表
    store_options = [
        "全部店铺",
        "販売一丁目（楽天）",
        "販売一丁目【本店】",
        "販売一丁目 Amazon店",
        "販売一丁目 Yahoo！ショッピング店",
        "販売一丁目 Qoo10店",
        "ニューライフ"
    ]
    
    # --- 搜索过滤器布局 ---
    with st.expander("筛选条件", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 日期区间选择（默认空）
            date_range = st.date_input("注文日時区间", value=[], help="请选择开始和结束日期")
            
        with col2:
            # JAN / 商品码 搜索
            search_code = st.text_input("搜索 JAN码 或 商品コード")
            
        with col3:
            # 店铺筛选下拉框
            selected_store = st.selectbox("筛选店铺", store_options)

    if st.button("开始搜索"):
        try:
            # 初始化查询（确认你的表名是不是叫 order）
            query = supabase.table("order").select("*")
            
            # --- 核心逻辑 1：JAN码 和 商品コード 双重搜索 ---
            # 💡 注意：日文列名在 or 查询中建议用双引号括起来
            if search_code:
                query = query.or_(f'"JANコード".eq.{search_code},"商品コード".eq.{search_code}')
            
            # --- 核心逻辑 2：店铺筛选 ---
            if selected_store != "全部店铺":
                query = query.eq("店舗名", selected_store)
                
            # --- 核心逻辑 3：日期区间筛选 ---
            if len(date_range) == 2:
                # 转换日期格式为字符串以便查询
                start_date = date_range[0].strftime('%Y-%m-%d 00:00:00')
                end_date = date_range[1].strftime('%Y-%m-%d 23:59:59')
                query = query.gte("注文日時", start_date).lte("注文日時", end_date)
            
            # 执行查询
            res = query.execute()
            data = pd.DataFrame(res.data)

            if not data.empty:
                st.success(f"🎊 成功找到 {len(data)} 条订单记录！")
                
                # 处理日期显示
                data['注文日時'] = pd.to_datetime(data['注文日時'])
                
                # 展示搜索出来的商品基本信息（取最新的一条作为代表）
                latest_item = data.sort_values(by='注文日時', ascending=False).iloc[0]
                st.info(f"**商品名：** {latest_item['商品名']}  \n**JAN码：** {latest_item['JANコード']}")
                
                # --- 数据可视化：每日销售趋势 ---
                data_for_chart = data.copy()
                data_for_chart['日期'] = data_for_chart['注文日時'].dt.date
                daily_trend = data_for_chart.groupby('日期')['数量'].sum().reset_index()
                
                st.subheader("📈 每日销售趋势")
                st.line_chart(daily_trend.set_index('日期'))
                
                # --- 分页汇总：周、月、年 ---
                st.write("### 📊 周期统计汇总")
                tab_week, tab_month, tab_year = st.tabs(["周汇总", "月汇总", "年汇总"])
                
                # 设置时间索引方便重采样
                data_indexed = data.set_index('注文日時')
                
                with tab_week:
                    week_res = data_indexed['数量'].resample('W').sum().reset_index()
                    st.table(week_res.rename(columns={'注文日時': '周截止日期', '数量': '销售总数'}))
                    
                with tab_month:
                    # 💡 核心修改：把 'M' 改成 'ME'
                    month_res = data_indexed['数量'].resample('ME').sum().reset_index()
                    # 为了表格好看，我们可以把日期只保留到月份
                    month_res['注文日時'] = month_res['注文日時'].dt.strftime('%Y-%m')
                    st.table(month_res.rename(columns={'注文日時': '月份', '数量': '销售总数'}))
                    
                with tab_year:
                    # 💡 核心修改：把 'A' 改成 'YE'
                    year_res = data_indexed['数量'].resample('YE').sum().reset_index()
                    # 为了表格好看，我们可以把日期只保留到年份
                    year_res['注文日時'] = year_res['注文日時'].dt.strftime('%Y')
                    st.table(year_res.rename(columns={'注文日時': '年份', '数量': '销售总数'}))
            
            else:
                st.warning("⚠️ 没找到匹配的订单，请检查筛选条件或 JAN 码是否正确。")
                
        except Exception as e:
            # 捕获并显示具体错误，方便咱们排查问题
            st.error("🚨 搜索出错啦！")
            st.code(str(e))

# 2. 数据上传
with tab_upload:
    st.header("📦 订单数据上传")
    uploaded_file = st.file_uploader("请选择原始 CSV 文件", type="csv")
    
    if uploaded_file is not None:
        # --- 核心修改 1：指定 dtype，保住前面的 0 ---
        # 我们把 管理番号、JANコード、商品コード 都强制设为字符串
        column_types = {
            '管理番号': str,
            'JANコード': str,
            '商品コード': str
        }
        
        try:
            # 读取时加入 dtype 参数
            df = pd.read_csv(uploaded_file, encoding='shift_jis', dtype=column_types)
        except:
            df = pd.read_csv(uploaded_file, encoding='utf-8', dtype=column_types)
        
        df = df.fillna('')
            
        st.write("预览上传的数据：", df.head())
        
        if st.button("🚀 一键同步到数据库"):
            # 准备数据
            # 这里的字段名要对应你 Supabase 表里的英文/中文列名
            # 如果你数据库是英文列名，记得在这里做一个映射映射 (rename)
            rows = df.to_dict('records')
            total_rows = len(rows)
            
            # --- 核心修改 2：添加进度条 ---
            progress_bar = st.progress(0) # 初始化进度条
            status_text = st.empty()      # 用来显示当前的进度文字
            
            # 分批上传（每批 50 条，避免请求太重导致报错）
            batch_size = 50
            success = True
            
            for i in range(0, total_rows, batch_size):
                batch = rows[i : i + batch_size]
                
                # 执行上传
                try:
                    # 替换为你的表名
                    supabase.table("order").insert(batch).execute()
                    
                    # 更新进度条
                    current_progress = min((i + batch_size) / total_rows, 1.0)
                    progress_bar.progress(current_progress)
                    status_text.text(f"正在上传：{min(i + batch_size, total_rows)} / {total_rows} 条数据...")
                    
                except Exception as e:
                    st.error(f"上传出错啦：{e}")
                    success = False
                    break
            
            if success:
                progress_bar.empty() # 完成后隐藏进度条
                status_text.text("✅ 所有数据已成功同步！")
                st.balloons() # 撒花庆祝一下！
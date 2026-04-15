import streamlit as st
import pandas as pd
from supabase import create_client, Client
import datetime

# --- 初始化 Supabase 连接 ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

st.set_page_config(page_title="買取数据分析助手", layout="wide")

# --- 侧边栏导航 ---
page = st.sidebar.radio("功能导航", ["数据上传", "销售分析搜索"])

# --- 分页1：数据上传 ---
if page == "数据上传":
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

# --- 分页2：销售分析搜索 ---
elif page == "销售分析搜索":
    st.header("🔍 销售详情搜索")
    
    # --- 搜索过滤器 ---
    with st.expander("筛选条件", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # 日期区间
            date_range = st.date_input("注文日時区间", value=[], help="默认空栏，请选择开始和结束日期")
            
        with col2:
            # JAN / 商品码 搜索
            search_code = st.text_input("搜索 JAN码 或 商品コード")
            
        with col3:
            # 店舗名筛选（动态从数据库获取列表）
            # 假设你已经从数据库取到了 unique_stores 列表
            stores = ["全部店铺", "新大久保店", "秋叶原店", "池袋店"] 
            selected_store = st.selectbox("筛选店铺", stores)

    if st.button("开始搜索"):
        # 1. 构造 Supabase 查询逻辑
        query = supabase.table("order").select("*")
        
        # 2. JAN/商品码 双重搜索 (OR 逻辑)
        if search_code:
            # 注意：Supabase 的 or 需要特殊写法
            query = query.or_(f"jan_code.eq.{search_code},product_code.eq.{search_code}")
        
        # 3. 日期筛选
        if len(date_range) == 2:
            query = query.gte("order_at", date_range[0]).lte("order_at", date_range[1])
            
        # 4. 店铺筛选
        if selected_store != "全部店铺":
            query = query.eq("store_name", selected_store)
            
        res = query.execute()
        data = pd.DataFrame(res.data)

        if not data.empty:
            # --- 处理“一个 JAN 对应多个商品名”的问题 ---
            # 逻辑：按 JAN 分组，取最新的商品名
            main_info = data.groupby('jan_code').agg({
                'product_name': lambda x: x.iloc[0], # 取第一个或最新的
                'quantity': 'sum',
                'order_at': 'count'
            }).reset_index()

            st.subheader(f"找到商品：{main_info['product_name'].iloc[0]} (JAN: {main_info['jan_code'].iloc[0]})")
            
            # --- 销售趋势（每天卖了几个） ---
            data['date'] = pd.to_datetime(data['order_at']).dt.date
            daily_sales = data.groupby('date')['quantity'].sum().reset_index()
            st.line_chart(daily_sales.set_index('date'))

            # --- 汇总按钮 ---
            st.write("### 汇总统计")
            tab_week, tab_month, tab_year = st.tabs(["周汇总", "月汇总", "年汇总"])
            
            with tab_week:
                # 使用 Pandas resample 处理
                st.write("本周销售汇总...")
            with tab_month:
                st.write("本月销售汇总...")
            with tab_year:
                st.write("本年销售汇总...")
        else:
            st.warning("没有找到匹配的数据哦，换个关键词试试？")
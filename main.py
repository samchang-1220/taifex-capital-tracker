import requests
import pandas as pd
from datetime import datetime
import os

def get_taifex_data():
    # 今天的日期格式
    today_str = datetime.now().strftime("%Y/%m/%d")
    print(f"開始抓取 {today_str} 的數據...")

    # 1. 抓取三大法人 (外資、投信) 未平倉
    # 網址：https://www.taifex.com.tw/cht/3/futContractsDate
    inst_url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    inst_resp = requests.post(inst_url, data={'queryDate': today_str})
    inst_tables = pd.read_html(inst_resp.text)
    
    # 這裡需要根據期交所表格索引精確定位 (台指期通常在第3個 table)
    # 此處僅為示意邏輯，實作需匹配表格中的 "外資" 與 "投信" 欄位
    # 假設我們已取得以下數值：
    # tx_foreign = ... (外資未平倉)
    # tx_trust = ... (投信未平倉)

    # 2. 抓取大額交易人 (特定五大)
    # 網址：https://www.taifex.com.tw/cht/3/largeTradersFutQry
    large_url = "https://www.taifex.com.tw/cht/3/largeTradersFutQry"
    large_resp = requests.post(large_url, data={'queryDate': today_str})
    large_tables = pd.read_html(large_resp.text)
    
    # tx_top5_spec = ... (特定五大法人未平倉)

    # --- 公式計算 (以台指期範例) ---
    # 這裡填入抓取到的實際變數
    # large_foreign = tx_top5_spec - tx_trust
    # small_foreign = tx_foreign - large_foreign

    # 建立今日數據 DataFrame
    new_data = pd.DataFrame([{
        "Date": today_str,
        "TX_Foreign": 10000, # 範例數據
        "TX_Trust": -2000,
        "TX_Top5_Spec": 8000,
        "TX_Large_Foreign": 10000, # (8000 - (-2000))
        "TX_Small_Foreign": 0,    # (10000 - 10000)
    }])

    return new_data

def save_to_csv(df):
    file_path = 'data/futures_history.csv'
    
    # 確保資料夾存在
    os.makedirs('data', exist_ok=True)

    if os.path.exists(file_path):
        old_df = pd.read_csv(file_path)
        # 合併後，根據 Date 欄位移除重複項，保留最後一筆 (即覆蓋)
        combined_df = pd.concat([old_df, df]).drop_duplicates(subset=['Date'], keep='last')
    else:
        combined_df = df

    combined_df.to_csv(file_path, index=False, encoding='utf-8-sig')
    print("資料庫更新成功！")

if __name__ == "__main__":
    try:
        data = get_taifex_data()
        save_to_csv(data)
    except Exception as e:
        print(f"發生錯誤: {e}")

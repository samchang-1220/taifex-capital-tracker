import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import io

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.taifex.com.tw/cht/3/futContractsDate'
}

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})
        print(f"TG Status: {r.status_code}")
    except: pass

def get_futures_data():
    check_date = datetime.now()
    found_data = False
    # 根據需求，縮短回溯天數為 6 天
    max_tries = 6 
    
    while not found_data and max_tries > 0:
        date_str = check_date.strftime("%Y/%m/%d")
        print(f"🔍 正在嘗試抓取日期: {date_str}...")
        
        try:
            # 1. 下載三大法人 CSV (三大法人未平倉量)
            inst_url = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
            r1 = requests.post(inst_url, data={'queryDate': date_str, 'commodityId': ''}, headers=HEADERS, timeout=10)
            
            # 2. 下載大額交易人 CSV
            large_url = "https://www.taifex.com.tw/cht/3/largeTradersFutDown"
            r2 = requests.post(large_url, data={'queryDate': date_str}, headers=HEADERS, timeout=10)

            # 強制將編碼轉為 cp950 (期交所常用的 Big5) 並檢查內容
            content1 = r1.content.decode('cp950', errors='ignore')
            content2 = r2.content.decode('cp950', errors='ignore')

            if "日期" in content1 and "商品名稱" in content1:
                df_inst = pd.read_csv(io.StringIO(content1))
                df_large = pd.read_csv(io.StringIO(content2))
                found_data = True
                print(f"✅ 成功找到 {date_str} 的數據！")
                break
        except Exception as e:
            print(f"抓取過程出錯: {e}")
        
        check_date -= timedelta(days=1)
        max_tries -= 1

    if not found_data:
        return None, None

    results = []
    # 標的代碼對應
    targets = [
        {"name": "台指期", "inst_code": "臺股期貨", "large_code": "臺股期貨"},
        {"name": "那指期", "inst_code": "美國那斯達克100期貨", "large_code": "美國那斯達克100"}
    ]

    for t in targets:
        try:
            # --- 三大法人資料提取 ---
            inst_sub = df_inst[df_inst['商品名稱'].str.strip() == t['inst_code']]
            # 外資未平倉淨額
            foreign_net = int(inst_sub[inst_sub['身份別'].str.contains("外資")]['未平倉持有工口數-淨額'].values[0])
            # 投信未平倉淨額
            trust_net = int(inst_sub[inst_sub['身份別'].str.contains("投信")]['未平倉持有工口數-淨額'].values[0])

            # --- 大額交易人資料提取 ---
            # 篩選特定標的 且 合約月份為所有月份
            large_sub = df_large[(df_large['商品名稱'].str.strip() == t['large_code']) & (df_large['合約月份'].str.strip() == '所有月份')]
            # 特定五大法人留倉 = (前五大特定買方 - 前五大特定賣方)
            # 在 CSV 中，特定買方在第 6 欄，特定賣方在第 8 欄 (Index 5, 7)
            top5_spec_buy = int(large_sub.iloc[0, 5])
            top5_spec_sell = int(large_sub.iloc[0, 7])
            top5_spec_net = top5_spec_buy - top5_spec_sell

            # --- 公式計算 ---
            # 1. 大外資 = 特定五大法人 - 投信
            big_f = top5_spec_net - trust_net
            # 2. 小外資 = 外資 - 大外資
            small_f = foreign_net - big_f
            
            results.append({
                "標的": t['name'],
                "外資": foreign_net,
                "大外資": big_f,
                "小外資": small_f,
                "預測": "🟢 偏多" if small_f > 0 else "🔴 偏空"
            })
        except Exception as e:
            print(f"⚠️ 解析 {t['name']} 失敗: {e}")

    return date_str, results

def main():
    date_str, data = get_futures_data()
    
    if not data:
        print("❌ 依然找不到資料。")
        send_tg_msg(f"❌ *系統錯誤*：回溯 6 天仍無法取得期交所 CSV。請確認官網連線狀況。")
        return

    # 存檔至 CSV (資料夾: data/)
    file_path = 'data/futures_history.csv'
    os.makedirs('data', exist_ok=True)
    df_new = pd.DataFrame(data)
    df_new['Date'] = date_str
    if os.path.exists(file_path):
        df_old = pd.read_csv(file_path)
        df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Date', '標的'], keep='last')
    else:
        df_final = df_new
    df_final.to_csv(file_path, index=False, encoding='utf-8-sig')

    # TG 訊息推送
    msg = f"📊 *每日小外資籌碼報告*\n📅 資料日期：{date_str}\n"
    msg += "---" + "\n"
    for item in data:
        msg += f"【{item['標的']}】\n"
        msg += f"▫️ 外資: {item['外資']:,}\n"
        msg += f"▫️ 大外資: {item['大外資']:,}\n"
        msg += f"▫️ *小外資: {item['小外資']:,}*\n"
        msg += f"💡 預測: {item['預測']}\n\n"
    send_tg_msg(msg)

if __name__ == "__main__":
    main()

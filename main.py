import requests
import pandas as pd
from datetime import datetime
import os

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("未設定 TG Token 或 Chat ID，跳過發送。")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def get_futures_data():
    today_str = datetime.now().strftime("%Y/%m/%d")
    print(f"執行時間: {today_str}")

    # 1. 抓取三大法人未平倉 (外資、投信)
    inst_url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    r1 = requests.post(inst_url, data={'queryDate': today_str})
    df_inst = pd.read_html(r1.text)[2] # 三大法人表格通常在 index 2
    
    # 2. 抓取大額交易人 (特定五大)
    large_url = "https://www.taifex.com.tw/cht/3/largeTradersFutQry"
    r2 = requests.post(large_url, data={'queryDate': today_str})
    df_large = pd.read_html(r2.text)[2] # 大額交易人表格

    results = []
    
    # 定義要抓取的標的與名稱對應
    targets = [
        {"name": "台指期", "code": "臺股期貨", "inst_idx": 0}, 
        {"name": "那指期", "code": "美國那斯達克100期貨", "inst_idx": None} 
    ]

    for target in targets:
        try:
            # A. 提取外資與投信 (未平倉淨額在第13欄與第10欄，需視期交所當下表格調整)
            # 這裡用標題搜尋定位更安全
            target_inst = df_inst[df_inst.iloc[:, 1].str.contains(target['code'], na=False)]
            foreign_net = int(target_inst.iloc[0, 13]) # 外資未平倉淨額
            trust_net = int(target_inst.iloc[1, 13])   # 投信未平倉淨額 (通常在下一列)

            # B. 提取特定五大 (前五大特定法人 多-空)
            target_large = df_large[df_large.iloc[:, 1].str.contains(target['code'], na=False)]
            # 這裡選取「所有月份」且為「前五大交易人」之「特定法人」的多空部隊
            top5_buy = int(target_large.iloc[0, 5])
            top5_sell = int(target_large.iloc[0, 6])
            top5_net = top5_buy - top5_sell

            # C. 公式計算
            big_foreign = top5_net - trust_net
            small_foreign = foreign_net - big_foreign
            
            signal = "🔴 偏空" if small_foreign < 0 else "🟢 偏多"

            results.append({
                "標的": target['name'],
                "外資": foreign_net,
                "大外資": big_foreign,
                "小外資": small_foreign,
                "預測": signal
            })
        except Exception as e:
            print(f"抓取 {target['name']} 失敗: {e}")

    return today_str, results

def main():
    date_str, data = get_futures_data()
    if not data: return

    # 存檔邏輯
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

    # TG 訊息組合
    msg = f"📊 *每日小外資籌碼報告* ({date_str})\n\n"
    for item in data:
        msg += f"【{item['標的']}】\n"
        msg += f"▫️ 外資留倉: {item['外資']}\n"
        msg += f"▫️ 大外資: {item['大外資']}\n"
        msg += f"▫️ *小外資: {item['小外資']}* \n"
        msg += f"💡 隔日預測: {item['預測']}\n\n"
    
    send_tg_msg(msg)

if __name__ == "__main__":
    main()

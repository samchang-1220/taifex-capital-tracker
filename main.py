import requests
import pandas as pd
from datetime import datetime
import os

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_api_data():
    try:
        # 1. 抓取三大法人 API
        inst_url = "https://openapi.taifex.com.tw/v1/FuturesThreeInstitutionalExchanges"
        r1 = requests.get(inst_url, timeout=20)
        
        # 2. 抓取大額交易人 API
        large_url = "https://openapi.taifex.com.tw/v1/DailyFuturesTradersRegion"
        r2 = requests.get(large_url, timeout=20)

        if r1.status_code == 200 and r2.status_code == 200:
            return r1.json(), r2.json()
        else:
            print(f"API 狀態異常: {r1.status_code}, {r2.status_code}")
            return None, None
    except Exception as e:
        print(f"連線 API 發生錯誤: {e}")
        return None, None

def process_data(inst_json, large_json):
    # 將資料轉為 DataFrame 方便篩選
    df_inst = pd.DataFrame(inst_json)
    df_large = pd.DataFrame(large_json)

    # 取得最新日期 (API 通常只給當天最新的資料)
    latest_date = df_inst['Date'].max()
    results = []

    # 標的對應 (API 中的名稱通常很準確)
    # t_code: 三大法人 API 名稱, l_code: 大額交易人 API 名稱
    targets = [
        {"name": "台指期", "t_code": "TX", "l_code": "TX"},
        {"name": "那指期", "t_code": "UNF", "l_code": "UNF"}
    ]

    for t in targets:
        try:
            # --- 三大法人 ---
            # 篩選對應標的之「外資」與「投信」未平倉淨額 (OpenInterestNetCount)
            # 身份別代碼: 外資 = 003, 投信 = 001
            f_net = int(df_inst[(df_inst['SymbolId'] == t['t_code']) & (df_inst['InstitutionalEntityId'] == '003')]['OpenInterestNetCount'].values[0])
            i_net = int(df_inst[(df_inst['SymbolId'] == t['t_code']) & (df_inst['InstitutionalEntityId'] == '001')]['OpenInterestNetCount'].values[0])

            # --- 大額交易人 ---
            # 篩選「所有月份 (All)」之「前五大特定法人」
            # 欄位：Top5SpecificLongCount (買), Top5SpecificShortCount (賣)
            l_row = df_large[(df_large['SymbolId'] == t['l_code']) & (df_large['ContractMonthOrWeek'] == 'All')].iloc[0]
            top5_spec_net = int(l_row['Top5SpecificLongCount']) - int(l_row['Top5SpecificShortCount'])

            # --- 公式計算 ---
            big_f = top5_spec_net - i_net
            small_f = f_net - big_f
            
            results.append({
                "標的": t['name'],
                "外資": f_net,
                "大外資": big_f,
                "小外資": small_f,
                "預測": "🟢 偏多" if small_f > 0 else "🔴 偏空"
            })
        except Exception as e:
            print(f"處理 {t['name']} 失敗: {e}")

    return latest_date, results

def main():
    inst_json, large_json = get_api_data()
    if not inst_json or not large_json:
        send_tg_msg("❌ API 抓取失敗：期交所 API 暫無回應或 GitHub IP 被封。")
        return

    date_str, data = process_data(inst_json, large_json)
    if not data: return

    # 存檔 (維持 CSV 歷史紀錄)
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

    # TG 推送
    msg = f"🚀 *小外資籌碼 API 報告*\n📅 資料日期：{date_str}\n"
    msg += "---" + "\n"
    for item in data:
        msg += f"【{item['標的']}】\n"
        msg += f"▫️ 大外資: {item['大外資']:,}\n"
        msg += f"▫️ *小外資: {item['小外資']:,}*\n"
        msg += f"💡 預測: {item['預測']}\n\n"
    send_tg_msg(msg)

if __name__ == "__main__":
    main()

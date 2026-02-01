import requests
import pandas as pd
from datetime import datetime
import os
import json

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def fetch_api_safely(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"❌ API 失敗碼: {r.status_code} URL: {url}")
            return None
        
        # 嘗試解析 JSON
        return r.json()
    except json.JSONDecodeError:
        print(f"❌ 解析失敗！收到的內容不是 JSON。內容開頭為: {r.text[:100]}")
        return None
    except Exception as e:
        print(f"❌ 連線異常: {e}")
        return None

def main():
    print("🚀 開始執行 API 抓取任務...")
    
    # 1. 抓取三大法人 API
    inst_data = fetch_api_safely("https://openapi.taifex.com.tw/v1/FuturesThreeInstitutionalExchanges")
    # 2. 抓取大額交易人 API
    large_data = fetch_api_safely("https://openapi.taifex.com.tw/v1/DailyFuturesTradersRegion")

    if not inst_data or not large_data:
        send_tg_msg("⚠️ *系統警告*：期交所 API 回傳格式錯誤或遭封鎖。請檢查 GitHub Actions Log。")
        return

    # 轉為 DataFrame
    df_inst = pd.DataFrame(inst_data)
    df_large = pd.DataFrame(large_data)
    
    # 取得最新日期
    latest_date = df_inst['Date'].max()
    results = []

    # 標的對應
    targets = [
        {"name": "台指期", "t_code": "TX", "l_code": "TX"},
        {"name": "那指期", "t_code": "UNF", "l_code": "UNF"}
    ]

    for t in targets:
        try:
            # --- 數據過濾 ---
            # 外資 = 003, 投信 = 001
            f_net = int(df_inst[(df_inst['SymbolId'] == t['t_code']) & (df_inst['InstitutionalEntityId'] == '003')]['OpenInterestNetCount'].values[0])
            i_net = int(df_inst[(df_inst['SymbolId'] == t['t_code']) & (df_inst['InstitutionalEntityId'] == '001')]['OpenInterestNetCount'].values[0])
            
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
            print(f"⚠️ {t['name']} 數據解析失敗: {e}")

    if results:
        # 存檔至 CSV
        file_path = 'data/futures_history.csv'
        os.makedirs('data', exist_ok=True)
        df_new = pd.DataFrame(results)
        df_new['Date'] = latest_date
        
        if os.path.exists(file_path):
            df_old = pd.read_csv(file_path)
            df_final = pd.concat([df_old, df_new]).drop_duplicates(subset=['Date', '標的'], keep='last')
        else:
            df_final = df_new
        df_final.to_csv(file_path, index=False, encoding='utf-8-sig')

        # TG 推送
        msg = f"🚀 *小外資籌碼預測報告*\n📅 資料日期：{latest_date}\n"
        msg += "---" + "\n"
        for item in results:
            msg += f"【{item['標的']}】\n"
            msg += f"▫️ 大外資: {item['大外資']:,}\n"
            msg += f"▫️ *小外資: {item['小外資']:,}*\n"
            msg += f"💡 預測: {item['預測']}\n\n"
        send_tg_msg(msg)
        print("✅ 任務圓滿完成！")

if __name__ == "__main__":
    main()

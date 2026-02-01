import requests
import pandas as pd
from datetime import datetime, timedelta
import os

# --- 設定區 ---
TG_TOKEN = os.getenv('TG_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')
# FinMind 官網註冊後可取得 Token (免費)，不填也能跑但有限次數
FINMIND_TOKEN = "" 

def send_tg_msg(message):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"})

def get_finmind_data(dataset, date):
    url = "https://api.finmindtrade.com/api/v4/data"
    parameter = {
        "dataset": dataset,
        "start_date": date,
        "token": FINMIND_TOKEN,
    }
    resp = requests.get(url, params=parameter)
    data = resp.json()
    if data['msg'] == 'success':
        return pd.DataFrame(data['data'])
    return pd.DataFrame()

def main():
    # 1. 尋找最近有開盤的日期 (回溯 6 天)
    check_date = datetime.now()
    found = False
    
    for i in range(6):
        target_date = (check_date - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"🔍 檢查 FinMind 資料日期: {target_date}")
        
        # 抓取三大法人
        df_inst = get_finmind_data("TaiwanFuturesInstitutionalEntity", target_date)
        # 抓取大額交易人
        df_large = get_finmind_data("TaiwanFuturesTradersRegion", target_date)
        
        if not df_inst.empty and not df_large.empty:
            found = True
            break
            
    if not found:
        send_tg_msg("❌ 系統錯誤：FinMind 暫時無法提供數據。")
        return

    results = []
    # 標的對應
    targets = [
        {"name": "台指期", "code": "TX"},
        {"name": "那指期", "code": "UNF"}
    ]

    for t in targets:
        try:
            # --- 三大法人資料 ---
            # 篩選特定標的 (TX 或 UNF)
            inst_sub = df_inst[df_inst['fut_id'] == t['code']]
            # 外資 (InstitutionalEntity: ForeignInv) 淨額
            f_net = int(inst_sub[inst_sub['institutional_entity'] == 'ForeignInv']['open_interest_net'].values[0])
            # 投信 (InstitutionalEntity: Trust) 淨額
            i_net = int(inst_sub[inst_sub['institutional_entity'] == 'Trust']['open_interest_net'].values[0])

            # --- 大額交易人資料 ---
            # 篩選標的 且 合約為 "all"
            large_sub = df_large[(df_large['fut_id'] == t['code']) & (df_large['contract_month'] == 'all')].iloc[0]
            # 特定五大法人留倉 = 特定五大買 - 特定五大賣
            spec_net = int(large_sub['top_five_specific_long_oi']) - int(large_sub['top_five_specific_short_oi'])

            # --- 公式計算 ---
            big_f = spec_net - i_net
            small_f = f_net - big_f
            
            results.append({
                "標的": t['name'],
                "外資": f_net,
                "大外資": big_f,
                "小外資": small_f,
                "預測": "🟢 偏多" if small_f > 0 else "🔴 偏空"
            })
        except Exception as e:
            print(f"⚠️ {t['name']} 解析失敗: {e}")

    # --- 存檔與推送 ---
    if results:
        # 存檔 CSV (略)
        msg = f"🚀 *小外資籌碼預測* (FinMind)\n📅 資料日期：{target_date}\n"
        msg += "---" + "\n"
        for item in results:
            msg += f"【{item['標的']}】\n▫️ 大外資: {item['大外資']:,}\n▫️ *小外資: {item['小外資']:,}*\n💡 預測: {item['預測']}\n\n"
        send_tg_msg(msg)
        print("✅ 任務圓滿完成！")

if __name__ == "__main__":
    main()

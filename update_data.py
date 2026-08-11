import os
import sys
import json
import re
import time
import requests
import io
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BINGO5_UPDATER")

PRIMARY_CSV_URL = 'https://loto-life.net/csv/bingo5'
BACKUP_JSON_URL = 'https://tk030-lotto.github.io/lotto-data-hub/data/bingo5.json'

def clean_val(val):
    if not isinstance(val, str):
        return val
    s = val.strip()
    match = re.search(r'="(.+?)"', s)
    if match:
        return match.group(1)
    return s.strip('"')

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(clean_val)

def fetch_from_primary():
    logger.info(f"Downloading CSV from primary source: {PRIMARY_CSV_URL}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    max_retries = 3
    retry_delay = 5
    response = None
    
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(PRIMARY_CSV_URL, headers=headers, timeout=15)
            response.raise_for_status()
            break
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            if attempt == max_retries:
                raise e
            logger.warning(f"Primary attempt {attempt} failed: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            
    csv_bytes = response.content
    decoded_text = None
    for enc in ('cp932', 'utf-8', 'utf-8-sig'):
        try:
            decoded_text = csv_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
            
    if not decoded_text:
        raise ValueError("Failed to decode CSV bytes for Bingo5")
        
    df = pd.read_csv(io.StringIO(decoded_text.strip()))
    df.columns = [clean_val(c) if isinstance(c, str) else c for c in df.columns]
    df = clean_data(df)
    
    parsed_history = []
    
    for _, row in df.iterrows():
        try:
            # 1列目: 回号
            round_no = int(row.iloc[0])
            # 2列目: 抽せん日
            date_str = str(row.iloc[1]).strip()
            # 3〜10列目: 当せん数字 8個
            numbers = []
            for col_idx in range(2, 10):
                num_val = int(row.iloc[col_idx])
                numbers.append(num_val)
                
            if len(numbers) != 8:
                continue
                
            parsed_history.append({
                "round": round_no,
                "date": date_str,
                "numbers": numbers
            })
        except Exception:
            continue
            
    parsed_history.sort(key=lambda x: x['round'], reverse=True)
    return parsed_history

def fetch_from_backup():
    logger.info(f"Downloading JSON from backup source (Lotto Data Hub): {BACKUP_JSON_URL}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    response = requests.get(BACKUP_JSON_URL, headers=headers, timeout=15)
    response.raise_for_status()
    data = response.json()
    
    parsed_history = []
    for item in data:
        parsed_history.append({
            "round": int(item["round"]),
            "date": str(item["date"]).strip(),
            "numbers": [int(n) for n in item["numbers"]]
        })
        
    parsed_history.sort(key=lambda x: x['round'], reverse=True)
    return parsed_history

def main():
    target_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bingo5_data.js")
    
    parsed_history = []
    try:
        parsed_history = fetch_from_primary()
        logger.info(f"Successfully fetched {len(parsed_history)} records from primary source.")
    except Exception as e:
        logger.warning(f"Primary source failed: {e}. Trying backup source...")
        try:
            parsed_history = fetch_from_backup()
            logger.info(f"Successfully fetched {len(parsed_history)} records from backup source.")
        except Exception as backup_e:
            logger.error(f"Backup source also failed: {backup_e}")
            sys.exit(1)
            
    if not parsed_history:
        logger.error("No Bingo5 data parsed.")
        sys.exit(1)
        
    try:
        js_content = f"""// ビンゴ5履歴データ（全件）
// 自動生成・同期機能用
const DEFAULT_BINGO5_DATA = {json.dumps(parsed_history, ensure_ascii=False, indent=2)};
"""
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(js_content)
        logger.info(f"Successfully updated bingo5_data.js. Latest round: {parsed_history[0]['round']} ({parsed_history[0]['date']})")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error writing to bingo5_data.js: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

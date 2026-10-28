import streamlit as st
import os
# アプリ起動時にPlaywrightのChromiumをインストール（クラウド環境対策）
@st.cache_resource
def install_playwright_browser():
    try:
        os.system("playwright install chromium")
    except Exception as e:
        print(f"Browser install failed: {e}")

# 起動時に実行
install_playwright_browser()

import datetime
from zoneinfo import ZoneInfo
import unicodedata
import re
import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser

# ==========================================
# 1. ページ設定とCSSカスタマイズ
# ==========================================
st.set_page_config(page_title="映画スケジュール＆時間割", layout="wide")

st.markdown(
    """
    <style>
    /* 時間割表のカラム幅調整 */
    .stColumn {
        min-width: 220px;
        max-width: 300px;
    }
    /* ヘッダーの作品タイトル（全文表示・折り返し許可） */
    .timeline-movie-title-full {
        font-weight: bold;
        font-size: 0.95rem;
        margin-bottom: 4px;
        word-wrap: break-word;
    }
    .theater-label {
        color: #666;
        font-size: 0.8rem;
        margin-bottom: 6px;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. サイト・劇場設定
# ==========================================
# 統合版の劇場設定
ALL_THEATERS = {
    "SMT": {
        "新宿ピカデリー": "shinjuku",
        "丸の内ピカデリー": "marunouchi",
        #"MOVIX亀有": "kameari",
        #"MOVIX昭島": "akishima",
        #"MOVIX橋本": "hashimoto",
        #"MOVIXつくば": "tsukuba",
        #"MOVIX宇都宮": "utsunomiya",
        #"MOVIX伊勢崎": "isesaki",
        "MOVIXさいたま": "saitama",
        "MOVIX川口": "kawaguchi",
        #"MOVIX柏の葉": "kashiwanoha",
    },
    "TOHO": {
        "TOHOシネマズ新宿": "076",
        "TOHOシネマズ上野": "080",
        "TOHOシネマズ日比谷": "081",
        "TOHOシネマズ池袋": "084",
        "TOHOシネマズ渋谷": "043",
        "TOHOシネマズ錦糸町（楽天地／オリナス）":"029",
        "TOHOシネマズシャンテ":"041",
    },
    "109": {
        "109シネマズ菖蒲": "shobu",
        #"109シネマズ二子玉川": "futakotamagawa",
        "109シネマズ川崎": "kawasaki",
        "109シネマズ木場": "kiba",
        "109シネマズ港北": "kohoku",
        "109シネマズ プレミアム新宿": "premiumshinjuku",
    },
    "CS": {
        "グランドシネマサンシャイン 池袋": "gdcs",
        #"シネマサンシャイン平和島": "heiwajima",
        #"シネマサンシャインユーカリが丘": "yukarigaoka",
        #"シネマサンシャイン土浦": "tsuchiura",
        #"シネマサンシャイン沼津": "numazu",
        #"シネマサンシャインららぽーと沼津": "lalaportnumazu",
        #"シネマサンシャイン大和郡山": "yamatokoriyama",
    },
    "KINEZO": {
        "新宿バルト9": "shinjuku_wald9",
        "T・ジョイPRINCE品川": "tjoy-prince-shinagawa",
        "T・ジョイSEIBU大泉": "t-joy_seibu_oizumi",
        "横浜ブルク13": "yokohama_burg13",
        "T・ジョイ横浜": "t-joy_yokohama",
        "こうのすシネマ": "kounosu-cinema",
    },
    "UC": {
        "United Cinemasアクアシティお台場": "odaiba",
        "United Cinemas豊洲": "toyosu",
        "Cineplex幸手": "satte",
        "United Cinemas幕張": "makuhari",
        "United Cinemas浦和": "urawa",
        "United Cinemas春日部": "kasukabe",
        "United Cinemasウニクス南古谷": "minamifuruya",
    },
    "AEON": {
        "イオンシネマ羽生": "hanyu",
        "イオンシネマ春日部": "kasukabe",
        #"イオンシネマむさし村山": "musashimurayama",
        #"イオンシネマシアタス調布": "chofu",
        #"イオンシネマ板橋": "itabashi",
        #"イオンシネマ浦和美園": "urawamisono",
        "イオンシネマ越谷レイクタウン": "koshigaya",
        "イオンシネマ幕張新都心": "makuhari",
    },
    "HUMAX": {
        "HUMAX池袋": "ikebukuro",
        "HUMAX渋谷": "shibuya",
    },
    "TTCG": {
        "テアトル新宿": "theatre_shinjuku",
        "ヒューマントラスト有楽町": "human_yurakucho",
        "ヒューマントラスト渋谷": "human_shibuya",
    },
    "TACHIKAWA": {
        "立川シネマシティ": "cinemacity",
    },
    "KORONA": {
        "小田原コロナシネマワールド": "odw",
    },
}

# UI表示用のフラットなリストを作成するヘルパー
def get_all_theater_names():
    names = []
    for chain, theaters in ALL_THEATERS.items():
        names.extend(theaters.keys())
    return names

# ==========================================
# 3. スクレイピング処理
# ==========================================
# ==========================================
# MOVIX用スクレイピング関数
# ==========================================
def fetch_smt_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    url = f"https://www.smt-cinema.com/site/{site_code}/index.html"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            
            page.wait_for_timeout(2000)

            today_str = datetime.date.today().strftime("%Y%m%d")

            if date_str != today_str:
                try:
                    selector = f"[id*='{date_str}'], [data-date*='{date_str}']"
                    date_element = page.wait_for_selector(
                        selector, timeout=3000
                    )

                    if date_element:
                        date_element.evaluate("el => el.click()")
                        page.wait_for_timeout(3000)
                    else:
                        browser.close()
                        return []
                except Exception:
                    browser.close()
                    return []

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        schedule_divs = soup.select("div.inner[id]")
        if schedule_divs:
            has_matching_date = any(
                date_str in div.get("id", "") for div in schedule_divs
            )
            if not has_matching_date:
                return []
        else:
            return []

        movie_blocks = soup.select("div.list")

        for block in movie_blocks:
            title_elem = block.select_one(".movieTitle h2")
            if not title_elem:
                continue

            en_label = title_elem.select_one("span.enLabel")
            if en_label:
                en_label.decompose()

            movie_title = title_elem.get_text(strip=True)

            schedule_blocks = block.select("div.block")
            for s_block in schedule_blocks:
                time_elem = s_block.select_one("p.time")
                if time_elem:
                    time_text = time_elem.get_text(strip=True)
                    if "～" in time_text:
                        start_time, end_time = time_text.split("～", 1)
                    else:
                        start_time = time_text
                        end_time = ""

                    start_time = (
                        start_time.zfill(5) if ":" in start_time else start_time
                    )
                    end_time = (
                        end_time.zfill(5) if ":" in end_time else end_time
                    )

                    schedules.append(
                        {
                            "劇場名": theater_name,
                            "作品名": movie_title,
                            "開始時間": start_time,
                            "終了時間": end_time,
                        }
                    )

#    except Exception:
#        return []

    except Exception as e:
    # エラーの詳細をそのまま画面に出力
        st.error(f"Playwrightエラー ({theater_name}): {str(e)}")
        return []

    return schedules

# ==========================================
# TOHOシネマズ用スクレイピング関数
# ==========================================

def fetch_toho_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    """TOHOシネマズの指定劇場・指定日付のスケジュールを取得する関数"""
    url = f"https://hlo.tohotheater.jp/net/schedule/{site_code}/TNPI2000J01.do"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,  # 運用時は True に変更可能
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
                permissions=[],
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(1000)

            # ▼▼▼ Cookie同意ポップアップ・バナーの非表示処理 ▼▼▼
            #try:
            #    page.evaluate("""
            #        () => {
            #            const banner = document.getElementById('onetrust-banner-sdk');
            #            if (banner) banner.style.display = 'none';
            #            const acceptBtn = document.getElementById('onetrust-accept-btn-handler');
            #            if (acceptBtn) acceptBtn.click();
            #        }
            #    """)
            #except Exception as e:
            #    print(f"Cookie Banner Handle Warning: {e}")

            # 本日以外の指定日の場合、日付タブをクリック
            today_str = datetime.date.today().strftime("%Y%m%d")
            if date_str != today_str:
                try:
                    # 数字で始まるIDに対応するため [id='YYYYMMDD'] 形式のセレクターを使用
                    date_selector = f"[id='{date_str}']"

                    # 1. 該当の日付タブ要素がDOMに出現・表示されるのを待機
                    date_element = page.wait_for_selector(
                        date_selector, state="visible", timeout=5000
                    )

                    if date_element:
                        # 2. Playwrightネイティブのクリックを実行
                        date_element.click()

                        # 3. タブが選択状態 (.is-selected) に変わるのを待機
                        page.wait_for_selector(
                            f"{date_selector}.is-selected", timeout=5000
                        )

                        # 4. スケジュール枠のコンテンツ描画を待機
                        page.wait_for_selector(
                            "div.schedule-body-section-item", timeout=5000
                        )
                        page.wait_for_timeout(1000)
                    else:
                        print(f"日付タブ要素が見つかりません: {date_str}")
                        browser.close()
                        return []

                except Exception as e:
                    print(f"TOHO Date Select Error ({date_str}): {e}")
                    browser.close()
                    return []

            html = page.content()
            browser.close()

        # ▼▼▼ BeautifulSoup によるHTML解析 ▼▼▼
        soup = BeautifulSoup(html, "html.parser")
        #作品ごとのブロックを取得
        movie_blocks = soup.select("div.schedule-body-section-item")
        for block in movie_blocks:
            #作品名を取得
            title_elem = block.select_one("h5.schedule-body-title")
            if not title_elem:
                continue
            movie_title = title_elem.get_text(strip=True)
            
            #スケジュール（時間）のブロックを取得
            schedule_items = block.select("div.schedule-item")
            for s_item in schedule_items:
                time_elem = s_item.select_one("p.time")
                if time_elem:
                    start_elem = time_elem.select_one("span.start")
                    end_elem = time_elem.select_one("span.end")

                    if start_elem and end_elem:
                        start_time = start_elem.get_text(strip=True)
                        end_time = end_elem.get_text(strip=True)

                        start_time = (
                            start_time.zfill(5)
                            if ":" in start_time
                            else start_time
                        )
                        end_time = (
                            end_time.zfill(5) if ":" in end_time else end_time
                        )

                        schedules.append(
                            {
                                "劇場名": theater_name,
                                "作品名": movie_title,
                                "開始時間": start_time,
                                "終了時間": end_time,
                            }
                        )

    except Exception as e:
        print(f"TOHO Scraping Error: {e}")
        return []

    return schedules

# ==========================================
# 109シネマズ用スクレイピング関数
# ==========================================
def fetch_109_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    url = f"https://109cinemas.net/{site_code}/"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(2000)

            today_str = datetime.date.today().strftime("%Y%m%d")
            if date_str != today_str:
                try:
                    selector = f"[data-date*='{date_str}'], [id*='{date_str}'], [href*='{date_str}']"
                    date_element = page.wait_for_selector(
                        selector, timeout=3000
                    )

                    if date_element:
                        date_element.click()
                        page.wait_for_timeout(3000)
                    else:
                        browser.close()
                        return []
                except Exception:
                    browser.close()
                    return []

            target_frame_html = ""
            try:
                page.wait_for_selector(
                    "iframe[src*='schedule'], iframe[src*='schedules']",
                    timeout=5000,
                )
                for frame in page.frames:
                    if (
                        "schedule" in frame.url
                        or "schedules" in frame.url
                    ):
                        target_frame_html = frame.content()
                        break
            except Exception:
                pass

            if not target_frame_html:
                target_frame_html = page.content()

            browser.close()

        soup = BeautifulSoup(target_frame_html, "html.parser")

        title_map = {}
        for opt in soup.select("option[value]"):
            val = opt.get("value", "").strip()
            text = opt.get_text(strip=True)
            if val and text:
                title_map[val] = text

        movie_blocks = soup.select("article")

        for block in movie_blocks:
            movie_title = ""
            title_elem = block.select_one("header h2")
            if title_elem:
                movie_title = title_elem.get_text(strip=True)

            art_id = block.get("id", "").strip()
            if not movie_title and art_id in title_map:
                movie_title = title_map[art_id]

            if not movie_title:
                continue

            time_items = block.select("ul.timetable li.check_date")
            if not time_items:
                time_items = block.select("ul.timetable li")

            for item in time_items:
                start_elem = item.select_one("time.start")
                end_elem = item.select_one("time.end")

                if start_elem and end_elem:
                    start_time = start_elem.get_text(strip=True)
                    end_time = end_elem.get_text(strip=True)

                    start_time = (
                        start_time.zfill(5) if ":" in start_time else start_time
                    )
                    end_time = (
                        end_time.zfill(5) if ":" in end_time else end_time
                    )

                    schedules.append(
                        {
                            "劇場名": theater_name,
                            "作品名": movie_title,
                            "開始時間": start_time,
                            "終了時間": end_time,
                        }
                    )

    except Exception as e:
        print(f"109 Scraping Error: {e}")
        return []

    return schedules

# ==========================================
# T-joy用スクレイピング関数
# ==========================================

def fetch_kinezo_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    url = f"https://tjoy.jp/{site_code}/"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(2000)

            #本日以外の指定日の場合、data-date="YYYY-MM-DD" を指定してクリック
            today_str = datetime.date.today().strftime("%Y%m%d")
            if date_str != today_str:
                try:
                    #YYYYMMDD -> YYYY-MM-DD (例: "20260917" -> "2026-09-17")
                    formatted_date = (
                        f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                    )
                    selector = f"a.calendar-item[data-date='{formatted_date}'], [data-date='{formatted_date}']"

                    date_element = page.wait_for_selector(
                        selector, timeout=5000
                    )

                    if date_element:
                        date_element.click()
                        page.wait_for_timeout(3000)
                    else:
                        browser.close()
                        return []
                except Exception:
                    browser.close()
                    return []

            html = page.content()
            browser.close()
            
        # ▼▼▼ BeautifulSoup によるHTML解析 ▼▼▼
        soup = BeautifulSoup(html, "html.parser")

        #各作品の親ブロック (.section-container) を取得
        movie_blocks = soup.select(".section-container")
        if not movie_blocks:
            movie_blocks = soup.select("section, div.film-item")

        for block in movie_blocks:
            #作品名の取得 (<h5 class="js-title-film">)
            title_elem = block.select_one(".js-title-film, h5")
            if not title_elem:
                continue
            movie_title = title_elem.get_text(strip=True)

            #上映時刻の取得 (<p class="schedule-time">)
            time_elems = block.select(".schedule-time")

            for time_elem in time_elems:
                time_text = time_elem.get_text(strip=True)  # 例: "13:50～ 16:55"

                if "～" in time_text or "~" in time_text:
                    sep = "～" if "～" in time_text else "~"
                    parts = time_text.split(sep, 1)
                    if len(parts) == 2:
                        start_time = parts[0].strip().zfill(5)
                        end_time = parts[1].strip().zfill(5)

                        schedules.append(
                            {
                                "劇場名": theater_name,
                                "作品名": movie_title,
                                "開始時間": start_time,
                                "終了時間": end_time,
                            }
                        )

    except Exception as e:
        print(f"KINEZO Scraping Error: {e}")
        return []

    return schedules
    
# ==========================================
# シネプレックス用スクレイピング関数
# ==========================================

def fetch_uc_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    # YYYYMMDD -> YYYY-MM-DD に変換 (例: "20260917" -> "2026-09-17")
    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    # 日付別直接アクセスURL
    url = f"https://www.unitedcinemas.jp/{site_code}/daily.php?date={formatted_date}"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # 作品ごとのブロック (li.clearfix) を取得
        movie_blocks = soup.select("li.clearfix")

        for block in movie_blocks:
            # 作品名の取得 (<span class="movieTitle"> <a>)
            title_elem = block.select_one("span.movieTitle a")
            if not title_elem:
                continue
            movie_title = title_elem.get_text(strip=True)

            # 上映時間ブロックの取得
            time_blocks = block.select("ul.tl ol")

            for time_block in time_blocks:
                start_elem = time_block.select_one("li.startTime")
                end_elem = time_block.select_one("li.endTime")

                if start_elem and end_elem:
                    start_time = start_elem.get_text(strip=True).zfill(5)

                    # "～12:21" から "～" を除去
                    end_text = end_elem.get_text(strip=True)
                    end_time = (
                        end_text.replace("～", "")
                        .replace("~", "")
                        .strip()
                        .zfill(5)
                    )

                    schedules.append(
                        {
                            "劇場名": theater_name,
                            "作品名": movie_title,
                            "開始時間": start_time,
                            "終了時間": end_time,
                        }
                    )

    except Exception as e:
        print(f"UC Scraping Error: {e}")
        return []

    return schedules
    
# ==========================================
# シネマサンシャイン用スクレイピング関数
# ==========================================

def fetch_cs_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    url = f"https://www.cinemasunshine.co.jp/theater/{site_code}/"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(2000)

            today_str = datetime.date.today().strftime("%Y%m%d")
            if date_str != today_str:
                try:
                    target_md = f"{date_str[4:6]}/{date_str[6:8]}"

                    date_item = page.locator(
                        ".schedule-swiper__item, .day-wrap"
                    ).filter(has_text=target_md).first

                    if date_item.count() > 0:
                        date_item.click()
                        page.wait_for_timeout(3000)
                    else:
                        browser.close()
                        return []
                except Exception:
                    browser.close()
                    return []

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # HTML構造に基づく作品ブロックの取得（.content-item を最優先に指定）
        movie_blocks = soup.select(
            ".content-item, .schedule-movie, .movie-block"
        )
        if not movie_blocks:
            movie_blocks = soup.select("div[class*='schedule']")

        for block in movie_blocks:
            # 作品タイトルの抽出（.item-title の配下にある .title を指定）
            title_elem = block.select_one(".item-title .title, .title")
            if not title_elem:
                continue

            movie_title = title_elem.get_text(strip=True)

            # スケジュールアイテム（.schedule-item）を抽出
            items = block.select(".schedule-item")
            for item in items:
                time_elem = item.select_one(".time")
                if not time_elem:
                    continue

                # テキストを取得し、余分な空白や改行を除去
                time_text = time_elem.get_text(strip=True)
                time_text = time_text.replace("\n", "").replace(" ", "").replace(" ", "")

                if "〜" in time_text:
                    parts = time_text.split("〜", 1)
                    start_time = parts[0].strip().zfill(5)
                    end_time = parts[1].strip().zfill(5)

                    entry = {
                        "劇場名": theater_name,
                        "作品名": movie_title,
                        "開始時間": start_time,
                        "終了時間": end_time,
                    }
                    if entry not in schedules:
                        schedules.append(entry)

    except Exception as e:
        print(f"CS Scraping Error: {e}")
        return []

    return schedules

# ==========================================
# イオンシネマ用スクレイピング関数
# ==========================================

def fetch_aeon_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    # イオンシネマの日付指定直接URL（例: https://theater.aeoncinema.com/theaters/hanyu/?date=20260918）
    url = f"https://theater.aeoncinema.com/theaters/{site_code}/?date={date_str}"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(2000)
            
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")

        # 作品ブロック (.p-schedule__information) を取得
        info_blocks = soup.select(".p-schedule__information")

        for block in info_blocks:
            # 作品名 (<a class="p-schedule__titleJp"> 内の <h2>)
            title_elem = block.select_one(".p-schedule__titleJp h2")
            if not title_elem:
                continue
            movie_title = title_elem.get_text(strip=True)

            # 各上映枠 (.p-schedule__ticket) を取得
            tickets = block.select(".p-schedule__ticket")

            for ticket in tickets:
                time_elem = ticket.select_one(".p-schedule__time")
                if not time_elem:
                    continue

                start_elem = time_elem.select_one("span")
                end_elem = time_elem.select_one("small")

                if start_elem and end_elem:
                    start_time = start_elem.get_text(strip=True).zfill(5)

                    # "~17:10" や "〜17:10" から記号を除去
                    end_text = end_elem.get_text(strip=True)
                    end_time = (
                        end_text.replace("~", "")
                        .replace("〜", "")
                        .strip()
                        .zfill(5)
                    )
                    schedules.append(
                        {
                            "劇場名": theater_name,
                            "作品名": movie_title,
                            "開始時間": start_time,
                            "終了時間": end_time,
                        }
                    )
    except Exception as e:
        print(f"Aeon Scraping Error: {e}")
        return []

    return schedules

# ==========================================
# HUMAXシネマズ用スクレイピング関数
# ==========================================

def fetch_humax_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    """HUMAXシネマズの指定劇場・指定日付の上映スケジュールを取得する関数"""
    
    clean_date = date_str.replace("-", "").replace("/", "")
    if len(clean_date) == 8:
        date_dash = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:]}"
    else:
        return []

    url = f"https://www.humax-cinema.co.jp/{site_code}/"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,  # 画面非表示（処理速度向上）
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(1000)

            # 日付切り替え処理
            today_dash = datetime.date.today().strftime("%Y-%m-%d")
            if date_dash != today_dash:
                try:
                    tab_selectors = [
                        f"[data-date='{date_dash}']",
                        f"[data-date='{clean_date}']",
                        f"a[href*='{date_dash}']",
                        f"a[href*='{clean_date}']"
                    ]
                    
                    clicked = False
                    for sel in tab_selectors:
                        elem = page.query_selector(sel)
                        if elem and elem.is_visible():
                            elem.click()
                            page.wait_for_timeout(2000)
                            clicked = True
                            break
                            
                    # タブが見つからなかった場合は直接URL遷移によるフォールバック
                    if not clicked:
                        direct_url = f"https://www.humax-cinema.co.jp/{site_code}/schedule/?date={clean_date}"
                        page.goto(direct_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(2000)

                except Exception:
                    pass

            # 目的の日付枠の描画を待機
            target_container_selector = f"div.schedule-content[data-schedule-date='{date_dash}']"
            try:
                page.wait_for_selector(target_container_selector, timeout=5000)
            except Exception:
                browser.close()
                return []

            html = page.content()
            browser.close()

        # BeautifulSoup による解析
        soup = BeautifulSoup(html, "html.parser")
        target_container = soup.select_one(target_container_selector)
        if not target_container:
            return []

        movie_blocks = target_container.select("li.schedule-movie-item")
        
        for block in movie_blocks:
            title_elem = block.select_one("h3.schedule-movie-information-title")
            if not title_elem:
                continue
            movie_title = title_elem.get_text(strip=True)

            showtime_items = block.select("li.schedule-showtime-item")
            for s_item in showtime_items:
                time_elem = s_item.select_one("span.schedule-showtime-time")
                if time_elem:
                    time_text = time_elem.get_text(strip=True)
                    times = re.findall(r"\d{1,2}:\d{2}", time_text)
                    if len(times) >= 2:
                        start_time = times[0].zfill(5)
                        end_time = times[1].zfill(5)

                        schedules.append(
                            {
                                "劇場名": theater_name,
                                "作品名": movie_title,
                                "開始時間": start_time,
                                "終了時間": end_time,
                            }
                        )

    except Exception:
        return []

    return schedules

# ==========================================
# テアトルシネマ用スクレイピング関数
# ==========================================

def fetch_ttcg_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    """テアトルシネマグループの指定劇場・指定日付の上映スケジュールを取得する関数"""
    
    clean_date = date_str.replace("-", "").replace("/", "")
    if len(clean_date) != 8:
        return []

    # 検索用に月と日を数値化して文字列へ（例: "09" -> "9", "28" -> "28"）
    target_month = str(int(clean_date[4:6]))
    target_day = str(int(clean_date[6:8]))

    url = f"https://ttcg.jp/{site_code}/"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,  # 画面非表示
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass
            
            # JavaScriptによるスケジュール要素全体がDOMに描画されるのを待機
            try:
                page.wait_for_selector(".schedule-week-box", timeout=5000)
                page.wait_for_selector(".schedule-nowShowing", timeout=5000)
            except Exception:
                browser.close()
                return []

            # クリック切り替えは行わず、全日程が含まれた状態のHTMLを取得
            html = page.content()
            browser.close()

        # ▼▼▼ BeautifulSoup による解析（インデックス同期） ▼▼▼
        soup = BeautifulSoup(html, "html.parser")
        
        # 1. <div class="schedule-week"> の中から指定日付が何番目にあるかを特定
        target_index = -1
        week_boxes = soup.select(".schedule-week-box")
        for i, box in enumerate(week_boxes):
            day_elem = box.select_one("p.schedule-day")
            if not day_elem:
                continue
            
            b_elem = day_elem.select_one("b")
            if not b_elem:
                continue
                
            day_text = b_elem.get_text(strip=True)
            full_text = day_elem.get_text(strip=True)
            
            # テキスト（例: "9/28[月]"）に月と日が合致するかチェック
            if day_text == target_day and f"{target_month}/" in full_text:
                target_index = i
                break
                
        # 画面上の日付リストに存在しない場合（公開前など）は終了
        if target_index == -1:
            return []
            
        # 2. 全日程のスケジュールコンテナを取得し、該当インデックスのものを抽出対象にする
        now_showing_containers = soup.select(".schedule-nowShowing")
        if target_index >= len(now_showing_containers):
            return []
            
        target_container = now_showing_containers[target_index]
        
        # 3. 対象コンテナ内から作品と時間を抽出
        movie_blocks = target_container.select(".schedule-nowShowing-box")

        for block in movie_blocks:
            title_elem = block.select_one(".schedule-nowShowing-title h4 a")
            if not title_elem:
                continue
            
            # 不要な <span> 要素 (初日や終映未定など) を削除してタイトルのみ取得
            for span in title_elem.find_all("span"):
                span.extract()
                
            movie_title = title_elem.get_text(strip=True)

            # 上映時間の取得
            time_divs = block.select(".schedule-nowShowing-screening ul li div.time")
            for t_div in time_divs:
                time_text = t_div.get_text(separator=" ", strip=True)
                
                times = re.findall(r"\b(\d{1,2}:\d{2})\b", time_text)
                if len(times) >= 1:
                    start_time = times[0].zfill(5)
                    end_time = times[1].zfill(5) if len(times) >= 2 else ""

                    schedules.append({
                        "劇場名": theater_name,
                        "作品名": movie_title,
                        "開始時間": start_time,
                        "終了時間": end_time,
                    })

        # 重複排除処理
        unique_schedules = []
        seen = set()
        for s in schedules:
            identifier = (s["作品名"], s["開始時間"], s["終了時間"])
            if identifier not in seen:
                seen.add(identifier)
                unique_schedules.append(s)

        schedules = unique_schedules

    except Exception:
        return []

    return schedules

# ==========================================
# 立川シネマシティ用スクレイピング関数
# ==========================================

def fetch_cinemacity_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    """立川シネマシティの指定日付の上映スケジュールを取得する関数

    :param theater_slug: 予備パラメータ (任意の文字列で可)
    :param theater_name: 劇場名 (例: '立川シネマシティ')
    :param date_str: 日付文字列 (例: '20260929' または '2026-09-29')
    :return: スケジュール情報のリスト [{"劇場名": ..., "作品名": ..., "開始時間": ..., "終了時間": ...}]
    """
    
    clean_date = date_str.replace("-", "").replace("/", "")
    if len(clean_date) != 8:
        return []

    # 正しいスケジュールURLのフォーマット
    url = f"https://res.cinemacity.co.jp/TicketReserver/schedule/{clean_date}"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,  # 運用向け・画面非表示
                #channel="chrome",
                args=["--ignore-certificate-errors"],
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            # スケジュールテーブルの読み込み待機
            try:
                page.wait_for_selector(".time-table, span.schedule-movie-title", timeout=5000)
            except Exception:
                pass

            html = page.content()
            browser.close()

        # ▼▼▼ BeautifulSoup による解析 ▼▼▼
        soup = BeautifulSoup(html, "html.parser")

        # 作品ごとのテーブル（または .time-table）を取得
        time_tables = soup.select(".time-table")
        if not time_tables:
            # フォールバック: 直接 table を全取得
            time_tables = [soup]

        for container in time_tables:
            # 1つの .time-table 内にある各作品ブロック（内側の table）を走査
            movie_tables = container.select("table") if container.name != "table" else [container]

            for m_table in movie_tables:
                # 作品タイトルの取得
                title_elem = m_table.select_one("span.schedule-movie-title a, span.schedule-movie-title")
                if not title_elem:
                    continue
                movie_title = title_elem.get_text(strip=True)

                # 上映時間の取得 (tdbg1 などの時間セルを走査)
                time_cells = m_table.select("td.tdbg1, td")
                for cell in time_cells:
                    start_elem = cell.select_one("span.start-time")
                    end_elem = cell.select_one("span.end-time")

                    if start_elem and end_elem:
                        start_raw = start_elem.get_text(strip=True)
                        end_raw = end_elem.get_text(strip=True)

                        # 空セルを除外
                        if not start_raw:
                            continue

                        # 正規表現で "HH:MM" 形式のみをクリーンに抽出
                        start_match = re.search(r"\d{1,2}:\d{2}", start_raw)
                        end_match = re.search(r"\d{1,2}:\d{2}", end_raw)

                        if start_match:
                            start_time = start_match.group(0).zfill(5)
                            end_time = end_match.group(0).zfill(5) if end_match else ""

                            schedules.append(
                                {
                                    "劇場名": theater_name,
                                    "作品名": movie_title,
                                    "開始時間": start_time,
                                    "終了時間": end_time,
                                }
                            )

        # 重複排除処理
        unique_schedules = []
        seen = set()
        for s in schedules:
            identifier = (s["作品名"], s["開始時間"], s["終了時間"])
            if identifier not in seen:
                seen.add(identifier)
                unique_schedules.append(s)

        schedules = unique_schedules

    except Exception:
        return []

    return schedules

# ==========================================
# コロナシネマワールド用スクレイピング関数
# ==========================================

def fetch_korona_schedule(
    site_code: str, theater_name: str, date_str: str
) -> list[dict]:
    """コロナシネマワールドの指定劇場・指定日付の上映スケジュールを取得する関数

    :param theater_slug: 劇場スラッグ (例: 'odw' は小田原劇場)
    :param theater_name: 劇場名 (例: '小田原コロナシネマワールド')
    :param date_str: 日付文字列 (例: '20260929' または '2026-09-29')
    :return: スケジュール情報のリスト [{"劇場名": ..., "作品名": ..., "開始時間": ..., "終了時間": ...}]
    """

    clean_date = date_str.replace("-", "").replace("/", "")
    if len(clean_date) != 8:
        return []

    # 検索・比較用の月日文字列 (例: "09/29")
    target_mm_dd = f"{clean_date[4:6]}/{clean_date[6:8]}"

    url = f"https://cinema.korona.co.jp/theaters/{site_code}/"
    schedules = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,  # 運用向け・画面非表示
                #channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled", # 自動化検出の無効化
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ],
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(2000)
            # page.wait_for_timeout(10000)

            # ポップアップ等の消去（存在する場合）
            try:
                for sel in [".close", ".modal-close", "button.c-modal__close"]:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(500)
            except Exception:
                pass

            # ▼▼▼ 日付選択処理 ▼▼▼
            try:
                # 対象の日付要素を探してクリック
                clicked = page.evaluate(
                    f"""
                    () => {{
                        const targetDay = '{target_mm_dd}';
                        const items = document.querySelectorAll('.schedule-swiper__item');
                        for (let item of items) {{
                            const daySpan = item.querySelector('span.day');
                            if (daySpan && daySpan.textContent.trim() === targetDay) {{
                                item.click();
                                return true;
                            }}
                        }}
                        return false;
                    }}
                """
                )

                if clicked:
                    # クリックした日付要素に active クラスが付くのを待機
                    page.wait_for_function(
                        f"""
                        () => {{
                            const targetDay = '{target_mm_dd}';
                            const activeItem = document.querySelector('.schedule-swiper__item.active');
                            if (!activeItem) return false;
                            const daySpan = activeItem.querySelector('span.day');
                            return daySpan && daySpan.textContent.trim() === targetDay;
                        }}
                    """,
                        timeout=5000,
                    )
                    page.wait_for_timeout(1500)
                else:
                    # 対象の日付がスライダー内にない場合（範囲外等）
                    browser.close()
                    return []
            except Exception:
                pass

            html = page.content()
            browser.close()

        # ▼▼▼ BeautifulSoup による解析 ▼▼▼
        soup = BeautifulSoup(html, "html.parser")

        # 作品ごとのブロック要素を取得
        content_items = soup.select(".content-item")

        for item in content_items:
            # 作品タイトルの取得
            title_elem = item.select_one(".item-title a.title")
            if not title_elem:
                continue
            movie_title = title_elem.get_text(strip=True)

            # 各上映枠（時間要素）を取得
            schedule_items = item.select(".schedule-item")
            for s_item in schedule_items:
                time_div = s_item.select_one(".time")
                if not time_div:
                    continue

                time_text = time_div.get_text(strip=True)

                # "09:35〜11:30" や "09:35 11:30" から時間表記を正規表現で抽出
                times = re.findall(r"\b(\d{1,2}:\d{2})\b", time_text)
                if len(times) >= 1:
                    start_time = times[0].zfill(5)
                    end_time = times[1].zfill(5) if len(times) >= 2 else ""

                    schedules.append(
                        {
                            "劇場名": theater_name,
                            "作品名": movie_title,
                            "開始時間": start_time,
                            "終了時間": end_time,
                        }
                    )

        # 重複排除処理
        unique_schedules = []
        seen = set()
        for s in schedules:
            identifier = (s["作品名"], s["開始時間"], s["終了時間"])
            if identifier not in seen:
                seen.add(identifier)
                unique_schedules.append(s)

        schedules = unique_schedules

    #except Exception:
    #    return []
    except Exception as e:
    # エラーの詳細をそのまま画面に出力
        st.error(f"Playwrightエラー ({theater_name}): {str(e)}")
        return []

    return schedules

# ==========================================
# 4. ヘルパー関数（時間割表生成・重複判定）
# ==========================================
def time_to_minutes(time_str: str) -> int | None:
    if not time_str or ":" not in time_str:
        return None
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        return None


def assign_virtual_screens(schedules: list[dict]) -> list[dict]:
    """
    同一劇場・同一作品で上映時間が重複している場合、
    別の列（仮想的なスクリーン枠）に割り当てる処理
    """
    df = pd.DataFrame(schedules)
    if df.empty:
        return []

    enhanced = []
    for (title, theater), group in df.groupby(["作品名", "劇場名"]):
        group = group.sort_values("開始時間")
        tracks = []  # 各枠の終了時間（分）を記録

        for _, row in group.iterrows():
            s_min = time_to_minutes(row["開始時間"])
            e_min = time_to_minutes(row["終了時間"])
            if s_min is None or e_min is None:
                continue

            placed_track = -1
            for i, track_end in enumerate(tracks):
                if track_end <= s_min:
                    placed_track = i
                    tracks[i] = e_min
                    break

            if placed_track == -1:
                placed_track = len(tracks)
                tracks.append(e_min)

            new_row = row.to_dict()
            new_row["列番"] = placed_track + 1
            enhanced.append(new_row)

    return enhanced


def generate_timeline_matrix(schedules: list[dict]) -> pd.DataFrame:
    if not schedules:
        return pd.DataFrame()

    # 07:00 ～ 29:00 まで5分単位のタイムライン作成
    start_grid_min = 7 * 60
    end_grid_min = 29 * 60
    time_slots = []

    for m in range(start_grid_min, end_grid_min, 5):
        h = m // 60
        mins = m % 60
        time_slots.append(f"{h:02d}:{mins:02d}")

    df_raw = pd.DataFrame(schedules)
    unique_items = (
        df_raw[["作品名", "劇場名", "列番"]].drop_duplicates().to_dict("records")
    )

    matrix_data = {t: [] for t in time_slots}
    columns = []

    for item in unique_items:
        col_name = f"{item['作品名']}_{item['劇場名']}_{item['列番']}"
        columns.append(col_name)

        sub_df = df_raw[
            (df_raw["作品名"] == item["作品名"])
            & (df_raw["劇場名"] == item["劇場名"])
            & (df_raw["列番"] == item["列番"])
        ]

        for t_str in time_slots:
            slot_min = time_to_minutes(t_str)
            slot_end = slot_min + 5
            symbol = ""

            for _, row in sub_df.iterrows():
                s_min = time_to_minutes(row["開始時間"])
                e_min = time_to_minutes(row["終了時間"])

                if s_min is None or e_min is None:
                    continue
                
                # スロット（5分単位）内に時刻が含まれるかで判定
                if slot_min <= s_min < slot_end:
                    symbol = "上映開始"
                    break
                elif slot_min <= e_min < slot_end:
                    symbol = "上映終了"
                    break
                elif s_min < slot_min and slot_min < e_min:
                    symbol = "｜"
                    break

            matrix_data[t_str].append(symbol)

    res_df = pd.DataFrame(matrix_data, index=columns).T
    return res_df


@st.dialog("作品・劇場詳細")
def show_detail_dialog(movie_title: str, theater_name: str):
    st.markdown(f"### {movie_title}")
    st.markdown(f"**劇場:** {theater_name}")


# ==========================================
# 5. メイン UI
# ==========================================
def main():
    st.title("🎬 映画スケジュール & 時間割ビューア")

    # セッション状態の初期化
    if "schedules" not in st.session_state:
        st.session_state.schedules = []
    if "timeline_targets" not in st.session_state:
        st.session_state.timeline_targets = []

# ----------------------------------------------------
    # 【ステップ1】 メイン画面：日付選択および劇場選択・スケジュール取得
    # ----------------------------------------------------
    st.subheader("📅 【ステップ1】 鑑賞日と劇場の選択")

    # メイン画面で日付を選択
    jst = ZoneInfo("Asia/Tokyo")
    today = datetime.datetime.now(jst).date()
    target_date = st.date_input(
        "鑑賞したい日付を選択してください",
        value=today,
        min_value=today,
        max_value=today + datetime.timedelta(days=7),
        help="上映スケジュールを取得する日付を指定します。"
    )
    date_str = target_date.strftime("%Y%m%d")

    st.markdown("##### 🎬 劇場の選択")
    st.caption("スケジュールを取得したい劇場にチェックを入れてください。（チェーン名の横の『＋ / －』で折りたたむことができます）")

    # チェーンキー（辞書のキー）に対応する日本語表示名
    CHAIN_LABEL_MAP = {
        "SMT": "松竹マルチプレックスシアターズ（ピカデリー・MOVIX）",
        "TOHO": "TOHOシネマズ",
        "109": "109シネマズ",
        "CS": "シネマサンシャイン",
        "KINEZO": "T-joy（KINEZO）",
        "UC": "UNITED CINEMAS",
        "AEON": "イオンシネマ",
        "HUMAX": "HUMAXシネマ",
        "TTCG": "テアトルシネマグループ",
        "TACHIKAWA": "立川シネマシティ",
        "KORONA": "コロナシネマワールド"
    }

    # ==========================================
    # 全選択・全解除のための Session State 初期化 & コールバック定義
    # ==========================================
    if "chk_all_theaters" not in st.session_state:
        st.session_state.chk_all_theaters = False

    for chain_key, theaters_dict in ALL_THEATERS.items():
        if f"chk_chain_all_{chain_key}" not in st.session_state:
            st.session_state[f"chk_chain_all_{chain_key}"] = False
        for t_name in theaters_dict.keys():
            if f"select_theater_{t_name}" not in st.session_state:
                st.session_state[f"select_theater_{t_name}"] = False

    # 1. 最上段「すべての劇場を選択」のコールバック
    def on_change_all_theaters():
        val = st.session_state.chk_all_theaters
        for chain_key, theaters_dict in ALL_THEATERS.items():
            st.session_state[f"chk_chain_all_{chain_key}"] = val
            for t_name in theaters_dict.keys():
                st.session_state[f"select_theater_{t_name}"] = val

    # 2. 各チェーン「すべての劇場を選択」のコールバック
    def on_change_chain(c_key):
        val = st.session_state[f"chk_chain_all_{c_key}"]
        for t_name in ALL_THEATERS[c_key].keys():
            st.session_state[f"select_theater_{t_name}"] = val
        
        # 全体全選択のチェック状態を更新
        all_selected = all(
            st.session_state.get(f"select_theater_{t}", False)
            for c in ALL_THEATERS.values() for t in c.keys()
        )
        st.session_state.chk_all_theaters = all_selected

    # 3. 個別劇場のコールバック
    def on_change_theater(c_key):
        # チェーン内が全てONか判定
        chain_selected = all(
            st.session_state.get(f"select_theater_{t}", False)
            for t in ALL_THEATERS[c_key].keys()
        )
        st.session_state[f"chk_chain_all_{c_key}"] = chain_selected

        # 全体が全てONか判定
        all_selected = all(
            st.session_state.get(f"select_theater_{t}", False)
            for c in ALL_THEATERS.values() for t in c.keys()
        )
        st.session_state.chk_all_theaters = all_selected

    # 最上段：全劇場を一括選択・解除するチェックボックス
    st.checkbox(
        "🌐 取得可能なすべての劇場を選択する",
        key="chk_all_theaters",
        on_change=on_change_all_theaters
    )
    st.divider()

    selected_theater_names = []

    # ALL_THEATERS 辞書の構造に基づいてチェーンごとの expander を動的に作成
    for chain_key, theaters_dict in ALL_THEATERS.items():
        chain_label = CHAIN_LABEL_MAP.get(chain_key, chain_key)
        theater_list = list(theaters_dict.keys())

        with st.expander(f"🏢 {chain_label} （{len(theater_list)} 劇場）", expanded=False):
            # チェーン内の全選択チェックボックス
            st.checkbox(
                f"✅ {chain_label} のすべての劇場を選択",
                key=f"chk_chain_all_{chain_key}",
                on_change=on_change_chain,
                args=(chain_key,)
            )
            st.markdown("---")

            cols = st.columns(3)
            for idx, t_name in enumerate(theater_list):
                col = cols[idx % 3]
                is_checked = col.checkbox(
                    t_name,
                    key=f"select_theater_{t_name}",
                    on_change=on_change_theater,
                    args=(chain_key,)
                )
                if is_checked:
                    selected_theater_names.append(t_name)

    # 選択状況の案内文表示
    if selected_theater_names:
        st.success(f"✅ **選択中の劇場 ({len(selected_theater_names)}件):** " + " / ".join(selected_theater_names))
    else:
        st.info("ℹ️ 上映スケジュールを取得する劇場を少なくとも1つ選択してください。")

    # スケジュール取得ボタン
    btn_fetch = st.button(
        "🔍 スケジュールを取得する",
        type="primary",
        width="stretch",
        disabled=len(selected_theater_names) == 0
    )

    if btn_fetch:
        if not selected_theater_names:
            st.warning("劇場を1つ以上選択してください。")
        else:
            with st.spinner(f"{target_date.strftime('%Y年%m月%d日')} のスケジュール情報を取得中..."):
                all_schedules = []
                for t_name in selected_theater_names:
                    if t_name in ALL_THEATERS.get("SMT", {}):
                        site_code = ALL_THEATERS["SMT"][t_name]
                        res = fetch_smt_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("TOHO", {}):
                        site_code = ALL_THEATERS["TOHO"][t_name]
                        res = fetch_toho_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("109", {}):
                        site_code = ALL_THEATERS["109"][t_name]
                        res = fetch_109_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("CS", {}):
                        site_code = ALL_THEATERS["CS"][t_name]
                        res = fetch_cs_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("KINEZO", {}):
                        site_code = ALL_THEATERS["KINEZO"][t_name]
                        res = fetch_kinezo_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("UC", {}):
                        site_code = ALL_THEATERS["UC"][t_name]
                        res = fetch_uc_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("AEON", {}):
                        site_code = ALL_THEATERS["AEON"][t_name]
                        res = fetch_aeon_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("HUMAX", {}):
                        site_code = ALL_THEATERS["HUMAX"][t_name]
                        res = fetch_humax_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("TTCG", {}):
                        site_code = ALL_THEATERS["TTCG"][t_name]
                        res = fetch_ttcg_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("TACHIKAWA", {}):
                        site_code = ALL_THEATERS["TACHIKAWA"][t_name]
                        res = fetch_cinemacity_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)
                    elif t_name in ALL_THEATERS.get("KORONA", {}):
                        site_code = ALL_THEATERS["KORONA"][t_name]
                        res = fetch_korona_schedule(site_code, t_name, date_str)
                        all_schedules.extend(res)

                # データリセットと Session State への保存
                st.session_state.schedules = all_schedules
                st.session_state.timeline_targets = []

                # 前回の作品選択用チェックボックス状態等を初期化（劇場選択用キーは除外）
                for key in list(st.session_state.keys()):
                    if key.startswith("chk_") and not key.startswith("chk_all_theaters") and not key.startswith("chk_chain_all_"):
                        del st.session_state[key]

                if not all_schedules:
                    st.error(
                        "指定された日付のスケジュールはまだ公開されていないか、休館日等の理由で取得できませんでした。別の日付をお試しください。"
                    )
                else:
                    st.success(f"🎉 全 {len(all_schedules)} 件の上映スケジュールを取得しました！")

    # ----------------------------------------------------
    # 【ステップ2】 メイン画面：フィルター＆作品選択
    # ----------------------------------------------------
    if st.session_state.schedules:
        df_all = pd.DataFrame(st.session_state.schedules)
        unique_pairs = (
            df_all[["作品名", "劇場名"]].drop_duplicates().to_dict("records")
        )

        st.subheader("【ステップ2】 表示する作品を選択（フィルター）")
        st.caption(
            "一覧から時間割表に表示したい作品にチェックを入れてください。（作品名は全文表示されています）"
        )

        search_keyword = st.text_input("🔍 作品名キーワード検索")

        # 検索キーワードで一覧を絞り込み
        filtered_pairs = [
            p
            for p in unique_pairs
            if not search_keyword
            or search_keyword.lower() in p["作品名"].lower()
        ]

        # 一括操作ボタン
        col_s1, col_s2, _ = st.columns([1, 1, 4])
        if col_s1.button("検索結果をすべて選択"):
            for p in filtered_pairs:
                st.session_state[f"chk_{p['作品名']}___{p['劇場名']}"] = True
            st.rerun()

        if col_s2.button("検索結果をすべて解除"):
            for p in filtered_pairs:
                st.session_state[f"chk_{p['作品名']}___{p['劇場名']}"] = False
            st.rerun()

        # チェックボックス一覧表示（1列・全文表示）
        st.markdown(
            "<div style='margin-top: 10px; margin-bottom: 20px;'>",
            unsafe_allow_html=True,
        )
        for pair in filtered_pairs:
            chk_key = f"chk_{pair['作品名']}___{pair['劇場名']}"
            if chk_key not in st.session_state:
                st.session_state[chk_key] = False

            label = f"【{pair['劇場名']}】 {pair['作品名']}"
            st.checkbox(label, key=chk_key)
        st.markdown("</div>", unsafe_allow_html=True)

        # ----------------------------------------------------
        # 【ステップ3】 時間割表の表示実行
        # ----------------------------------------------------
        st.divider()

        col_btn_center, _ = st.columns([3, 4])
        with col_btn_center:
            if st.button(
                "🌟 チェックした作品で時間割表を表示する",
                type="primary",
                width='stretch',
            ):
                # チェックが入っている項目を抽出して保存
                st.session_state.timeline_targets = [
                    f"{p['作品名']}___{p['劇場名']}"
                    for p in unique_pairs
                    if st.session_state.get(
                        f"chk_{p['作品名']}___{p['劇場名']}", False
                    )
                ]

        # --- 時間割表（タイムライン）描画エリア ---
        if not st.session_state.timeline_targets:
            st.info(
                "【ステップ2】で作品を選択し、「時間割表を表示する」ボタンを押すとここに表が表示されます。"
            )
        else:
            st.subheader("📅 時間割表（タイムライン）")

            active_schedules_raw = []
            for pair_key in st.session_state.timeline_targets:
                title, theater = pair_key.split("___")
                sub_schedules = df_all[
                    (df_all["作品名"] == title) & (df_all["劇場名"] == theater)
                ].to_dict("records")
                active_schedules_raw.extend(sub_schedules)
            
            # --- 【改修】重複上映を判定し、別列（仮想スクリーン）に割り当てる ---
            active_schedules = assign_virtual_screens(active_schedules_raw)

            active_pairs = (
                pd.DataFrame(active_schedules)[["作品名", "劇場名", "列番"]]
                .drop_duplicates()
                .to_dict("records")
            )

            # 同一劇場・同一作品で列（枠）が複数あるかカウント
            track_counts = {}
            for p in active_pairs:
                key = (p["作品名"], p["劇場名"])
                track_counts[key] = track_counts.get(key, 0) + 1

            # カラムヘッダー（全文表示）
            cols = st.columns(len(active_pairs))
            for idx, pair in enumerate(active_pairs):
                with cols[idx]:
                    title = pair["作品名"]
                    theater = pair["劇場名"]
                    t_num = pair["列番"]

                    # 複数列ある場合は [枠1] などを付与してスクリーンを区別
                    display_title = title
                    if track_counts[(title, theater)] > 1:
                        display_title += f" [枠{t_num}]"

                    st.markdown(
                        f"""
                        <div style="border:1px solid #ddd; padding:8px; border-radius:5px; background-color:#f9f9f9;">
                            <div class="timeline-movie-title-full">{display_title}</div>
                            <div class="theater-label">📍 {theater}</div>
                        </div>
                    """,
                        unsafe_allow_html=True,
                    )

                    if st.button("詳細", key=f"btn_detail_{idx}"):
                        show_detail_dialog(display_title, theater)

            st.caption(
                "※ セルの「上映開始」「｜」（上映中）、「上映終了」はそれぞれ時刻の状況を示しています。"
            )

            # タイムライン行列の出力
            timeline_df = generate_timeline_matrix(active_schedules)

            # 表のカラム名も全文表示（省略せず指定）
            display_df = timeline_df.copy()
            display_df.columns = [
                f"{p['作品名']} [枠{p['列番']}] ({p['劇場名']})" if track_counts[(p["作品名"], p["劇場名"])] > 1 
                else f"{p['作品名']} ({p['劇場名']})"
                for p in active_pairs
            ]

            st.dataframe(display_df, width='stretch', height=500)

            # ==========================================
            # ヘルパー関数: 作品名と言語(字幕/吹替)によるグループ化
            # ==========================================
            def get_movie_group_key(title_str: str, include_format: bool = False) -> str:
                """
                上映タイトルから上映形態や上映時間表記、言語表記（字幕/吹替/(字)/(吹)等）を除去し、
                「作品名 (字幕 or 吹替)」のグループキーを生成する。
                """
                if not title_str:
                    return ""

                # 1. 全角英数字・記号の正規化 (ＩＭＡＸ -> IMAX, （字） -> (字) 等)
                norm = unicodedata.normalize('NFKC', title_str)

                # 2. 言語判定（"字幕", "字幕版", "(字)" / "吹替", "吹替版", "(吹)" に対応）
                # NFKC正規化により全角の（字）・（吹）も半角の(字)・(吹)として一括判定できます
                if any(k in norm for k in ["字幕", "(字)"]):
                    lang = "字幕"
                elif any(k in norm for k in ["吹替", "(吹)"]):
                    lang = "吹替"
                else:
                    lang = "通常"

                # 3. 特殊上映形態キーワード（長い名称を優先して判定）
                format_keywords = [
                    "IMAXレーザー","IMAXレーザーGT","ULTRA","DolbyCinema","Dolby Cinema","Dolby Vision",
                    "GT Technology","轟音上映","IMAX","MX4D","4DX","ScreenX","DC",
                    "Dolby","轟音","レーザー","BESTIA","enhanced","TCX","3D","2D","ODS",
                    "Dolby-ATMOS","極音","Atmos","極音02","PG12","/ PG12","SCREENX with",
                    "インフィニティビジョン","INFINITY VISION","極爆","<",">","＜","＞","『","』"
                ]

                # 特殊上映形態の検出（include_format=True の場合に使用）
                found_format = None
                if include_format:
                    for fmt in format_keywords:
                        if re.search(re.escape(fmt), norm, flags=re.IGNORECASE):
                            found_format = fmt
                            break

                # 4. 上映時間表記の除去（例: "(本編:172分)", "【本編：97分】", "(101分)" 等）
                cleaned = re.sub(r'[\(\[\{<（【〔＜]?\s*本編\s*[:：]?\s*\d+\s*分\s*[\)\]\}＞）】〕]?', '', norm, flags=re.IGNORECASE)
                cleaned = re.sub(r'[\(\[\{<（【〔＜]\s*\d+\s*分\s*[\)\]\}＞）】〕]', '', cleaned, flags=re.IGNORECASE)

                # 5. 上映形態・言語キーワード・(字)/(吹) タグの除去
                remove_keywords = format_keywords + [
                    "字幕版", "吹替版", "字幕", "吹替", "(字)", "(吹)"
                ]
                remove_keywords.sort(key=len, reverse=True)
                for kw in remove_keywords:
                    cleaned = re.sub(re.escape(kw), "", cleaned, flags=re.IGNORECASE)

                # 6. 中身が空になった括弧、または中に記号・スペースしか残っていない括弧の除去
                cleaned = re.sub(r'[\(\[\{<（【〔＜]\s*[・･\-\:：\s]*\s*[\)\]\}＞）】〕]', '', cleaned)

                # 7. 先頭・末尾に残った不要な記号（【】[]()・ : スラッシュ スペース等）の削除
                cleaned = re.sub(r'^[\(\)\[\]\{\}【】〔〕＜＞・･\-\:：;；/／\\｜\|\s]+|[\(\)\[\]\{\}【】〔〕＜＞・･\-\:：;；/／\\｜\|\s]+$', '', cleaned)

                # 8. 連続する余白の整形
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()

                # 万が一すべて消えてしまった場合は元のタイトルを採用
                if not cleaned:
                    cleaned = title_str.strip()

                # 9. グループ名の構築
                group_str = f"{cleaned}（{lang}）" if lang != "通常" else cleaned

                if include_format and found_format:
                    group_str += f"［{found_format}］"

                return group_str

            # ==========================================
            # 【ステップ4】 複数作品の鑑賞ルート検索
            # ==========================================
            st.divider()
            st.subheader("🚂 複数作品の鑑賞ルート検索")
            st.caption("時間割表に表示されている作品をグループ化し、被りなく巡回できる最適な鑑賞ルートを検索します。")
            
            # --- UI: 特殊上映形態によるグループ分け選択（チェックボックス） ---
            split_by_format = st.checkbox(
                "特殊上映形態（IMAX, 4DX, 轟音上映, Dolby Cinema/Atmos等）を分けて検索する",
                value=False,
                help="チェックを入れると、同じ作品・同じ言語でも「IMAX版」と「通常版」などを別作品（別グループ）として扱い、それぞれ1回ずつ鑑賞するルートを検索します。"
            )

            # アクティブなスケジュールを動的にグループ化
            grouped_schedules = {}
            for row in active_schedules:
                group_key = get_movie_group_key(row["作品名"], include_format=split_by_format)
                if group_key not in grouped_schedules:
                    grouped_schedules[group_key] = []

                # 同一グループ内で全く同じ上映開始・終了時刻の重複を防ぐ
                if not any(s["開始時間"] == row["開始時間"] and s["終了時間"] == row["終了時間"] and s["劇場名"] == row["劇場名"] for s in grouped_schedules[group_key]):
                    item = dict(row)
                    item["グループ名"] = group_key
                    grouped_schedules[group_key].append(item)

            all_groups = list(grouped_schedules.keys())

            if len(all_groups) < 2:
                st.info("鑑賞ルートを検索するには、【ステップ2】で2つ以上の異なる作品（または字幕・吹替・上映形態違い）を選択して時間割表を表示してください。")
            else:
                st.write(f"**対象作品数:** {len(all_groups)} 作品")
                st.caption("対象作品: " + " / ".join(f"`{g}`" for g in all_groups))

                # 検索条件のコンボボックス
                interval_option = st.selectbox(
                    "ブロック間（インターバル）の条件",
                    ["短い(0min～)", "少し短い(15min～)", "少し長い(30min～)", "長い(45min～)"],
                    index=1
                )

                if st.button("🌟 鑑賞ルートを検索する", type="primary"):
                    with st.spinner("最適な組み合わせを検索中..."):
                        all_found_routes = []

                        # 深さ優先探索 (DFS) で鑑賞パターンを全探索
                        def search_dfs(current_route, visited_groups):
                            if current_route:
                                all_found_routes.append(list(current_route))

                            for g_key in all_groups:
                                if g_key in visited_groups:
                                    continue

                                for show in grouped_schedules[g_key]:
                                    if current_route:
                                        prev_show = current_route[-1]
                                        prev_end = time_to_minutes(prev_show["終了時間"])
                                        curr_start = time_to_minutes(show["開始時間"])

                                        if prev_end is None or curr_start is None:
                                            continue

                                        interval = curr_start - prev_end

                                        # 時間の重複（マイナス）は不可
                                        if interval < 0:
                                            continue

                                        # インターバル条件の判定
                                        if interval_option == "短い(5min～)" and interval < 5:
                                            continue
                                        elif interval_option == "少し短い(15min～)" and interval < 15:
                                            continue
                                        elif interval_option == "少し長い(30min～)" and interval < 30:
                                            continue
                                        elif interval_option == "長い(45min～)" and interval < 45:
                                            continue

                                    search_dfs(current_route + [show], visited_groups | {g_key})

                        # 探索開始
                        search_dfs([], set())

                        if not all_found_routes:
                            st.warning("指定された条件（インターバル時間など）に一致する鑑賞ルートは見つかりませんでした。")
                        else:
                            # 合計待ち時間を計算する関数
                            def calc_total_interval(route):
                                total = 0
                                for i in range(1, len(route)):
                                    prev_end = time_to_minutes(route[i-1]["終了時間"])
                                    curr_start = time_to_minutes(route[i]["開始時間"])
                                    total += (curr_start - prev_end)
                                return total

                            # 重複ルート除外
                            unique_routes = []
                            seen_signatures = set()
                            for r in all_found_routes:
                                sig = tuple((s["作品名"], s["劇場名"], s["開始時間"], s["終了時間"]) for s in r)
                                if sig not in seen_signatures:
                                    seen_signatures.add(sig)
                                    unique_routes.append(r)

                            # 全体での最大鑑賞グループ数を確認してメッセージを表示
                            max_group_count = max(len(r) for r in unique_routes)
                            if max_group_count == len(all_groups):
                                st.success(f"🎉 全 {len(all_groups)} グループを鑑賞できるルートが見つかりました！（各タブで上位5件を表示）")
                            else:
                                st.warning(f"⚠️ 全 {len(all_groups)} グループを鑑賞できるルートはありませんでした。最大 {max_group_count} グループ鑑賞可能です。")

                            # ==========================================
                            # タブによるソート切り替え機能 (Streamlit / Python)
                            # ==========================================
                            tab1, tab2, tab3 = st.tabs([
                                "🏆 鑑賞グループ数優先", 
                                "⏰ 1作品目の開始時間優先", 
                                "⏱️ 合計待ち時間優先"
                            ])

                            # ソート用キーの定義
                            # パターン1: 鑑賞グループ数(多い順) → 1作品目開始時間(早い順) → 合計待ち時間(短い順)
                            key_pattern1 = lambda r: (-len(r), time_to_minutes(r[0]["開始時間"]), calc_total_interval(r))
                
                            # パターン2: 1作品目開始時間(早い順) → 鑑賞グループ数(多い順) → 合計待ち時間(短い順)
                            key_pattern2 = lambda r: (time_to_minutes(r[0]["開始時間"]), -len(r), calc_total_interval(r))
                
                            # パターン3: 合計待ち時間(短い順) → 鑑賞グループ数(多い順) → 1作品目開始時間(早い順)
                            key_pattern3 = lambda r: (calc_total_interval(r), -len(r), time_to_minutes(r[0]["開始時間"]))

                            sort_configs = [
                                (tab1, key_pattern1, "なるべく多くの作品を観られるルートを優先します。"),
                                (tab2, key_pattern2, "1作品目の開始時間が早い（早く見始められる）ルートを優先します。"),
                                (tab3, key_pattern3, "作品間の合計待ち時間が短い（無駄な時間がない）ルートを優先します。")
                            ]

                            # 各タブへの描画処理
                            for tab, sort_key, desc in sort_configs:
                                with tab:
                                    st.caption(desc)
                                    sorted_routes = sorted(unique_routes, key=sort_key)
                                    top_routes = sorted_routes[:5]

                                    # 乗り換え案内風UIでの結果描画
                                    for idx, route in enumerate(top_routes):
                                        total_interval = calc_total_interval(route)
                                        group_cnt = len(route)

                                        st.markdown(f"#### パターン {idx + 1} （鑑賞作品数: {group_cnt}/{len(all_groups)} グループ ｜ ⏱️ 合計待ち時間: {total_interval}分）")

                                        html_lines = ["<div style='font-family: sans-serif; margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 8px; background-color: #fff;'>"]

                                        for i, show in enumerate(route):
                                            html_lines.append(f"""<div style='display: flex; margin-bottom: 0px;'>
<div style='width: 80px; text-align: right; padding-right: 15px; font-weight: bold; color: #333;'>
{show['開始時間']}<br>
<span style='font-size: 0.8em; color: #ccc;'>|</span><br>
<span style='color: #666;'>{show['終了時間']}</span>
</div>
<div style='border-left: 4px solid #1E90FF; padding-left: 15px; padding-bottom: 15px; position: relative;'>
<div style='position: absolute; left: -9px; top: 0px; width: 14px; height: 14px; border-radius: 50%; background-color: #1E90FF; border: 2px solid #fff;'></div>
<div style='font-weight: bold; font-size: 1.05em; color: #111;'>{show['作品名']}</div>
<div style='font-size: 0.8em; color: #888; margin-bottom: 4px;'>［グループ: {show['グループ名']}］</div>
<div style='font-size: 0.85em; color: #666;'>📍 {show['劇場名']}</div>
</div>
</div>""")

                                            if i < len(route) - 1:
                                                next_show = route[i+1]
                                                interval = time_to_minutes(next_show["開始時間"]) - time_to_minutes(show["終了時間"])
                                                html_lines.append(f"""<div style='display: flex; margin-bottom: 0px;'>
<div style='width: 80px; text-align: right; padding-right: 15px; font-size: 0.85em; color: #888; display: flex; flex-direction: column; justify-content: center;'>
待ち時間<br><span style='font-weight: bold; color: #555;'>{interval}分</span>
</div>
<div style='border-left: 4px dotted #ccc; padding-left: 15px; padding-bottom: 15px; height: 50px;'>
</div>
</div>""")

                                        html_lines.append("</div>")

                                        st.markdown("\n".join(html_lines), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
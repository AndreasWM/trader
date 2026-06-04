"""
iShares ETF Holdings Downloader
================================
Lädt die Ticker-Symbole des iShares Expanded Tech-Software Sector ETF (IGV)
und gibt sie als Python-Liste zurück.

Abhängigkeiten:
    pip install selenium pandas
"""

import io, os, re, tempfile, time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

ETF_URL = (
    "https://www.ishares.com/ch/professionelle-anleger/de/produkte/239771/"
    "ishares-north-american-techsoftware-etf"
)
# ETF_URL = (
#     "https://www.ishares.com/ch/professionelle-anleger/de/produkte/239705/"
#     "ishares-phlx-semiconductor-etf"
# )


DOWNLOAD_TIMEOUT = 60


def _make_driver(download_dir: str) -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_experimental_option("prefs", {
        "download.default_directory":   download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade":   True,
    })
    return webdriver.Chrome(options=opts)


def _wait_for_download(download_dir: str) -> str:
    deadline = time.time() + DOWNLOAD_TIMEOUT
    while time.time() < deadline:
        files = [f for f in os.listdir(download_dir)
                 if not f.endswith(".crdownload") and not f.startswith(".")]
        if files:
            time.sleep(0.5)
            return os.path.join(download_dir, files[0])
        time.sleep(0.3)
    raise TimeoutError(f"Download nicht abgeschlossen nach {DOWNLOAD_TIMEOUT}s.")


def get_symbols() -> list[str]:
    """
    Lädt die aktuellen ETF-Positionen von iShares und gibt die
    Ticker-Symbole als sortierte Liste zurück.

    Returns
    -------
    list[str]
        Z.B. ['ADBE', 'APP', 'CRWD', 'CRM', ...]
    """
    with tempfile.TemporaryDirectory() as download_dir:
        driver = _make_driver(download_dir)
        try:
            driver.get(ETF_URL)
            time.sleep(3)

            # Holdings-URL aus der gerenderten Seite lesen
            match = re.search(
                r'(/ch/[^"\'<\s]*\.ajax\?[^"\'<\s]*fileName=[^"\'<\s]*holdings[^"\'<\s]*)',
                driver.page_source, re.IGNORECASE
            )
            if not match:
                raise RuntimeError("Holdings-Download-Link nicht auf der Seite gefunden.")

            holdings_url = "https://www.ishares.com" + match.group(1).replace("&amp;", "&")
            driver.get(holdings_url)
            filepath = _wait_for_download(download_dir)

            with open(filepath, "rb") as f:
                data = f.read()
        finally:
            driver.quit()

    # CSV parsen: Header-Zeile anhand der Spaltenanzahl finden
    text  = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    counts = [line.count(",") for line in lines]
    hdr    = next(i for i, c in enumerate(counts) if c == max(counts))
    df     = pd.read_csv(
        io.StringIO("\n".join(lines[hdr:])),
        na_values=["-", "–", "N/A", "n/a", ""],
        on_bad_lines="warn",
    )
    df.dropna(how="all", inplace=True)

    # Nur Zeilen mit gültigem Ticker (nur Buchstaben) und Anlageklasse "Aktien"
    ticker_col = next(
        (c for c in df.columns if "ticker" in c.lower() or "emittent" in c.lower()),
        df.columns[0]
    )
    anlage_col = next(
        (c for c in df.columns if "anlageklasse" in c.lower() or "asset" in c.lower()),
        None
    )

    mask = df[ticker_col].notna() & df[ticker_col].astype(str).str.strip().str.match(r'^[A-Za-z]+$')
    if anlage_col:
        mask &= df[anlage_col].astype(str).str.strip().str.lower() == "aktien"

    symbols = df.loc[mask, ticker_col].str.strip().tolist()
    return symbols


if __name__ == "__main__":
    symbols = get_symbols()
    print(f"symbols = {symbols}")
    print(f"\n{len(symbols)} Symbole geladen.")
"""
universe.py
Universe saham per sektor untuk Regime Screener.

CATATAN JUJUR: ini BUKAN universe 840 emiten penuh dari build_setup.py Setup Board
(file itu tidak tersedia di sesi ini). Ini basket representatif per sektor,
bisa diperluas nanti begitu sumber data 840 emiten tersedia -- struktur kode
di bawah dirancang supaya tinggal ganti SECTOR_BASKETS tanpa ubah logic lain.

Daftar Papan Pengembangan BEI juga tidak ada scraper resminya di sini --
PAPAN_PENGEMBANGAN cuma placeholder dari yang disebutkan di riset sebelumnya
(NCKL, DOID per pemindahan 29 Mei 2026). Perlu di-update manual/dicek ulang
secara berkala.
"""

SECTOR_BASKETS = {
    "Barang Baku": ["TPIA.JK", "INTP.JK", "SMGR.JK", "INKP.JK", "ANTM.JK", "INCO.JK", "MDKA.JK"],
    "Energi": ["MEDC.JK", "PGAS.JK", "ADRO.JK", "PTBA.JK", "ITMG.JK", "AKRA.JK"],
    "Perindustrian": ["ASII.JK", "UNTR.JK", "HEXA.JK", "AUTO.JK"],
    "Keuangan": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "BBNI.JK", "BRIS.JK"],
    "Konsumer Siklikal": ["MAPI.JK", "ACES.JK", "LPPF.JK", "ERAA.JK"],
    "Properti": ["BSDE.JK", "CTRA.JK", "PWON.JK", "SMRA.JK"],
    "Kesehatan": ["KLBF.JK", "HEAL.JK", "MIKA.JK", "SIDO.JK"],
}

# Sektor yang secara struktur neraca wajar leverage tinggi -- DER TIDAK dipakai
# sebagai kriteria "berat naik" untuk sektor ini (sesuai kesepakatan: kriteria
# fundamental beda untuk sektor finansial).
SEKTOR_FINANSIAL = {"Keuangan"}

PAPAN_PENGEMBANGAN = {"NCKL.JK", "DOID.JK"}  # placeholder, perlu update manual berkala

ALL_TICKERS = sorted({t for basket in SECTOR_BASKETS.values() for t in basket})

"""Real French SKU catalog — 45 products, 4 zones."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class CatalogItem:
    code: str             # short canonical code (used in random sku_id)
    brand: str
    name: str             # full product name
    zone: str             # FROZEN | FRESH | AMBIENT | HEAVY
    weight_kg: float
    volume_l: float
    fragile: bool = False


CATALOG: List[CatalogItem] = [
    # ---------- FROZEN ----------
    CatalogItem("FRZ-EPI",  "Findus",       "Epinards branches 750g",        "FROZEN", 0.75, 0.8),
    CatalogItem("FRZ-FRT",  "Picard",       "Frites allumettes 1kg",         "FROZEN", 1.00, 1.2),
    CatalogItem("FRZ-LAS",  "Marie",        "Lasagnes Bolognaise 2 portions","FROZEN", 0.90, 1.1),
    CatalogItem("FRZ-ICE",  "Ben & Jerry's","Cookie Dough 500ml",            "FROZEN", 0.60, 0.6, True),
    CatalogItem("FRZ-MAI",  "Bonduelle",    "Mais surgele 600g",             "FROZEN", 0.60, 0.7),
    CatalogItem("FRZ-STK",  "Charal",       "Steaks haches x4",              "FROZEN", 0.80, 0.9),
    CatalogItem("FRZ-CRM",  "Pierre Martinet","Creme Brulee x4",             "FROZEN", 0.56, 0.7, True),
    CatalogItem("FRZ-CAB",  "Iglo",         "Cabillaud vapeur x2",           "FROZEN", 0.34, 0.5),
    CatalogItem("FRZ-TRT",  "Bonne Maman",  "Tarte aux pommes",              "FROZEN", 0.60, 1.0, True),
    CatalogItem("FRZ-PRO",  "Thiriet",      "Profiteroles 450g",             "FROZEN", 0.45, 0.8, True),

    # ---------- FRESH ----------
    CatalogItem("FRH-ACT",  "Danone",       "Activia Fraise 4x125g",         "FRESH",  0.50, 0.6, True),
    CatalogItem("FRH-BTR",  "President",    "Beurre Doux 250g",              "FRESH",  0.25, 0.3),
    CatalogItem("FRH-JAM",  "Fleury Michon","Jambon 4 tranches",             "FRESH",  0.26, 0.4, True),
    CatalogItem("FRH-CRM",  "Elle & Vire",  "Creme fraiche 20cl",            "FRESH",  0.22, 0.3, True),
    CatalogItem("FRH-YAO",  "Yoplait",      "Yaourt nature 16x125g",         "FRESH",  2.00, 2.4, True),
    CatalogItem("FRH-LRD",  "Leerdammer",   "Original tranches x12",         "FRESH",  0.30, 0.4),
    CatalogItem("FRH-LAI",  "Lactel",       "Lait demi-ecreme 1L",           "FRESH",  1.03, 1.1),
    CatalogItem("FRH-LAR",  "Herta",        "Lardons fumes 2x100g",          "FRESH",  0.20, 0.3),
    CatalogItem("FRH-PBR",  "Paysan Breton","Beurre sale 250g",              "FRESH",  0.25, 0.3),
    CatalogItem("FRH-CHV",  "Chavroux",     "Fromage de chevre 150g",        "FRESH",  0.15, 0.2, True),

    # ---------- AMBIENT ----------
    CatalogItem("AMB-FAR",  "Panzani",      "Pates Farfalle 500g",           "AMBIENT", 0.50, 0.7),
    CatalogItem("AMB-SPA",  "Barilla",      "Spaghetti n.5 500g",            "AMBIENT", 0.50, 0.7),
    CatalogItem("AMB-CER",  "Kellogg's",    "Corn Flakes 375g",              "AMBIENT", 0.375, 2.0),
    CatalogItem("AMB-CAF",  "Nestle",       "Nescafe Classic 200g",          "AMBIENT", 0.20, 0.5),
    CatalogItem("AMB-KET",  "Heinz",        "Ketchup 570g",                  "AMBIENT", 0.57, 0.8, True),
    CatalogItem("AMB-NUT",  "Ferrero",      "Nutella 750g",                  "AMBIENT", 0.75, 0.9, True),
    CatalogItem("AMB-EVN",  "Evian",        "Eau 6x1.5L pack",               "AMBIENT", 9.00, 9.5),
    CatalogItem("AMB-CCL",  "Coca-Cola",    "6x33cl",                        "AMBIENT", 1.98, 2.2),
    CatalogItem("AMB-PRG",  "Pringles",     "Original 185g",                 "AMBIENT", 0.185, 1.5, True),
    CatalogItem("AMB-FRT",  "Haribo",       "Fraises Tagada 300g",           "AMBIENT", 0.30, 0.5),
    CatalogItem("AMB-CAS",  "William Saurin","Cassoulet 840g",               "AMBIENT", 0.84, 1.0),
    CatalogItem("AMB-MOU",  "Amora",        "Moutarde de Dijon 440g",        "AMBIENT", 0.44, 0.5, True),
    CatalogItem("AMB-RIL",  "Bordeau Chesnel","Rillettes 220g",              "AMBIENT", 0.22, 0.3),
    CatalogItem("AMB-RIC",  "Ricard",       "1L",                            "AMBIENT", 1.10, 1.1, True),
    CatalogItem("AMB-ORN",  "Orangina",     "4x25cl",                        "AMBIENT", 1.00, 1.1),

    # ---------- HEAVY ----------
    CatalogItem("HVY-EVN",  "Evian",        "6x1.5L pack",                   "HEAVY", 9.00, 9.5),
    CatalogItem("HVY-ARI",  "Ariel",        "Lessive liquide 3.3L",          "HEAVY", 3.50, 3.8),
    CatalogItem("HVY-OLI",  "Lesieur",      "Huile d'olive 5L",              "HEAVY", 4.60, 5.2),
    CatalogItem("HVY-CCL",  "Coca-Cola",    "24x33cl caisses",               "HEAVY", 7.92, 8.5),
    CatalogItem("HVY-PER",  "Persil",       "Lessive poudre 3.38kg",         "HEAVY", 3.38, 5.0),
    CatalogItem("HVY-SOP",  "Sopalin",      "Essuie-tout x6",                "HEAVY", 0.60, 8.0),
    CatalogItem("HVY-LOT",  "Lotus",        "Papier WC x12",                 "HEAVY", 1.20, 15.0),
    CatalogItem("HVY-RIC",  "Ricard",       "6x1L carton",                   "HEAVY", 6.60, 7.0),
    CatalogItem("HVY-HEI",  "Heineken",     "24x25cl",                       "HEAVY", 6.00, 6.5),
    CatalogItem("HVY-SKP",  "Skip",         "Lessive liquide 2.37L",         "HEAVY", 2.50, 2.8),
]


CATALOG_BY_ZONE: Dict[str, List[CatalogItem]] = {}
for item in CATALOG:
    CATALOG_BY_ZONE.setdefault(item.zone, []).append(item)


def lookup(code: str) -> CatalogItem:
    for it in CATALOG:
        if it.code == code:
            return it
    raise KeyError(code)

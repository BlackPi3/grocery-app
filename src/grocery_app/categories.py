"""Categories: what kind of thing a product is.

Every insight built so far groups by `product_id`, which answers questions
about one product — personal inflation, the same item across stores — and
nothing about a *kind* of thing. "How much do I spend on chips" needs
something that says six bags across three shops are the same kind, and that
is this field's job.

Three levels, because the shopper wants to zoom:

    Molkereiprodukte & Eier  ->  Käse  ->  Reibekäse
    branch                       section   category

A product stores **only the category key**. Section and branch are derived
from the tables below, never written onto the record. That is the lesson
`is_budget_brand` cost us: the same fact copied onto 181 rows drifts, and
extending the table does not reach the rows already written. Regrouping here
is a one-line edit to `SECTIONS`, and no two products can disagree about which
branch `chips` belongs to, because neither of them carries the answer.

**The granularity rule is the shopping list.** A list says *Chips*, *Milch*,
*Reibekäse*. It does not say *Snacks* (too wide — "I buy Food every day" is
not an insight) and it does not say *funny-frisch Chipsfrisch Salt & Vinegar
175 g* (too narrow — that is just the product again).

**A category has to be recognisable, not merely true.** Open Food Facts filed
a chicken breast under `cut`, and Parham's objection is the exact test: he did
buy a cut, so the value is not false, but "cut" tells a person nothing about
what is in the bag. Truth is not the bar. The same reading makes Frisch Kauf's
coarse printed lines a legitimate category-level answer rather than a failure.

**The vocabulary is closed and lives here.** Free text is how `cut`, `chia`
and `stuffed wafers` got into the field in the first place, alongside
hand-written `Dairy` and `Snacks` — 46 distinct values over 181 products, which
nothing can group by. A product whose category is not in this table is a gap to
be reported, not a new category quietly minted.

**It is lifted from the retailers, not invented.** ALDI SÜD publishes a
153-leaf tree over its whole store and GLOBUS a three-level one (the third
level is in the product URLs, which the crawl does not record). Both are
German, human-designed, and already sit at shopping-list granularity — GLOBUS
files Kaffeesahne under `kaffeesahne-kondensmilch`, where a keyword matcher
reads "Kaffee" and files a cream under coffee. Their trees propose; they are
not the contract, because the stores disagree about shape (`Käse` is top-level
at ALDI, nested under dairy at GLOBUS) and cross-store comparison is the point
of the project. Same relationship this project already has with Open Food
Facts: their chain is evidence, our vocabulary is the contract.

**Keys are ascii, labels are German.** Identity is `reibekaese`; the word shown
to a reader is `Reibekäse`. `produce.py` already names the coupling this
avoids — there the vocabulary key doubles as the product name, which is the one
thing that has to be unpicked for a second market. A second language here is a
second label column.
"""

from __future__ import annotations

from grocery_app.resolver import fold

# --- level 1: the branches, roughly the parts of a shop you walk between ------
BRANCHES: dict[str, str] = {
    "obst-gemuese": "Obst & Gemüse",
    "molkerei": "Molkereiprodukte & Eier",
    "brot-aufstriche": "Brot, Aufstriche & Cerealien",
    "fleisch-fisch": "Fleisch & Fisch",
    "wurst": "Wurst & Aufschnitt",
    "suesswaren-snacks": "Süßigkeiten & salzige Snacks",
    "getraenke": "Getränke",
    "alkohol": "Alkoholische Getränke",
    "vorraete": "Vorräte",
    "konserven": "Konserven & Fertiggerichte",
    "tiefkuehl": "Tiefkühlung",
    "haushalt": "Haushaltsartikel",
    "drogerie": "Drogerie & Kosmetik",
}

# --- level 2: the sections within a branch ------------------------------------
# `Obst` and `Gemüse` are separate sections rather than one `Produce`, because
# "Produce" cannot tell you how much fruit you bought. Herbs are a third: dill
# is neither fruit nor vegetable, and GLOBUS shelves it separately too.
SECTIONS: dict[str, tuple[str, str]] = {
    "obst": ("Obst", "obst-gemuese"),
    "gemuese": ("Gemüse", "obst-gemuese"),
    "kraeuter": ("Frische Kräuter", "obst-gemuese"),
    "milch-joghurt": ("Milch & Joghurt", "molkerei"),
    "kaese": ("Käse", "molkerei"),
    "eier": ("Eier", "molkerei"),
    "milchersatz": ("Milchalternativen", "molkerei"),
    "backwaren": ("Brot & Backwaren", "brot-aufstriche"),
    "aufstriche": ("Aufstriche", "brot-aufstriche"),
    "cerealien": ("Müsli & Cerealien", "brot-aufstriche"),
    "fleisch": ("Fleisch", "fleisch-fisch"),
    "fisch": ("Fisch & Meeresfrüchte", "fleisch-fisch"),
    "aufschnitt": ("Wurst & Aufschnitt", "wurst"),
    "suesswaren": ("Süßigkeiten", "suesswaren-snacks"),
    "salzige-snacks": ("Salzige Snacks", "suesswaren-snacks"),
    "nuesse-trockenobst": ("Nüsse & Trockenobst", "suesswaren-snacks"),
    "heissgetraenke": ("Kaffee & Tee", "getraenke"),
    "kaltgetraenke": ("Kalte Getränke", "getraenke"),
    "wein": ("Wein", "alkohol"),
    "bier-spirituosen": ("Bier & Spirituosen", "alkohol"),
    "nudeln-reis": ("Nudeln, Reis & Hülsenfrüchte", "vorraete"),
    "gewuerze-oele": ("Saucen, Öle & Gewürze", "vorraete"),
    "backzutaten": ("Backzutaten", "vorraete"),
    "konserven-glas": ("Konserven & Glas", "konserven"),
    "fertiggerichte": ("Fertiggerichte", "konserven"),
    "tk-suesses": ("Eis & TK-Desserts", "tiefkuehl"),
    "tk-herzhaft": ("Tiefkühlkost", "tiefkuehl"),
    "reinigung": ("Wasch- & Putzmittel", "haushalt"),
    "papier-folien": ("Papier, Tücher & Folien", "haushalt"),
    "haushaltshelfer": ("Haushaltshelfer", "haushalt"),
    "koerperpflege": ("Körperpflege", "drogerie"),
    "gesundheit": ("Gesundheit", "drogerie"),
}

# --- level 3: the shopping-list line ------------------------------------------
# category key -> (German label, section key, folded aliases)
#
# Aliases are folded (lower case, umlauts expanded) because that is what a
# printed or catalog name is compared against. They are evidence for a
# *proposal* only; nothing here writes a category without review.
CATEGORIES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # -- Obst ------------------------------------------------------------------
    "aepfel": ("Äpfel", "obst", ("apfel", "aepfel")),
    "birnen": ("Birnen", "obst", ("birne", "birnen", "conference")),
    "bananen": ("Bananen", "obst", ("banane", "bananen")),
    "beeren": ("Beeren", "obst", ("heidelbeeren", "blaubeeren", "johannisbeeren",
                                  "erdbeeren", "himbeeren", "brombeeren", "beeren")),
    "steinobst": ("Steinobst", "obst", ("nektarine", "nektarinen", "pfirsich",
                                        "plattpfirsiche", "pflaumen", "kirschen",
                                        "aprikosen")),
    "zitrusfruechte": ("Zitrusfrüchte", "obst", ("zitrone", "zitronen", "limette",
                                                 "limetten", "orange", "orangen",
                                                 "mandarinen", "clementinen")),
    "trauben": ("Trauben", "obst", ("trauben", "weintrauben")),
    "melonen": ("Melonen", "obst", ("melone", "melonen", "wassermelone",
                                    "wassermelonen", "honigmelone")),
    "kiwis": ("Kiwis", "obst", ("kiwi", "kiwis")),
    "exotisches-obst": ("Exotisches Obst", "obst", ("avocado", "avocados", "physalis",
                                                    "mango", "ananas", "granatapfel")),
    # -- Gemüse ----------------------------------------------------------------
    "tomaten": ("Tomaten", "gemuese", ("tomate", "tomaten", "rispentomaten",
                                       "datteltomaten", "romatomaten", "cherrytomaten",
                                       "fleischtomaten", "flaschentomaten",
                                       "strauchtomaten", "kirschtomaten",
                                       "cocktailtomaten", "beef tomatoes")),
    "gurken": ("Gurken", "gemuese", ("gurke", "gurken", "salatgurken", "mini-gurken",
                                     "minigurken", "schlangengurke", "snackgurken")),
    "paprika-chili": ("Paprika & Chili", "gemuese", ("paprika", "spitzpaprika", "chili",
                                                     "peperoni", "bell pepper")),
    "zwiebeln-knoblauch": ("Zwiebeln & Knoblauch", "gemuese",
                           ("zwiebel", "zwiebeln", "speisezwiebeln", "lauchzwiebeln",
                            "fruehlingszwiebeln", "gemuesezwiebeln", "knoblauch",
                            "porree", "lauch")),
    "wurzelgemuese": ("Wurzelgemüse", "gemuese", ("karotte", "karotten", "moehre",
                                                  "moehren", "minimoehren", "babymoehren",
                                                  "radieschen", "sellerie", "rote bete",
                                                  "sweet potato", "suesskartoffel",
                                                  "suesskartoffeln")),
    "kartoffeln": ("Kartoffeln", "gemuese", ("kartoffel", "kartoffeln",
                                             "speisekartoffeln", "drillinge")),
    "salat": ("Salat", "gemuese", ("salat", "salatherzen", "babyspinat", "spinat",
                                   "rucola", "feldsalat", "eisbergsalat")),
    "kohlgemuese": ("Kohlgemüse", "gemuese", ("brokkoli", "blumenkohl", "kohlrabi",
                                              "rosenkohl", "weisskohl", "rotkohl")),
    "pilze": ("Pilze", "gemuese", ("champignon", "champignons", "pilze", "pfifferlinge")),
    "zucchini-auberginen": ("Zucchini & Auberginen", "gemuese",
                            ("zucchini", "aubergine", "auberginen")),
    # -- Frische Kräuter -------------------------------------------------------
    "frische-kraeuter": ("Frische Kräuter", "kraeuter",
                         ("schnittkraeuter", "dill", "minze", "petersilie", "basilikum",
                          "schnittlauch", "koriander", "rosmarin", "thymian")),
    # -- Milch & Joghurt -------------------------------------------------------
    "milch": ("Milch", "milch-joghurt", ("milch", "vollmilch", "h-milch", "h-vollmilch",
                                         "alpenmilch", "frischmilch", "whole milk",
                                         "lactofree", "laktosefrei")),
    "joghurt": ("Joghurt", "milch-joghurt", ("joghurt", "sahnejoghurt", "naturjoghurt",
                                             "fruchtjoghurt", "yogurt")),
    "skyr": ("Skyr", "milch-joghurt", ("skyr",)),
    "quark": ("Quark", "milch-joghurt", ("quark", "magerquark", "speisequark")),
    "sahne": ("Sahne & Schmand", "milch-joghurt",
              ("sahne", "kaffeesahne", "kochsahne", "schlagsahne", "schmand",
               "creme fraiche", "kondensmilch", "creme a la cuisine")),
    "butter": ("Butter & Margarine", "milch-joghurt", ("butter", "margarine")),
    "desserts": ("Desserts", "milch-joghurt", ("pudding", "dessert", "grieszbrei")),
    # -- Käse ------------------------------------------------------------------
    "reibekaese": ("Reibekäse", "kaese", ("reibekaese", "gerieben", "geriebener")),
    "frischkaese": ("Frischkäse", "kaese", ("frischkaese", "huettenkaese")),
    "schnittkaese": ("Schnittkäse", "kaese", ("schnittkaese", "gouda", "edamer",
                                              "emmentaler", "kaesescheiben")),
    "hartkaese": ("Hartkäse", "kaese", ("hartkaese", "parmesan", "bergkaese")),
    "weichkaese": ("Weichkäse", "kaese", ("weichkaese", "camembert", "brie",
                                          "feta", "hirtenkaese", "mozzarella")),
    "kaese-snacks": ("Käsewürfel & Snacks", "kaese", ("kaesewuerfel", "kaesesnack")),
    # -- Eier, Milchalternativen ----------------------------------------------
    "eier-kat": ("Eier", "eier", ("ei", "eier", "eggs", "bruderkueken",
                                  "bodenhaltung", "freilandeier")),
    "pflanzendrink": ("Pflanzendrinks", "milchersatz",
                      ("pflanzendrink", "haferdrink", "sojadrink", "mandeldrink",
                       "plant-based", "milchalternative")),
    # -- Brot & Backwaren ------------------------------------------------------
    "brot": ("Brot", "backwaren", ("brot", "vollkornbrot", "bread")),
    "toastbrot": ("Toastbrot", "backwaren", ("toast", "toastbrot", "toast bread")),
    "broetchen": ("Brötchen & Baguette", "backwaren",
                  ("broetchen", "baguette", "weizenbroetchen", "saatenbroetchen",
                   "vollkornbroetchen", "rolls", "buns", "wraps")),
    "suessgebaeck": ("Süßgebäck & Kuchen", "backwaren",
                     ("kuchen", "torte", "suessgebaeck", "blaetterteiggebaeck",
                      "schokokraenze", "croissant")),
    "herzhaftes-gebaeck": ("Herzhaftes Gebäck", "backwaren",
                           ("boerek", "blaetterteig herzhaft", "laugengebaeck")),
    "knaeckebrot": ("Knäckebrot & Zwieback", "backwaren",
                    ("knaeckebrot", "zwieback", "reiswaffeln")),
    # -- Aufstriche ------------------------------------------------------------
    "marmelade": ("Marmelade & Fruchtaufstrich", "aufstriche",
                  ("konfituere", "marmelade", "fruchtaufstrich", "gelee", "jam")),
    "honig": ("Honig & Sirup", "aufstriche",
              ("honig", "honey", "sirup", "syrup", "ahornsirup", "maple")),
    "schokocreme": ("Nuss- & Schokocreme", "aufstriche",
                    ("nussnougatcreme", "schokocreme", "nutella", "erdnussbutter")),
    "herzhafte-aufstriche": ("Herzhafte Aufstriche", "aufstriche",
                             ("guacamole", "zaziki", "tzatziki", "hummus",
                              "kraeuterquark", "brotaufstrich")),
    # -- Cerealien -------------------------------------------------------------
    "muesli": ("Müsli & Flocken", "cerealien",
               ("muesli", "haferflocken", "flocken", "cornflakes", "cerealien",
                "porridge")),
    "muesliriegel": ("Müsliriegel", "cerealien", ("muesliriegel", "fruchtriegel")),
    # -- Fleisch & Fisch -------------------------------------------------------
    "gefluegel": ("Geflügel", "fleisch", ("haehnchen", "haehnchenbrust", "haehnchenbrustfilet",
                                          "innenbrustfilet", "pute", "chicken", "poultry",
                                          "chicken breast")),
    "rind": ("Rindfleisch", "fleisch", ("rind", "rindfleisch", "steak")),
    "schwein": ("Schweinefleisch", "fleisch", ("schwein", "schweinefleisch", "schnitzel")),
    "hackfleisch": ("Hackfleisch", "fleisch", ("hackfleisch", "gehacktes")),
    "fisch-kat": ("Fisch & Meeresfrüchte", "fisch",
                  ("lachs", "fisch", "thunfisch", "garnelen", "forelle")),
    # -- Wurst -----------------------------------------------------------------
    "salami": ("Salami", "aufschnitt", ("salami",)),
    "schinken": ("Schinken", "aufschnitt", ("schinken",)),
    "fleischwurst": ("Fleisch- & Streichwurst", "aufschnitt",
                     ("fleischwurst", "streichwurst", "leberwurst", "bratwurst",
                      "wuerstchen")),
    # -- Süßigkeiten -----------------------------------------------------------
    "schokolade": ("Schokolade", "suesswaren",
                   ("schokolade", "tafelschokolade", "chocolate", "schokolinsen",
                    "amicelli", "kitkat", "schoko rosinen", "schokorosinen",
                    "confetteria", "konfekt", "nougat")),
    "kekse": ("Kekse", "suesswaren", ("keks", "kekse", "kekstaler", "cookies",
                                      "haferkekse", "biscuit")),
    "waffeln": ("Waffeln", "suesswaren", ("waffel", "waffeln", "waffeltaler",
                                          "schnitten")),
    "fruchtgummi": ("Fruchtgummi & Lakritz", "suesswaren",
                    ("fruchtgummi", "goldbaeren", "lakritz", "gummibaerchen",
                     "weingummi")),
    "bonbons": ("Bonbons & Kaugummi", "suesswaren", ("bonbon", "bonbons", "kaugummi",
                                                     "drops", "lutscher")),
    # -- Salzige Snacks --------------------------------------------------------
    "chips": ("Chips", "salzige-snacks",
              ("chips", "kartoffelchips", "chipsfrisch", "crisps", "tortilla chips",
               "pufuleti", "knabbereien", "flips", "erdnussflips")),
    "cracker": ("Cracker & Salzgebäck", "salzige-snacks",
                ("cracker", "salzgebaeck", "salzstangen", "tuc")),
    # -- Nüsse & Trockenobst ---------------------------------------------------
    "nuesse": ("Nüsse & Kerne", "nuesse-trockenobst",
               ("nuesse", "walnuesse", "walnuts", "pistazien", "mandeln", "cashew",
                "haselnuesse", "studentenfutter", "kerne", "chia", "chia samen",
                "leinsamen", "sonnenblumenkerne")),
    "trockenobst": ("Trockenobst", "nuesse-trockenobst",
                    ("sultaninen", "rosinen", "trockenfruechte", "trockenobst",
                     "datteln", "aprikosen getrocknet")),
    # -- Kaffee & Tee ----------------------------------------------------------
    "kaffee": ("Kaffee", "heissgetraenke",
               ("kaffee", "coffee", "bohnenkaffee", "espresso", "kaffeepads",
                "kaffeekapseln", "instantkaffee", "filterkaffee")),
    "tee": ("Tee", "heissgetraenke", ("tee", "tea", "kraeutertee", "fruechtetee",
                                      "gruener tee", "schwarzer tee", "rooibos")),
    "kakao": ("Kakao", "heissgetraenke", ("kakao", "kakaopulver", "cocoa",
                                          "trinkschokolade")),
    # -- Kalte Getränke --------------------------------------------------------
    "wasser": ("Wasser", "kaltgetraenke", ("mineralwasser", "tafelwasser",
                                           "sprudel", "stilles wasser")),
    "saft": ("Saft & Smoothies", "kaltgetraenke",
             ("saft", "direktsaft", "orangendirektsaft", "nektar", "smoothie",
              "juice")),
    "limonade": ("Limonade & Cola", "kaltgetraenke",
                 ("cola", "coca-cola", "limonade", "limo", "brause", "eistee",
                  "energydrink")),
    "milchgetraenke": ("Milch- & Kaffeegetränke", "kaltgetraenke",
                       ("milchdrink", "kaffeegetraenk", "latte macchiato",
                        "chocolate milk", "milchmischgetraenk")),
    # -- Alkohol ---------------------------------------------------------------
    "rotwein": ("Rotwein", "wein", ("rotwein", "primitivo", "merlot", "chianti",
                                    "red wine")),
    "weisswein": ("Weißwein", "wein", ("weisswein", "riesling", "grauburgunder",
                                       "white wine")),
    "sekt": ("Sekt & Schaumwein", "wein", ("sekt", "schaumwein", "prosecco",
                                           "champagner")),
    "bier": ("Bier", "bier-spirituosen", ("bier", "pils", "weizenbier", "beer")),
    "spirituosen": ("Spirituosen", "bier-spirituosen", ("spirituosen", "wodka",
                                                        "whisky", "rum", "likoer",
                                                        "gin")),
    # -- Vorräte ---------------------------------------------------------------
    "nudeln": ("Nudeln & Pasta", "nudeln-reis", ("nudeln", "pasta", "spaghetti",
                                                 "lasagneblaetter", "penne",
                                                 "makkaroni")),
    "reis": ("Reis", "nudeln-reis", ("reis", "basmati", "basmatireis", "rice",
                                     "risotto")),
    "huelsenfruechte": ("Hülsenfrüchte", "nudeln-reis",
                        ("linsen", "bohnen", "kichererbsen", "wachtelbohnen",
                         "kidneybohnen", "huelsenfruechte", "beans")),
    "gewuerze": ("Gewürze & Salz", "gewuerze-oele",
                 ("gewuerz", "gewuerze", "pfeffer", "zimt", "salz", "meersalz",
                  "paprikapulver", "curry", "oregano", "seasoning")),
    "oel-essig": ("Öl & Essig", "gewuerze-oele",
                  ("oel", "sonnenblumenoel", "olivenoel", "rapsoel", "essig",
                   "balsamico", "oil")),
    "saucen": ("Saucen & Dressings", "gewuerze-oele",
               ("sauce", "saucen", "dressing", "ketchup", "mayonnaise", "senf",
                "remoulade", "salatsauce", "fix fuer")),
    "bruehe": ("Brühe & Fonds", "gewuerze-oele", ("bruehe", "bouillon", "fond",
                                                  "suppenwuerze")),
    "backzutaten-kat": ("Backzutaten", "backzutaten",
                        ("mehl", "backpulver", "zucker", "vanillezucker",
                         "backmischung", "kokosraspeln", "desiccated coconut",
                         "speisestaerke", "hefe")),
    # -- Konserven & Fertiggerichte -------------------------------------------
    "gemuesekonserven": ("Gemüsekonserven", "konserven-glas",
                         ("gehackte tomaten", "passierte tomaten", "mais dose",
                          "gemuesekonserve", "tomatenmark")),
    "essiggemuese": ("Essiggemüse", "konserven-glas",
                     ("gewuerzgurken", "salz-dill-gurken", "cornichons",
                      "silberzwiebeln", "oliven", "antipasti")),
    "obstkonserven": ("Obstkonserven", "konserven-glas", ("pfirsiche dose",
                                                          "obstkonserve",
                                                          "fruchtcocktail")),
    "fertiggerichte-kat": ("Fertiggerichte", "fertiggerichte",
                           ("fertiggericht", "ravioli", "eintopf", "suppe",
                            "instantnudeln")),
    "pizza": ("Pizza", "fertiggerichte", ("pizza", "flammkuchen", "picco belli")),
    # -- Tiefkühlung -----------------------------------------------------------
    "speiseeis": ("Speiseeis", "tk-suesses",
                  ("speiseeis", "eiscreme", "eisschale", "eis am stiel",
                   "frozen dessert", "schofrulade")),
    "tk-backwaren": ("TK-Desserts & Backwaren", "tk-suesses", ("tk dessert",
                                                               "tiefkuehl kuchen")),
    "tk-gemuese": ("TK-Gemüse", "tk-herzhaft", ("tk gemuese", "gemuesesortiment",
                                                "erbsen tiefgekuehlt", "rahmspinat")),
    "tk-kartoffel": ("Pommes & Kartoffelprodukte", "tk-herzhaft",
                     ("pommes", "wedges", "kroketten", "roesti")),
    "tk-fertig": ("TK-Fertiggerichte", "tk-herzhaft", ("tk pfannengericht",
                                                       "tiefkuehl fertiggericht")),
    # -- Haushalt --------------------------------------------------------------
    "waschmittel": ("Waschmittel", "reinigung",
                    ("waschmittel", "weichspueler", "fleckenentferner",
                     "schmutzfaenger", "detergent")),
    "spuelmittel": ("Spülmittel", "reinigung",
                    ("spuelmittel", "geschirrspuel", "spuelmaschinentabs",
                     "klarspueler", "spuelmaschinensalz", "dishwasher",
                     "dishwashing")),
    "putzmittel": ("Putzmittel", "reinigung",
                   ("putzmittel", "allzweckreiniger", "badreiniger", "wc-reiniger",
                    "schimmelentferner", "reinigungstuecher", "scheuermilch",
                    "mould remover", "cleaning cloth")),
    "schwaemme": ("Schwämme & Bürsten", "haushaltshelfer",
                  ("schwamm", "topfreiniger", "spuelbuerste", "scourer",
                   "putzlappen")),
    "kuechenrolle": ("Küchenrolle", "papier-folien",
                     ("kuechenrolle", "kuechenrollen", "kuechentuecher",
                      "haushaltstuecher", "kitchen roll")),
    "taschentuecher": ("Taschen- & Kosmetiktücher", "papier-folien",
                       ("taschentuecher", "kosmetiktuecher", "tempo", "kleenex",
                        "tissue")),
    "toilettenpapier": ("Toilettenpapier", "papier-folien", ("toilettenpapier",
                                                             "klopapier")),
    "folien-beutel": ("Folien & Beutel", "papier-folien",
                      ("gefrierbeutel", "muellbeutel", "abfallbeutel", "frischhaltefolie",
                       "alufolie", "backpapier", "garbage bag", "freezer bag")),
    "haushaltswaren": ("Haushaltswaren", "haushaltshelfer",
                       ("handschuhe", "haushaltshandschuhe", "batterien",
                        "destilliertes wasser", "distilled water", "kerzen",
                        "gloves")),
    # -- Drogerie --------------------------------------------------------------
    "duschgel": ("Duschgel & Seife", "koerperpflege",
                 ("duschgel", "dusche", "seife", "duschbad", "shower gel")),
    "koerperpflege-kat": ("Körper- & Gesichtspflege", "koerperpflege",
                          ("bodylotion", "creme", "gesichtspflege", "handcreme",
                           "waschemulsion", "waschlotion", "reinigungsmilch",
                           "make-up remover", "abschminktuecher")),
    "deo": ("Deodorant", "koerperpflege", ("deo", "deodorant", "deo-stick",
                                           "antitranspirant")),
    "haarpflege": ("Shampoo & Haarpflege", "koerperpflege", ("shampoo", "spuelung",
                                                             "haarpflege",
                                                             "conditioner")),
    "zahnpflege": ("Zahnpflege", "koerperpflege", ("zahnpasta", "zahnbuerste",
                                                   "mundspuelung", "zahnseide")),
    "hygiene": ("Hygieneartikel", "koerperpflege",
                ("wattepads", "wattestaebchen", "binden", "tampons", "cotton pad")),
    "nahrungsergaenzung": ("Nahrungsergänzung", "gesundheit",
                           ("magnesium", "vitamin", "vitamine", "supplement",
                            "nahrungsergaenzung", "zink", "eisen")),
}

# The sections where a null brand is the final answer rather than a gap. You
# pick loose fruit, vegetables and herbs up by weight and no barcode exists, so
# no lookup, no scan and no shopper will ever supply a brand. Everything else
# in a packet has a label that someone has simply not read yet.
#
# This replaces `category.startswith("Produce")`, which stopped meaning anything
# once `Produce` became `Obst`, `Gemüse` and `Kräuter`.
PRODUCE_SECTIONS: frozenset[str] = frozenset({"obst", "gemuese", "kraeuter"})


def is_produce(category_key: str | None) -> bool:
    """True when a null brand on this category is the final answer, not a gap."""
    entry = CATEGORIES.get(category_key or "")
    return bool(entry) and entry[1] in PRODUCE_SECTIONS


def label(category_key: str) -> str:
    return CATEGORIES[category_key][0]


def section_of(category_key: str) -> str:
    return CATEGORIES[category_key][1]


def branch_of(category_key: str) -> str:
    return SECTIONS[section_of(category_key)][1]


def path(category_key: str) -> tuple[str, str, str]:
    """The three labels a reader sees, coarsest first.

    `reibekaese` -> ("Molkereiprodukte & Eier", "Käse", "Reibekäse")
    """
    section = section_of(category_key)
    section_label, branch = SECTIONS[section]
    return BRANCHES[branch], section_label, label(category_key)


def problems(branches: dict[str, str] | None = None,
             sections: dict[str, tuple[str, str]] | None = None,
             categories: dict[str, tuple[str, str, tuple[str, ...]]] | None = None,
             ) -> list[str]:
    """Every way the three tables disagree with each other. Empty is good.

    The tables are hand-written and reference each other by key, so a typo in a
    section name is the obvious failure. It is checked here, as data, rather
    than discovered as a KeyError halfway through a batch run. The tables are
    arguments so the checks can be exercised on made-up ones.
    """
    BRANCHES_, SECTIONS_, CATEGORIES_ = branches, sections, categories
    branches = BRANCHES if BRANCHES_ is None else BRANCHES_
    sections = SECTIONS if SECTIONS_ is None else SECTIONS_
    categories = CATEGORIES if CATEGORIES_ is None else CATEGORIES_
    found: list[str] = []
    for section, (_, branch) in sorted(sections.items()):
        if branch not in branches:
            found.append(f"section {section}: unknown branch {branch}")
    for key, (text, section, aliases) in sorted(categories.items()):
        if section not in sections:
            found.append(f"category {key}: unknown section {section}")
        if not text:
            found.append(f"category {key}: no label")
        if len(set(aliases)) != len(aliases):
            found.append(f"category {key}: duplicate aliases")
    used = {section for _, section, _ in categories.values()}
    for section in sorted(set(sections) - used):
        found.append(f"section {section}: no categories")
    used_branches = {branch for _, branch in sections.values()}
    for branch in sorted(set(branches) - used_branches):
        found.append(f"branch {branch}: no sections")

    # An alias that reaches two categories makes a proposal a coin toss, and a
    # coin toss written down is exactly the failure this vocabulary exists to
    # remove.
    owners: dict[str, list[str]] = {}
    for key, (_, _, aliases) in categories.items():
        for alias in aliases:
            owners.setdefault(fold(alias), []).append(key)
    for alias, keys in sorted(owners.items()):
        if len(set(keys)) > 1:
            found.append(f"alias {alias!r} claimed by {', '.join(sorted(set(keys)))}")
    return found
